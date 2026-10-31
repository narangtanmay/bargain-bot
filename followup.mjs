import {existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
export const resultPath=taskId=>`.local/${taskId}-negotiation.json`;
export function recordNegotiation(taskId,{status,summary,result}){
 mkdirSync('.local',{recursive:true,mode:0o700});writeFileSync(resultPath(taskId),JSON.stringify({status,summary,result}),{mode:0o600});
}
export function loadNegotiation(taskId){
 return existsSync(resultPath(taskId))?JSON.parse(readFileSync(resultPath(taskId),'utf8')):null;
}
const AGAIN='To negotiate again with different limits, create a new Task.';
const eur=n=>`EUR ${Number(n).toFixed(2)}`;
export function replyText(stored){
 if(!stored)return 'No negotiation result is stored for this Task.';
 const {status,summary,result}=stored;
 const checks=result?.checks??[];
 const failed=checks.filter(c=>!c.passed).map(c=>c.name);
 const q=result?.quote;
 const outcome=status==='deal'&&q
  ?`${result.opening_prices_source==='provided'?'Simulated deal':'Deal'}: ${q.supplier} at ${eur(q.unit_price_eur)} per unit, total ${eur(q.total_eur)}.`
  :`No deal (${status}): ${failed.length?`failed checks: ${failed.join(', ')}`:String(summary).split('\n').find(l=>l.trim())||'no reason recorded'}.`.replace(/\.\.$/,'.');
 const lines=checks.map(c=>`- ${c.passed?'PASS':'FAIL'} ${c.name}: ${c.detail}`);
 return [outcome,...(lines.length?['Checks:',...lines]:[]),AGAIN].join('\n');
}
// Replies at most once per buyer comment. state maps event id to post-pending|posted.
export async function answerComments({events,state,load,post,save}){
 let next={...state};
 for(const e of events.filter(e=>e.actor?.type==='user'&&typeof e.comment==='string'&&e.comment.trim())){
  if(next[e.id])continue;
  next={...next,[e.id]:'post-pending'};save(next);
  await post(replyText(load()));
  next={...next,[e.id]:'posted'};save(next);
 }
 return next;
}
