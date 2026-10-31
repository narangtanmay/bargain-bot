import {test} from 'node:test';
import {verifiedDeal} from './test-fixtures/verified-result.mjs';
import assert from 'node:assert/strict';
import {runPaidJob} from './agent-api.mjs';
import {resultHash} from './standard-hash.mjs';
const payment={blockchainIdentifier:'bid',submitResultTime:String(Date.now()+600000)};
const run=async(outcome)=>{
 const job={id:'j',nonce:'0a0b0c0d0e0f10',input:{prompt:'item: x'}},calls=[],written=[];
 await runPaidJob({job,payment,negotiate:async()=>outcome,mps:async(...a)=>{calls.push(a)},save:()=>{},writeResult:(j,t)=>written.push(t)});
 return {job,calls,written};
};
test('deal submits the summary hash once and awaits result',async()=>{
 const {job,calls,written}=await run(verifiedDeal('Deal done'));
 assert.equal(calls.length,1);assert.equal(calls[0][0],'/payment/submit-result');
 assert.equal(calls[0][1].submitResultHash,resultHash('Deal done',job.nonce));
 assert.equal(job.phase,'awaiting-result');assert.deepEqual(written,['Deal done']);
});
test('no_deal never submits and fails the job with the summary',async()=>{
 const {job,calls}=await run({status:'no_deal',summary:'No supplier fits'});
 assert.equal(calls.length,0);assert.equal(job.status,'failed');assert.equal(job.phase,'no-result');
 assert.equal(job.negotiation,'no_deal');assert.equal(job.result,'No supplier fits');
});
for(const status of ['error','invalid_request'])test(`${status} never submits`,async()=>{
 const {job,calls}=await run({status,summary:'nope'});
 assert.equal(calls.length,0);assert.equal(job.phase,'no-result');assert.equal(job.negotiation,status);
});

test('a claimed deal without passing verification never submits through the agent API',async()=>{
 const outcome=verifiedDeal();outcome.result.checks[8].passed=false;
 const {job,calls,written}=await run(outcome);
 assert.equal(job.negotiation,'error');assert.equal(job.phase,'no-result');
 assert.deepEqual(calls,[]);assert.deepEqual(written,[]);
});
