import {createServer} from 'node:http';
import {randomUUID} from 'node:crypto';
import {existsSync,readFileSync,writeFileSync,mkdirSync,readdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {negotiate,scenarioFrom,ensureVerifiedOutcome} from './negotiate.mjs';
import {inputHash,resultHash,sha256} from './standard-hash.mjs';
import {confirmedState} from './paid-task.mjs';
const jobsDir='.local/standard-jobs';mkdirSync(jobsDir,{recursive:true,mode:0o700});
const token=process.env.MPS_RUNTIME_TOKEN;
const registry=()=>JSON.parse(readFileSync('docs/registration-state.json','utf8'));
const save=job=>writeFileSync(`${jobsDir}/${job.id}.json`,JSON.stringify(job),{mode:0o600});
const load=id=>JSON.parse(readFileSync(`${jobsDir}/${id}.json`,'utf8'));
export async function mps(path,body){
 const response=await fetch(process.env.MPS_URL+'/api/v1'+path,{method:body?'POST':'GET',headers:{token,'content-type':'application/json'},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(30000)});
 const data=await response.json();if(!response.ok)throw new Error(`Payment service HTTP ${response.status}`);return data.data;
}
const schema={input_data:[{id:'prompt',type:'string',name:'Purchase request',data:{description:'Task text, one field per line: item, quantity, max_unit_price_eur, delivery_days, must_have (repeatable).'},validations:[{validation:'min',value:'1'},{validation:'max',value:'16000'}]}]};
const respond=(res,status,data)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(data))};
// Deal-only payment rule (CONTRACT.md): only a `deal` summary is hashed and submitted; anything else is never submitted, so escrow refunds.
export async function runPaidJob({job,payment,negotiate,mps,save,writeResult}){
 job.phase='model-pending';job.status='running';save(job);
 if(Number(payment.submitResultTime)<=Date.now()+120000)return;
 const {status,summary}=ensureVerifiedOutcome(await negotiate(job.input.prompt));
 job.result=summary;job.negotiation=status;
 if(status!=='deal'){job.status='failed';job.phase='no-result';save(job);return;}
 writeResult(job,job.result);job.resultHash=resultHash(job.result,job.nonce);job.phase='submit-pending';save(job);
 if(Number(payment.submitResultTime)<=Date.now()){job.phase='deadline-blocked';job.status='failed';save(job);return;}
 await mps('/payment/submit-result',{network:'Preprod',blockchainIdentifier:payment.blockchainIdentifier,submitResultHash:job.resultHash});
 job.phase='awaiting-result';save(job);
}
const isMain=process.argv[1]===fileURLToPath(import.meta.url);
const port=Number(process.env.AGENT_API_PORT||21950);
if(isMain)createServer(async(req,res)=>{
 try{
 const url=new URL(req.url,'http://127.0.0.1');
 if(req.method==='GET'&&url.pathname==='/availability')return respond(res,200,{status:'available',type:'masumi-agent'});
 if(req.method==='GET'&&url.pathname==='/input_schema')return respond(res,200,schema);
 if(req.method==='GET'&&url.pathname==='/status'){
 const id=url.searchParams.get('job_id');if(!/^[0-9a-f-]{36}$/.test(id||''))return respond(res,400,{error:'Invalid job_id'});
 if(!existsSync(`${jobsDir}/${id}.json`))return respond(res,404,{error:'Job not found'});
 const job=load(id);return respond(res,200,{id,status:job.status,result:['completed','failed'].includes(job.status)?job.result:undefined});
 }
 if(req.method!=='POST'||url.pathname!=='/start_job')return respond(res,404,{error:'Route not found'});
 let bytes=0,body='';for await(const part of req){bytes+=part.length;if(bytes>20000)return respond(res,413,{error:'Request too large'});body+=part}
 const input=JSON.parse(body);const nonce=input.identifier_from_purchaser??input.identifierFromPurchaser;
 if(!/^[a-fA-F0-9]{14,26}$/.test(nonce||'')||typeof input.input_data?.prompt!=='string'||!input.input_data.prompt.trim()||input.input_data.prompt.length>16000||Object.keys(input.input_data).some(k=>k!=='prompt'))return respond(res,400,{error:'Expected hex purchaser nonce and input_data.prompt'});
 const reg=registry();if(reg.registrationState!=='RegistrationConfirmed'&&reg.registration?.state!=='RegistrationConfirmed')return respond(res,503,{error:'Registration not confirmed'});
 // Persist before the payment write. Unknown outcomes require inspection, never automatic replay.
 const key=sha256(nonce);let job=readdirSync(jobsDir).filter(x=>/^[0-9a-f-]{36}\.json$/.test(x)).map(x=>load(x.replace('.json',''))).find(j=>j.nonceKey===key);
 if(job){if(job.inputHash!==inputHash(input.input_data,nonce))return respond(res,409,{error:'Nonce already used with another input'});return respond(res,job.response?200:409,job.response||{error:'Payment outcome requires inspection'});}
 const now=Date.now();const minute=60000;
 job={id:randomUUID(),nonceKey:key,nonce,input:input.input_data,inputHash:inputHash(input.input_data,nonce),status:'awaiting_payment',phase:'payment-pending'};save(job);
 const payment=await mps('/payment',{network:'Preprod',paymentSourceType:'Web3CardanoV2',supportedPaymentSourceIndex:reg.supportedPaymentSourceIndex,inputHash:job.inputHash,agentIdentifier:reg.agentIdentifier,identifierFromPurchaser:nonce,RequestedFunds:[{unit:'16a55b2a349361ff88c03788f93e1e966e5d689605d044fef722ddde0014df10745553444d',amount:'1000000'}],payByTime:new Date(now+10*minute).toISOString(),submitResultTime:new Date(now+20*minute).toISOString(),unlockTime:new Date(now+36*minute).toISOString(),externalDisputeUnlockTime:new Date(now+52*minute).toISOString()});
 job.payment=payment;job.phase='waiting-payment';job.response={id:job.id,input_hash:job.inputHash,identifierFromPurchaser:nonce,blockchainIdentifier:payment.blockchainIdentifier,agentIdentifier:reg.agentIdentifier,sellerVKey:reg.sellerVkey,paymentSourceType:'Web3CardanoV2',supportedPaymentSourceIndex:reg.supportedPaymentSourceIndex,payByTime:Number(payment.payByTime),submitResultTime:Number(payment.submitResultTime),unlockTime:Number(payment.unlockTime),externalDisputeUnlockTime:Number(payment.externalDisputeUnlockTime)};save(job);return respond(res,200,job.response);
 }catch(e){respond(res,500,{error:'Request failed. Inspect the saved job state before retrying.'})}
}).listen(port,'127.0.0.1',()=>console.log('Agent API running',port));
let busy=false;
if(isMain)setInterval(async()=>{
 if(busy)return;busy=true;
 try{for(const file of readdirSync(jobsDir).filter(x=>/^[0-9a-f-]{36}\.json$/.test(x))){
 const job=load(file.replace('.json',''));try{
 if(!['waiting-payment','awaiting-result'].includes(job.phase))continue;
 const payment=await mps('/payment/resolve-blockchain-identifier',{network:'Preprod',blockchainIdentifier:job.payment.blockchainIdentifier,includeHistory:'true'});
 if(job.phase==='awaiting-result'){if(payment.onChainState==='ResultSubmitted'&&payment.resultHash===job.resultHash&&confirmedState(payment,'ResultSubmitted')){job.phase='result-confirmed';job.status='completed';save(job)}continue;}
 if(payment.onChainState!=='FundsLocked'||!confirmedState(payment,'FundsLocked'))continue;
 if(Number(payment.submitResultTime)<=Date.now()+120000){job.phase='deadline-blocked';job.status='failed';save(job);continue;}
 await runPaidJob({job,payment,negotiate:(p)=>negotiate(p,{scenario:scenarioFrom(p)}),mps,save,writeResult:(j,t)=>writeFileSync(`${jobsDir}/${j.id}.txt`,t,{mode:0o600})});
 }catch(e){console.error('Standard job needs inspection',job.id)}
 }}finally{busy=false}
},5000);
