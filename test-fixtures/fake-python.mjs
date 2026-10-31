#!/usr/bin/env node
import {writeFileSync,readFileSync} from 'node:fs';
import {verifiedDeal} from './verified-result.mjs';
const args=process.argv.slice(2),out=args[args.indexOf('--out')+1],mode=process.env.FAKE_NEGOTIATOR;
const quote={supplier:'Supplier B',unit_price_eur:4.75,quantity:2000,total_eur:9500};
if(mode==='crash'){console.error('Traceback: boom');process.exit(1);}
if(mode==='hang')setTimeout(()=>{},60000);
else if(mode==='malformed')writeFileSync(out,'{not json');
else if(mode==='unknown')writeFileSync(out,JSON.stringify({status:'maybe',summary_markdown:'x'}));
else writeFileSync(out,JSON.stringify({status:mode,quote:mode==='deal'?quote:null,checks:mode==='deal'?verifiedDeal().result.checks:[],summary_markdown:`${mode} summary`,args,cwd:process.cwd(),raw_request:readFileSync(args[args.indexOf('--request-file')+1],'utf8')}));
