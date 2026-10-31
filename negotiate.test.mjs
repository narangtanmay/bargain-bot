import {test,beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {readdirSync} from 'node:fs';
import {negotiate,scenarioFrom,parseOutcome,ensureVerifiedOutcome} from './negotiate.mjs';
import {verifiedDeal} from './test-fixtures/verified-result.mjs';
const fixtures=fileURLToPath(new URL('./test-fixtures/',import.meta.url));
const request='item: bracket\nquantity: 2000\nmax_unit_price_eur: 4.80\ndelivery_days: 21\n';
beforeEach(()=>{process.env.NEGOTIATOR_DIR=fixtures;});
function run(mode,input=request,options){process.env.FAKE_NEGOTIATOR=mode;return negotiate(input,{pythonBin:process.execPath,pythonArgs:[resolve(fixtures,'fake-python.mjs')],...options});}
test('deal returns the negotiator summary and contract-only flags',async()=>{
 const outcome=await run('deal',request,{seed:7});
 assert.equal(outcome.status,'deal');assert.equal(outcome.summary,'deal summary');
 assert.deepEqual(outcome.result.args.slice(0,2),['-m','negotiator']);
 assert.deepEqual(outcome.result.args.slice(-2),['--seed','7']);
 assert.equal(outcome.result.cwd,resolve(fixtures));
});
test('no_deal passes through with its summary',async()=>{
 assert.deepEqual(await run('no_deal').then(o=>[o.status,o.summary]),['no_deal','no_deal summary']);
});
test('scenario line in the task text is passed as --scenario',async()=>{
 const outcome=await run('no_deal',`${request}Scenario: above_cap\n`);
 assert.deepEqual(outcome.result.args.slice(-2),['--scenario','above_cap']);
 assert.equal(scenarioFrom('scenario: rm -rf'),'normal');
});
test('malformed JSON, unknown status, crash and timeout become error',async()=>{
 for(const [mode,options] of [['malformed'],['unknown'],['crash'],['hang',{timeoutMs:300}]]){
  const outcome=await run(mode,request,options);
  assert.equal(outcome.status,'error',mode);assert.match(outcome.summary,/No deal was made/);assert.equal(outcome.result,null);
 }
});
test('empty task text is rejected without running the negotiator',async()=>{
 assert.equal((await run('crash','  ')).status,'invalid_request');
});
test('private request files are removed after each run',async()=>{
 await run('deal');
 assert.deepEqual(readdirSync('.local').filter(f=>f.startsWith('negotiate-')),[]);
});

test('deal status cannot bypass missing, failed, duplicate, or non-boolean verification checks',()=>{
 const good=verifiedDeal().result;
 assert.equal(parseOutcome(JSON.stringify(good)).status,'deal');
 const variants=[[],good.checks.slice(1),good.checks.map((c,i)=>i===0?{...c,passed:false}:c),
  good.checks.map((c,i)=>i===0?{...c,passed:'true'}:c),good.checks.map((c,i)=>i===0?good.checks[1]:c)];
 for(const checks of variants)assert.equal(parseOutcome(JSON.stringify({...good,checks})).status,'error');
 assert.equal(ensureVerifiedOutcome({status:'deal',summary:'unverified'}).status,'error');
 assert.equal(ensureVerifiedOutcome({...verifiedDeal(),summary:'changed after verification'}).status,'error');
});

test('JSON request is kept intact and its scenario reaches the subprocess',async()=>{
 const input=' \n'+JSON.stringify({item:'bracket',quantity:2000,max_unit_price_eur:4.8,delivery_days:21,scenario:'broken_quote'})+'\n';
 const outcome=await run('no_deal',input);
 assert.equal(outcome.result.raw_request,input);
 assert.deepEqual(outcome.result.args.slice(-2),['--scenario','broken_quote']);
 for(const malformed of ['{bad json','[]'])assert.equal((await run('crash',malformed)).status,'invalid_request');
});
