// Keep the authoritative Task text intact; decode JSON only when it is JSON input.
export function decodeTaskInput(input){
 if(typeof input!=='string'||!input.trim()||input.length>16000)throw new Error('Input must contain 1 to 16000 characters');
 const text=input.trim();
 if(!/^[{\[]/.test(text))return {format:'TEXT',raw:input,parsed:null};
 let parsed;
 try{parsed=JSON.parse(text)}catch{throw new Error('Task JSON is malformed; send a JSON object or field-per-line text');}
 if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw new Error('Task JSON must be an object');
 return {format:'JSON',raw:input,parsed};
}
