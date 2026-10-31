import test from 'node:test';
import assert from 'node:assert/strict';
import {startJobBody} from './examples/hire-from-agent.mjs';
test('start_job body has the MIP-003 shape and a 16-hex nonce',()=>{
 const b=startJobBody('item: x');
 assert.deepEqual(Object.keys(b),['identifier_from_purchaser','input_data']);
 assert.match(b.identifier_from_purchaser,/^[0-9a-f]{16}$/);
 assert.deepEqual(b.input_data,{prompt:'item: x'});
 assert.notEqual(b.identifier_from_purchaser,startJobBody('x').identifier_from_purchaser);
});
