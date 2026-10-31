import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {isMockMode} from './mock-agent.mjs';
import {loadSokosumiRuntime} from './sokosumi-runtime.mjs';
import {taskTarget,assertTaskTarget,verifyRuntimeTask} from './task-target.mjs';
import {answerComments,loadNegotiation} from './followup.mjs';
const target=taskTarget();
const {readRuntimeCredential,createCoworkerHttpClient,fetchTaskEvents,createTaskEvent}=await loadSokosumiRuntime();
const runtime=createCoworkerHttpClient({apiKey:readRuntimeCredential(target.coworkerId)});
export async function reply(task){
 if(isMockMode())return;
 assertTaskTarget(task,target);
 const taskId=task.id;
 await verifyRuntimeTask(runtime,taskId,target);
 const p=`.local/${taskId}-comments.json`;
 const state=existsSync(p)?JSON.parse(readFileSync(p,'utf8')):{};
 const {events}=await fetchTaskEvents(runtime,taskId,AbortSignal.timeout(30000));
 await answerComments({events,state,load:()=>loadNegotiation(taskId),save:s=>writeFileSync(p,JSON.stringify(s),{mode:0o600}),
  post:async comment=>{await verifyRuntimeTask(runtime,taskId,target);await createTaskEvent(runtime,taskId,{comment},AbortSignal.timeout(30000));}});
}
