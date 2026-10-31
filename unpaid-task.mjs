import {mockProcurementResult} from './mock-agent.mjs';
import {ensureVerifiedOutcome} from './negotiate.mjs';

// Network and file operations are injected so this same lifecycle runs locally without a live Task.
export async function advanceUnpaidTask(taskId,state,{negotiate,mockMode=false,save,writeResult,complete,record=()=>{}}){
 if(state.phase==='started'){
  await save({...state,phase:'model-pending'});
  let outcome;
  if(mockMode){
   try{const summary=mockProcurementResult(state.input);outcome={status:'mock',summary,result:JSON.parse(summary)};}
   catch(error){outcome={status:'invalid_request',summary:error.message,result:null};}
  }else{outcome=ensureVerifiedOutcome(await negotiate(state.input));record(taskId,outcome);}
  await writeResult(outcome.summary);
  state={...state,phase:'result-saved',negotiation:outcome.status};await save(state);
 }
 if(state.phase==='result-saved'){
  await save({...state,phase:'complete-pending'});
  const completion=await complete();
  state={...state,phase:'completed',completion};await save(state);
 }
 return state;
}
