import {readFileSync} from 'node:fs';
import {randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
// Example of another agent hiring this Coworker over MIP-003. Never pays, never reads keys: payment is the purchaser's own step.
export const startJobBody=prompt=>({identifier_from_purchaser:randomBytes(8).toString('hex'),input_data:{prompt}});
const get=async(base,path)=>{const r=await fetch(base+path,{signal:AbortSignal.timeout(30000)});if(!r.ok)throw new Error(`${path} HTTP ${r.status}`);return r.json()};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export async function hire(base,prompt,{pollMs=10000,log=console.log}={}){
 log('availability:',JSON.stringify(await get(base,'/availability')));
 log('input_schema:',JSON.stringify(await get(base,'/input_schema')));
 const r=await fetch(base+'/start_job',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(startJobBody(prompt)),signal:AbortSignal.timeout(30000)});
 if(!r.ok)throw new Error(`/start_job HTTP ${r.status}`);
 const job=await r.json(),id=job.job_id||job.id;
 log(`job ${id}. Payment is the purchaser's step, this script does not pay.`);
 log('Lock 1 tUSDM on your own Masumi Payment Service (POST /api/v1/purchase) with:');
 for(const k of ['blockchainIdentifier','agentIdentifier','sellerVKey','payByTime','submitResultTime','unlockTime','externalDisputeUnlockTime'])log(`  ${k}: ${job[k]}`);
 while(Date.now()<Number(job.submitResultTime)){
  const s=await get(base,`/status?job_id=${encodeURIComponent(id)}`);log('status:',s.status);
  if(s.status==='completed'||s.status==='failed'){log(s.result??'No result: the job stopped before a negotiation summary was made.');return s}
  await sleep(pollMs);
 }
 log('submitResultTime passed without a result. If you paid, the escrow is refundable.');
}
if(process.argv[1]===fileURLToPath(import.meta.url))hire(process.env.AGENT_URL||'http://127.0.0.1:21950',readFileSync(process.argv[2]||'negotiator/examples/request.txt','utf8')).catch(e=>{console.error(e.message);process.exit(1)});
