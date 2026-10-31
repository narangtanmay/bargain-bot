import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync,mkdirSync,mkdtempSync,rmSync,writeFileSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname,join,delimiter} from 'node:path';
import {fileURLToPath} from 'node:url';
import * as paidTask from './paid-task.mjs';

const worker=join(dirname(fileURLToPath(import.meta.url)),'worker.mjs');
const registration={status:'RegistrationConfirmed',agentIdentifier:'demo-agent',supportedPaymentSourceIndex:0,walletId:'demo-wallet'};
const runtime='MPS_RUNTIME_TOKEN=demo-test-token\n';
function fixture({registry=registration,credential=runtime,url='http://127.0.0.1:21949'}={}){
 const directory=mkdtempSync(join(tmpdir(),'payment-safety-'));
 mkdirSync(join(directory,'docs'));
 if(registry!==null)writeFileSync(join(directory,'docs','registration-state.json'),typeof registry==='string'?registry:JSON.stringify(registry));
 if(credential!==null){mkdirSync(join(directory,'.local'));writeFileSync(join(directory,'.local','mps-runtime.env'),credential,{mode:0o600});}
 const marker=join(directory,'cli-called');
 const cli=join(directory,process.platform==='win32'?'sokosumi.cmd':'sokosumi');
 const cliScript=join(directory,'fake-cli.mjs');
 const runtimeRoot=join(directory,'fake-cli');
 mkdirSync(join(runtimeRoot,'dist','src','coworker'),{recursive:true});
 mkdirSync(join(runtimeRoot,'dist','src','api','services'),{recursive:true});
 writeFileSync(join(runtimeRoot,'package.json'),'{"type":"module"}');
 writeFileSync(join(runtimeRoot,'dist','src','coworker','runtime-credentials.js'),"export const readRuntimeCredential=()=> 'synthetic-test-only';\n");
 writeFileSync(join(runtimeRoot,'dist','src','api','http-client.js'),'export const createCoworkerHttpClient=()=> ({});\n');
 writeFileSync(join(runtimeRoot,'dist','src','api','services','task-service.js'),'export const fetchTaskEvents=async()=>({events:[]});export const createTaskEvent=async()=>({});\n');
 writeFileSync(cliScript,`#!${process.execPath}\nimport('node:fs').then(fs=>{if(process.argv.slice(2).join(' ')==='skills path'){process.stdout.write(${JSON.stringify(join(runtimeRoot,'skills'))}+'\\n');}else{fs.writeFileSync(${JSON.stringify(marker)},'called');process.stdout.write('{"tasks":[]}\\n');}});\n`,{mode:0o700});
 if(process.platform==='win32')writeFileSync(cli,`@echo off\r\n\"${process.execPath}\" \"${cliScript}\" %*\r\n`);
 else writeFileSync(cli,readFileSync(cliScript,'utf8'),{mode:0o700});
 return {directory,marker,env:{SystemRoot:process.env.SystemRoot??'',WINDIR:process.env.WINDIR??'',SOKOSUMI_CLI_PATH:cli,COWORKER_ID:'demo-coworker',PAID_TASKS_ENABLED:'true',MPS_URL:url,PATH:process.platform==='win32'?[directory,join(process.env.SystemRoot,'System32')].join(delimiter):directory},cleanup:()=>rmSync(directory,{recursive:true,force:true})};
}

test('paid worker refuses startup before polling or locking when registration is absent',()=>{
 const f=fixture({registry:null,credential:null});
 try{
  const child=spawnSync(process.execPath,[worker],{cwd:f.directory,env:f.env,encoding:'utf8',timeout:1000});
  assert.doesNotMatch(child.stdout,/Continuous worker running/);
  assert.equal(child.status,1,child.stderr);
  assert.match(child.stderr,/refusing to process Tasks without escrow/);
  assert.equal(existsSync(f.marker),false);
  assert.equal(existsSync(join(f.directory,'.local','worker.lock')),false);
 }finally{f.cleanup();}
});

test('paid readiness rejects incomplete or malformed setup and accepts complete synthetic setup',()=>{
 const previous=process.cwd(),previousUrl=process.env.MPS_URL;
 const cases=[
  [{},true],
  [{registry:null},false],
  [{registry:'{'},false],
  [{registry:{...registration,status:'Pending'}},false],
  [{registry:{...registration,agentIdentifier:''}},false],
  [{registry:{...registration,supportedPaymentSourceIndex:undefined}},false],
  [{registry:{...registration,walletId:''}},false],
  [{credential:null},false],
  [{credential:'MPS_RUNTIME_TOKEN=*****masked\n'},false],
  [{credential:'MPS_RUNTIME_TOKEN=\n'},false],
  [{url:''},false],
  [{url:'file:///tmp/mps'},false],
 ];
 try{
  for(const [options,expected] of cases){
   const f=fixture(options);
   try{
    process.chdir(f.directory);process.env.MPS_URL=f.env.MPS_URL;
    assert.equal(paidTask.isPaidReady(),expected,JSON.stringify(options));
   }finally{process.chdir(previous);f.cleanup();}
  }
 }finally{if(previousUrl===undefined)delete process.env.MPS_URL;else process.env.MPS_URL=previousUrl;}
});

test('paid startup policy permits unpaid mode and requires readiness only for paid mode',()=>{
 assert.equal(typeof paidTask.assertPaidTasksReady,'function');
 assert.equal(paidTask.assertPaidTasksReady('false',false),false);
 assert.equal(paidTask.assertPaidTasksReady(undefined,false),false);
 assert.equal(paidTask.assertPaidTasksReady('true',true),true);
 assert.throws(()=>paidTask.assertPaidTasksReady('true',false),/refusing to process Tasks without escrow/);
});

test('unpaid worker starts and polls with the supported CLI adapter',()=>{
 const f=fixture({registry:null,credential:null});
 try{
  const child=spawnSync(process.execPath,[worker],{cwd:f.directory,env:{...f.env,PAID_TASKS_ENABLED:'false',MOCK_AGENT:'false',NEGOTIATOR_LLM:'off',NEGOTIATOR_TACTICIAN:'off'},encoding:'utf8',timeout:1500});
  assert.match(child.stdout,/Continuous worker running/,child.stderr);
  assert.equal(existsSync(f.marker),true,child.stderr);
  assert.equal(child.error?.code,'ETIMEDOUT');
 }finally{f.cleanup();}
});
