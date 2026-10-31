import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mockProcurementResult,isMockMode} from './mock-agent.mjs';

test('mock procurement result preserves the request and makes no real-world claims',()=>{
 const request=JSON.stringify({product:'Demo item',quantity:3,maximum_unit_price:'20.00 EUR',maximum_total_price:'60.00 EUR',delivery_deadline:'2026-10-31',mandatory_commercial_terms:['Invoice required']});
 const result=JSON.parse(mockProcurementResult(request));
 assert.equal(result.result_type,'MOCK_PROCUREMENT_SIMULATION');
 assert.equal(result.status,'PROCESSED');
 assert.equal(result.buyer_request.raw,request);
 assert.deepEqual(result.buyer_request.parsed,JSON.parse(request));
 assert.equal(result.supplier_response_fixture.status,'NOT_CONTACTED');
 assert.equal(result.commercial_outcome.quote,null);
 assert.equal(result.commercial_outcome.supplier_confirmation,null);
 assert.equal(result.payment.status,'NOT_PERFORMED');
 assert.equal(result.payment.cardano_transaction_hash,null);
});

test('mock procurement result accepts plain text and rejects empty or oversized input',()=>{
 const result=JSON.parse(mockProcurementResult('Request: source two replacement sensors.'));
 assert.equal(result.buyer_request.format,'TEXT');
 assert.equal(result.buyer_request.raw,'Request: source two replacement sensors.');
 assert.throws(()=>mockProcurementResult('  '),/Input must contain/);
 assert.throws(()=>mockProcurementResult('x'.repeat(16001)),/Input must contain/);
});

test('mock mode is explicit and mock result follows the no-deal boundary',()=>{
 assert.equal(isMockMode({MOCK_AGENT:'true'}),true);
 assert.equal(isMockMode({MOCK_AGENT:'false'}),false);
 const result=JSON.parse(mockProcurementResult('{"item":"Demo item"}'));
 assert.equal(result.summary_markdown.includes('MOCK/SIMULATION ONLY'),true);
 assert.equal(result.status,'PROCESSED');
 assert.equal(result.quote,null);
 assert.deepEqual(result.checks,[]);
 assert.deepEqual(result.transcript,[]);
});

test('mock preserves exact JSON bytes and rejects malformed JSON rather than treating it as text',()=>{
 const input=' \n{"product":"USB-C scanner","quantity":2}\n ';
 const {buyer_request}=JSON.parse(mockProcurementResult(input));
 assert.equal(buyer_request.raw,input);
 assert.deepEqual(buyer_request.parsed,{product:'USB-C scanner',quantity:2});
 for(const input of ['{bad json','[]'])assert.throws(()=>mockProcurementResult(input),/JSON/);
});
