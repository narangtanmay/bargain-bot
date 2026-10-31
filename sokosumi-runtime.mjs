import {join,win32,posix} from 'node:path';
import {pathToFileURL} from 'node:url';
import {runSokosumiCli} from './sokosumi-cli.mjs';
let loaded;
export const runSokosumi=runSokosumiCli;
export function sokosumiRoot(run=(command,args,options)=>runSokosumiCli(args,options)){
 const raw=run('sokosumi',['skills','path'],{encoding:'utf8',timeout:30000}).trim();
 const paths=raw.startsWith('/')?posix:win32;
 const skillsPath=paths.normalize(raw);
 if(!paths.isAbsolute(skillsPath)||paths.basename(skillsPath)!=='skills')throw new Error('sokosumi skills path returned an invalid package path');
 return paths.join(paths.dirname(skillsPath),'dist','src');
}
export async function loadSokosumiRuntime(){
 if(!loaded){const root=sokosumiRoot();
  loaded=Promise.all(['coworker/runtime-credentials.js','api/http-client.js','api/services/task-service.js'].map(p=>import(pathToFileURL(join(root,p)).href))).then(modules=>Object.assign({},...modules));
 }
 return loaded;
}
