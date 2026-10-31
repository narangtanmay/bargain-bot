import {test} from 'node:test';
import {verifiedDeal} from './test-fixtures/verified-result.mjs';
import assert from 'node:assert/strict';
import {mkdtempSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {taskHash,purchasePayload,createPaidAdapter,confirmedState,assertPaidTasksReady,USDM} from './paid-task.mjs';
// A fresh clone has no .local/ yet; run there so a missing mkdir cannot hide behind another test file.
process.chdir(mkdtempSync(join(tmpdir(),'paid-task-')));
const registration={walletId:'seller-wallet',agentIdentifier:'a'.repeat(80),supportedPaymentSourceIndex:0};
const target={coworkerId:'coworker',organizationId:null};
const task={id:'task',coworkerId:'coworker',organizationId:null};
const core={get:async()=>({data:task})};
const payment={sellerReturnAddress:null,forceLayer:null,PaymentSource:{network:'Preprod',paymentSourceType:'Web3CardanoV2',smartContractAddress:'addr_test1contract',policyId:'a'.repeat(56)},SmartContractWallet:{id:'seller-wallet',walletVkey:'b'.repeat(56)},RequestedFunds:[{amount:'1000000',unit:USDM}],agentIdentifier:registration.agentIdentifier,blockchainIdentifier:'signed',inputHash:taskHash('abc'),payByTime:String(Date.now()+100000),submitResultTime:String(Date.now()+200000),unlockTime:'9999999999999',externalDisputeUnlockTime:'9999999999999'};
test('Task compatibility hashes exact UTF-8 bytes without JSON escapes or nonce',()=>{
 assert.equal(taskHash('abc'),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
 assert.notEqual(taskHash('a\nb'),taskHash('a\\nb'));
});
test('paid mode refuses to process Tasks when MPS setup is not confirmed',()=>{
 assert.equal(assertPaidTasksReady('false',false),false);
 assert.equal(assertPaidTasksReady(undefined,false),false);
 assert.throws(()=>assertPaidTasksReady('true',false),/refusing to process Tasks without escrow/);
 assert.equal(assertPaidTasksReady('true',true),true);
});
test('signed fields preserved and unsupported signed override rejected',()=>{
 const payload=purchasePayload(payment,'01020304050607',registration);
 assert.equal(payload.blockchainIdentifier,payment.blockchainIdentifier);
 assert.equal(payload.unlockTime,payment.unlockTime);
 assert.throws(()=>purchasePayload({...payment,forceLayer:'L1'},'nonce',registration),/cannot preserve/);
 assert.throws(()=>purchasePayload({...payment,sellerReturnAddress:'addr_test1seller'},'nonce',registration),/cannot preserve/);
 assert.throws(()=>purchasePayload({...payment,SmartContractWallet:{id:'other'}},'nonce',registration),/differs/);
});
test('uncertain purchase never reposted',async()=>{
 let posts=0;const adapter=await createPaidAdapter({target,registration,save:async()=>{},negotiate:async()=>{throw Error('unexpected model')},core:{...core,post:async()=>{posts++;throw Error('timeout')}}});
 await assert.rejects(()=>adapter.advance(task,{input:'abc',paid:{stage:'purchase-pending'}}),/automatic retry disabled/);
 assert.equal(posts,0);
});
test('unconfirmed escrow does not invoke model',async()=>{
 let sends=0;const adapter=await createPaidAdapter({target,core,registration,save:async()=>{},negotiate:async()=>{sends++;},mps:async()=>({...payment,onChainState:'FundsLocked',CurrentTransaction:{status:'Pending'}})});
 const state=await adapter.advance(task,{input:'abc',paid:{stage:'awaiting-escrow',payment}});
 assert.equal(sends,0);assert.equal(state.paid.stage,'awaiting-escrow');
});
test('expired deadline prevents model after confirmed read',async()=>{
 let sends=0;const expired={...payment,submitResultTime:'1'};
 const adapter=await createPaidAdapter({target,core,registration,save:async()=>{},negotiate:async()=>{sends++;},mps:async()=>({...expired,onChainState:'FundsLocked',CurrentTransaction:{status:'Confirmed',newOnChainState:'FundsLocked'}})});
 await assert.rejects(()=>adapter.advance(task,{input:'abc',paid:{stage:'awaiting-escrow',payment:expired}}),/deadline expired/);
 assert.equal(sends,0);
});

test('confirmed history proves lock when CurrentTransaction is absent',()=>{
 assert.equal(confirmedState({CurrentTransaction:null,TransactionHistory:[{status:'Confirmed',newOnChainState:'FundsLocked'}]},'FundsLocked'),true);
 assert.equal(confirmedState({CurrentTransaction:null,TransactionHistory:[{status:'Confirmed',newOnChainState:'ResultSubmitted'}]},'FundsLocked'),false);
});
test('successful quote survives later payload rejection',async()=>{
 let saved; const adapter=await createPaidAdapter({target,core,registration,save:async(_,s)=>{saved=s},negotiate:async()=>{},mps:async()=>({...payment,forceLayer:'L1'})});
 const state=await adapter.advance(task,{input:'abc'});
 assert.equal(saved.paid.payment.blockchainIdentifier,'signed');
 assert.equal(state.paid.stage,'terms-saved');
 await assert.rejects(()=>adapter.advance(task,state),/cannot preserve/);
});

test('running MPS legacy response without unsigned forceLayer is supported',()=>{const older={...payment};delete older.forceLayer;assert.equal(purchasePayload(older,'nonce',registration).blockchainIdentifier,'signed');});

test('unrelated confirmed transaction cannot prove escrow',()=>{assert.equal(confirmedState({CurrentTransaction:{status:'Confirmed',newOnChainState:'Withdrawn'}},'FundsLocked'),false)});

test('paid execution rejects another Workspace or Coworker before any saved state or payment write',async()=>{
 let writes=0;
 const target={coworkerId:'event-coworker',organizationId:'event-organization'};
 const adapter=await createPaidAdapter({target,registration,save:async()=>{writes++;},negotiate:async()=>{},mps:async()=>{writes++;return payment;}});
 for(const task of [
  {id:'task',coworkerId:'event-coworker',organizationId:null},
  {id:'task',coworkerId:'event-coworker',organizationId:'other-organization'},
  {id:'task',coworkerId:'other-coworker',organizationId:'event-organization'},
 ])await assert.rejects(adapter.advance(task,{input:'abc'}),/configured Coworker and Workspace/);
 assert.equal(writes,0);
});

function escrowed(outcome){
 const calls=[],events=[],saved=[];
 const adapter=createPaidAdapter({target,registration,save:async(_,s)=>{saved.push(s)},negotiate:async()=>outcome,
  core:{...core,post:async(path,body)=>{events.push(body);return {data:{id:'event'}}}},
  mps:async path=>{calls.push(path);return {...payment,onChainState:'FundsLocked',CurrentTransaction:{status:'Confirmed',newOnChainState:'FundsLocked'}}}});
 return {adapter,calls,events,saved};
}
test('no deal never submits a result and completes the Task with a refund note',async()=>{
 for(const status of ['no_deal','invalid_request','error']){
  const {adapter,calls,events,saved}=escrowed({status,summary:`${status} summary`});
  let state=await (await adapter).advance(task,{input:'abc',phase:'started',paid:{stage:'awaiting-escrow',payment}});
  state=await (await adapter).advance(task,state);
  assert.equal(calls.includes('/api/v1/payment/submit-result'),false);
  assert.equal(state.phase,'completed');assert.equal(state.paid.stage,'no-result');
  assert.equal(state.paid.payment.blockchainIdentifier,'signed');assert.equal(state.paid.observed.blockchainIdentifier,'signed');
  assert.equal(saved.some(s=>s.paid.stage==='no-result-pending'),true);
  assert.equal(events.length,1);assert.equal(events[0].status,'COMPLETED');assert.match(events[0].comment,/No result was submitted.*refunded/);
 }
});
test('deal submits the summary hash to MPS',async()=>{
 const {adapter,calls}=escrowed(verifiedDeal());
 let state=await (await adapter).advance(task,{input:'abc',paid:{stage:'awaiting-escrow',payment}});
 assert.equal(state.paid.resultHash,taskHash('deal summary'));
 state=await (await adapter).advance(task,state);
 assert.equal(state.paid.stage,'awaiting-result');
 assert.deepEqual(calls.filter(c=>c.endsWith('submit-result')),['/api/v1/payment/submit-result']);
});

test('a claimed deal without complete passing verification never submits a payment result',async()=>{
 const unverified=verifiedDeal();unverified.result.checks[0].passed=false;
 for(const outcome of [unverified,{status:'deal',summary:'claimed deal'}]){
  const {adapter,calls,events}=escrowed(outcome);
  let state=await (await adapter).advance(task,{input:'abc',paid:{stage:'awaiting-escrow',payment}});
  state=await (await adapter).advance(task,state);
  assert.equal(state.paid.stage,'no-result');assert.equal(state.paid.negotiation,'error');
  assert.equal(calls.some(c=>c.endsWith('submit-result')),false);
  assert.equal(events[0].status,'COMPLETED');
 }
});
