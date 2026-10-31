import {execFile} from 'node:child_process';
import {mkdirSync,mkdtempSync,readFileSync,rmSync,writeFileSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {promisify} from 'node:util';
import {decodeTaskInput} from './task-input.mjs';
const run=promisify(execFile);
const STATUSES=['deal','no_deal','invalid_request'];
const SCENARIOS=['normal','above_cap','broken_quote'];
export const CHECK_NAMES=['unit_price_within_cap','total_within_max','price_below_opening_quote','quantity_matches','delivery_within_deadline','must_haves_met','supplier_confirmation_present','confirmation_signature_valid','confirmation_matches_accepted_sheet','total_consistent'];
export function scenarioFrom(input){
 let parsed;try{parsed=decodeTaskInput(input).parsed}catch{}
 if(parsed)return SCENARIOS.includes(parsed.scenario)?parsed.scenario:'normal';
 const m=/^\s*scenario\s*:\s*(\S+)\s*$/im.exec(input);
 return SCENARIOS.includes(m?.[1]?.toLowerCase())?m[1].toLowerCase():'normal';
}
function failure(reason){return {status:'error',summary:`Negotiation failed: ${reason}. No deal was made.`,result:null};}
export function parseOutcome(text){
 let result;
 try{result=JSON.parse(text)}catch{return failure('negotiator returned malformed JSON')}
 if(!STATUSES.includes(result?.status))return failure('negotiator returned an unknown status');
 if(typeof result.summary_markdown!=='string'||!result.summary_markdown.trim())return failure('negotiator returned no summary');
 if(result.status==='deal'&&(typeof result.quote!=='object'||result.quote===null))return failure('negotiator returned a deal without a quote');
 if(result.status==='deal'&&(!Array.isArray(result.checks)||result.checks.length!==CHECK_NAMES.length||
  CHECK_NAMES.some((name,i)=>result.checks[i]?.name!==name||result.checks[i]?.passed!==true)))return failure('deal did not pass the complete verification contract');
 return {status:result.status,summary:result.summary_markdown,result};
}
export function ensureVerifiedOutcome(outcome){
 if(outcome?.status!=='deal')return outcome;
 const verified=parseOutcome(JSON.stringify(outcome.result));
 if(verified.status!=='deal')return verified;
 return outcome.summary===verified.summary?outcome:failure('deal summary differs from the verified result');
}
export async function negotiate(input,{seed,scenario,timeoutMs=120000,pythonBin=process.env.PYTHON_BIN||'python3',pythonArgs=[]}={}){
 if(typeof input!=='string'||!input.trim()||input.length>16000)return {status:'invalid_request',summary:'The task text must contain 1 to 16000 characters.',result:null};
 try{decodeTaskInput(input)}catch(error){return {status:'invalid_request',summary:error.message,result:null}}
 scenario=SCENARIOS.includes(scenario)?scenario:scenarioFrom(input);
 mkdirSync('.local',{recursive:true,mode:0o700});
 const dir=resolve(mkdtempSync('.local/negotiate-'));
 try{
  const requestFile=join(dir,'request.txt'),out=join(dir,'result.json');
  writeFileSync(requestFile,input,{mode:0o600});
  const args=[...pythonArgs,'-m','negotiator','--request-file',requestFile,'--out',out];
  if(Number.isInteger(seed))args.push('--seed',String(seed));
  if(scenario!=='normal')args.push('--scenario',scenario);
  try{await run(pythonBin,args,{cwd:process.env.NEGOTIATOR_DIR||join(dirname(fileURLToPath(import.meta.url)),'negotiator'),timeout:timeoutMs,maxBuffer:4*1024*1024});}
  catch(e){console.error('Negotiator failed',String(e.stderr||e.message).slice(0,200));return failure(e.killed?'negotiator timed out':'negotiator crashed');}
  let text;
  try{text=readFileSync(out,'utf8')}catch{return failure('negotiator wrote no result file')}
  return parseOutcome(text);
 }finally{rmSync(dir,{recursive:true,force:true});}
}
