import {decodeTaskInput} from './task-input.mjs';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

export function mockProcurementResult(input) {
 const buyerRequest=decodeTaskInput(input);
 return JSON.stringify({
  result_type:'MOCK_PROCUREMENT_SIMULATION',
  status:'PROCESSED',
  summary_markdown:'**MOCK/SIMULATION ONLY.** The buyer request was received and preserved. No real negotiation took place; no supplier was contacted or confirmed an offer, and no payment occurred.',
  quote:null,
  checks:[],
  transcript:[],
  request_interpretation:'The buyer request was received and preserved. No offer or price was generated.',
  buyer_request:buyerRequest,
  supplier_response_fixture:{kind:'LOCAL_FIXTURE',status:'NOT_CONTACTED',message:'No supplier was contacted. This fixture does not represent supplier availability, a quote, or confirmation.'},
  commercial_outcome:{status:'NO_DEAL_MOCK_ONLY',quote:null,supplier_confirmation:null},
  payment:{status:'NOT_PERFORMED',negotiation_service_fee:null,goods_invoice:null,cardano_transaction_hash:null},
  limitations:['Simulation only; no real negotiation took place.','No supplier confirmed an offer.','No goods delivery, invoice, escrow, or payment was verified.']
 },null,2);
}

export function isMockMode(env=process.env){return env.MOCK_AGENT?.trim().toLowerCase()==='true';}

function runCli(args=process.argv.slice(2)) {
 if(args.length!==2||args[0]!=='--input-file')throw new Error('Usage: npm run mock -- --input-file mock-procurement-request.json');
 const input=readFileSync(resolve(process.cwd(),args[1]),'utf8');
 process.stdout.write(`${mockProcurementResult(input)}\n`);
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 try{runCli()}catch(error){console.error(`Mock agent error: ${error.message}`);process.exitCode=1;}
}
