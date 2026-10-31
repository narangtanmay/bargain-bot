import {test} from 'node:test';
import assert from 'node:assert/strict';
import {replyText,answerComments} from './followup.mjs';
const checks=[...'abcdef'].map((n,i)=>({name:`check_${n}`,passed:i!==2,detail:'d'}));
const deal={status:'deal',summary:'s',result:{quote:{supplier:'Supplier B',unit_price_eur:4.75,total_eur:9500},checks:checks.map(c=>({...c,passed:true}))}};
test('deal reply states supplier, prices, six checks and next step',()=>{
 const t=replyText(deal);
 assert.match(t,/Deal: Supplier B at EUR 4\.75 per unit, total EUR 9500\.00\./);
 assert.equal(t.match(/PASS/g).length,6);
 assert.match(t,/create a new Task\.$/);
});
test('no_deal reply names failed check and shows FAIL',()=>{
 const t=replyText({status:'no_deal',summary:'x',result:{quote:null,checks}});
 assert.match(t,/No deal \(no_deal\): failed checks: check_c\./);
 assert.match(t,/FAIL check_c/);assert.equal(t.match(/PASS/g).length,5);
});
test('missing result says none is stored',()=>{
 assert.match(replyText(null),/No negotiation result is stored for this Task/);
});
test('replies once per buyer comment and never to own comments',async()=>{
 const posts=[];const ev=[{id:'1',actor:{type:'user'},comment:'hi'},{id:'2',actor:{type:'agent'},comment:'mine'},{id:'3',actor:{type:'user'},comment:'  '}];
 const args={events:ev,state:{},load:()=>deal,post:async c=>posts.push(c),save:()=>{}};
 const s=await answerComments(args);
 await answerComments({...args,state:s});
 assert.equal(posts.length,1);assert.deepEqual(s,{1:'posted'});
});
