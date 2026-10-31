import {existsSync,readFileSync,writeFileSync} from 'node:fs';
import {runSokosumiCli} from './sokosumi-cli.mjs';
import {acquireWorkerLock} from './worker-lock.mjs';
import {negotiate} from './negotiate.mjs';
import {isMockMode} from './mock-agent.mjs';
import {advanceUnpaidTask} from './unpaid-task.mjs';
import {reply} from './comments.mjs';
import {recordNegotiation} from './followup.mjs';
import {createPaidAdapter,isPaidReady,assertPaidTasksReady} from './paid-task.mjs';
import {taskTarget,isTaskForTarget} from './task-target.mjs';
const target=taskTarget();
const id=target.coworkerId;
if(isMockMode()&&process.env.PAID_TASKS_ENABLED==='true')throw new Error('MOCK_AGENT requires PAID_TASKS_ENABLED=false');
const paidModeEnabled=assertPaidTasksReady(process.env.PAID_TASKS_ENABLED,isPaidReady());
const releaseLock=acquireWorkerLock();
process.once('exit',releaseLock);
for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>{releaseLock();process.exit(0)});
function cli(args){return JSON.parse(runSokosumiCli(['--preprod',...args,'--json'],{encoding:'utf8',timeout:30000,maxBuffer:4*1024*1024}));}
const paid=await createPaidAdapter({target,negotiate,record:recordNegotiation,save:async(taskId,state)=>writeFileSync(`.local/${taskId}.json`,JSON.stringify(state),{mode:0o600})});
console.log('Continuous worker running',process.pid);
while(true){
 try{
 const tasks=cli(['tasks','list','--coworker-id',id,...target.taskArgs]).tasks;
 for(const t of tasks.filter(t=>isTaskForTarget(t,target))){
 try{
 const journal=`.local/${t.id}.json`,resultFile=`.local/${t.id}.txt`;
 let state=existsSync(journal)?JSON.parse(readFileSync(journal,'utf8')):{};
 if(t.status==='READY'&&!state.phase){writeFileSync(journal,JSON.stringify({phase:'starting'}),{mode:0o600});const started=cli(['runtime','start',t.id,...target.runtimeArgs,'--coworker-id',id]);state={phase:'started',input:started.description};writeFileSync(journal,JSON.stringify(state),{mode:0o600});}
 if(state.paid&&!paidModeEnabled)continue;
 if(state.paid||(state.phase==='started'&&paidModeEnabled)){state=await paid.advance(t,state);if(state.phase==='completed')await reply(t);continue;}
 state=await advanceUnpaidTask(t.id,state,{
  negotiate,record:recordNegotiation,mockMode:isMockMode(),
  save:async next=>writeFileSync(journal,JSON.stringify(next),{mode:0o600}),
  writeResult:async summary=>writeFileSync(resultFile,summary,{mode:0o600}),
  complete:async()=>cli(['runtime','complete',t.id,...target.runtimeArgs,'--coworker-id',id,'--result-file',resultFile])
 });
 if(state.phase==='completed')await reply(t);
 }catch(e){console.error('Task blocked',t.id,e.message.slice(0,200))}
 }
 }catch(e){console.error('Polling read failed',e.message.slice(0,200))}
 await new Promise(r=>setTimeout(r,5000));
}
