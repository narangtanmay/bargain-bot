import {test} from 'node:test';
import assert from 'node:assert/strict';
import {buildSokosumiInvocation,runSokosumiCli} from './sokosumi-cli.mjs';

test('Windows CLI invocation safely calls the configured Sokosumi command shim',()=>{
 const invocation=buildSokosumiInvocation(['--preprod','tasks','list','--personal'],{platform:'win32',env:{SOKOSUMI_CLI_PATH:'C:\\Users\\Adrian User\\npm\\sokosumi.cmd'}});
 assert.equal(invocation.command,'cmd.exe');
 assert.deepEqual(invocation.args,['/d','/s','/c','call "C:\\Users\\Adrian User\\npm\\sokosumi.cmd" "--preprod" "tasks" "list" "--personal"']);
});

test('Windows CLI invocation rejects shell metacharacters in the path or arguments',()=>{
 assert.throws(()=>buildSokosumiInvocation(['tasks','list & whoami'],{platform:'win32',env:{}}),/unsupported shell characters/);
 assert.throws(()=>buildSokosumiInvocation(['--version'],{platform:'win32',env:{SOKOSUMI_CLI_PATH:'sokosumi.cmd & whoami'}}),/unsupported shell characters/);
});

test('non-Windows invocation executes the CLI directly',()=>{
 const invocation=buildSokosumiInvocation(['--version'],{platform:'linux',env:{}});
 assert.deepEqual(invocation,{command:'sokosumi',args:['--version']});
});

test('CLI runner passes through argv and process options',()=>{
 let call;
 const output=runSokosumiCli(['--version'],{platform:'win32',env:{SOKOSUMI_CLI_PATH:'sokosumi.cmd'},encoding:'utf8',run:(...args)=>{call=args;return '1.0.4';}});
 assert.equal(output,'1.0.4');
 assert.equal(call[0],'cmd.exe');
 assert.deepEqual(call[1],['/d','/s','/c','call "sokosumi.cmd" "--version"']);
 assert.equal(call[2].encoding,'utf8');
 assert.equal(call[2].windowsHide,true);
 assert.equal(call[2].windowsVerbatimArguments,true);
});
