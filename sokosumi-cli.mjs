import {execFileSync} from 'node:child_process';

const safeWindowsToken=/^[A-Za-z0-9_ .:/\\@+-]+$/u;

export function buildSokosumiInvocation(args,{platform=process.platform,env=process.env}={}){
 if(!Array.isArray(args)||args.some(arg=>typeof arg!=='string'))throw new TypeError('Sokosumi CLI arguments must be strings');
 if(platform!=='win32')return {command:env.SOKOSUMI_CLI_PATH||'sokosumi',args};
 const cliPath=env.SOKOSUMI_CLI_PATH||'sokosumi.cmd';
 if(!safeWindowsToken.test(cliPath))throw new Error('SOKOSUMI_CLI_PATH contains unsupported shell characters');
 for(const arg of args)if(!safeWindowsToken.test(arg))throw new Error('Sokosumi CLI argument contains unsupported shell characters');
 const commandLine=`call "${cliPath}" ${args.map(arg=>`"${arg}"`).join(' ')}`;
 return {command:'cmd.exe',args:['/d','/s','/c',commandLine]};
}

export function runSokosumiCli(args,{platform=process.platform,env=process.env,run=execFileSync,...options}={}){
 const invocation=buildSokosumiInvocation(args,{platform,env});
 return run(invocation.command,invocation.args,{...options,...(platform==='win32'?{windowsHide:true,windowsVerbatimArguments:true}:{})});
}
