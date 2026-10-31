import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {advanceUnpaidTask} from './unpaid-task.mjs';
import {negotiate,CHECK_NAMES} from './negotiate.mjs';

const jsonRequest={item:'stainless steel mounting bracket',quantity:2000,max_unit_price_eur:4.8,delivery_days:21,must_haves:['delivery within deadline','payment terms net 30']};
async function run(input,{mockMode=false,phase='started',negotiate:runNegotiator=negotiate}={}){
 const saved=[],results=[],recorded=[],completions=[];
 const state=await advanceUnpaidTask('local-unpaid-fixture',{phase,input},{mockMode,negotiate:runNegotiator,
  save:async state=>saved.push(state),writeResult:async summary=>results.push(summary),
  record:(id,outcome)=>recorded.push(outcome),complete:async()=>{assert.equal(saved.at(-1).phase,'complete-pending');completions.push('complete');return {status:'COMPLETED'};}});
 return {state,saved,results,recorded,completions};
}

test('mock JSON completes unpaid without invoking the engine or claiming a deal',async()=>{
 const input=readFileSync('mock-procurement-request.json','utf8');
 const runResult=await run(input,{mockMode:true,negotiate:()=>{throw Error('mock invoked negotiator')}});
 const result=JSON.parse(runResult.results[0]);
 assert.equal(runResult.state.phase,'completed');assert.equal(runResult.state.negotiation,'mock');
 assert.equal(result.buyer_request.raw,input);assert.deepEqual(result.buyer_request.parsed,JSON.parse(input));
 assert.equal(result.payment.status,'NOT_PERFORMED');assert.equal(result.quote,null);
 assert.equal(runResult.recorded.length,0);assert.equal(runResult.completions.length,1);
});

for(const [name,input,status] of [
 ['text deal',readFileSync('negotiator/examples/request-normal.txt','utf8'),'deal'],
 ['JSON deal',JSON.stringify(jsonRequest),'deal'],
 ['above cap',JSON.stringify({...jsonRequest,scenario:'above_cap'}),'no_deal'],
 ['broken signed confirmation',JSON.stringify({...jsonRequest,scenario:'broken_quote'}),'no_deal'],
 ['incomplete JSON','{"item":"bracket"}','invalid_request'],
 ['malformed JSON','{bad json','invalid_request'],
])test(name+' completes through the local unpaid lifecycle',async()=>{
 const {state,recorded,saved,results,completions}=await run(input);
 assert.equal(state.phase,'completed');assert.equal(state.negotiation,status);
 assert.equal(recorded[0].status,status);assert.equal(results.length,1);assert.equal(completions.length,1);
 assert.deepEqual(saved.map(s=>s.phase),['model-pending','result-saved','complete-pending','completed']);
 if(status==='deal'){
  assert.deepEqual(recorded[0].result.checks.map(c=>c.name),CHECK_NAMES);
  assert.equal(recorded[0].result.checks.every(c=>c.passed===true),true);
 }
 if(input.includes('broken_quote'))assert.equal(recorded[0].result.checks.find(c=>c.name==='confirmation_matches_accepted_sheet').passed,false);
});

test('claimed unverified deal is completed as an error without publishing its deal summary',async()=>{
 const {state,results}=await run('item: x',{negotiate:async()=>({status:'deal',summary:'unchecked deal'})});
 assert.equal(state.negotiation,'error');assert.notEqual(results[0],'unchecked deal');
});

test('saved results resume completion without running negotiation again',async()=>{
 const {state,results,completions}=await run('item: x',{phase:'result-saved',negotiate:()=>{throw Error('duplicate negotiation')}});
 assert.equal(state.phase,'completed');assert.equal(results.length,0);assert.equal(completions.length,1);
});
