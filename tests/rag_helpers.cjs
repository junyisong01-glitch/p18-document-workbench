const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const nodes=new Map();const $=id=>{if(!nodes.has(id))nodes.set(id,{value:'',innerHTML:'',textContent:'',disabled:false,checked:false,open:false,classList:{remove(){},add(){}},addEventListener(){},focus(){},close(){this.open=false},showModal(){this.open=true}});return nodes.get(id)};
const context={window:{},document:{querySelector:$,activeElement:{focus(){}}},console};vm.runInNewContext(fs.readFileSync('web/rag.js','utf8'),context);
(async()=>{
 const requests=[];const ui=context.window.P18Rag.create({api:async(path)=>{requests.push(path);return path==='/api/rag'?{provider:'DeepSeek',configured:false,notice:'未配置'}:{status:'no_evidence',message:'未调用模型',session_id:'test'}},esc:s=>String(s),onShow(){}});
 assert.equal(requests.length,0);ui.show();await new Promise(r=>setImmediate(r));assert.deepEqual(requests,['/api/rag']);
 $('#rag-question').value='负责人是谁？';await $('#rag-form').onsubmit({preventDefault(){}});
 assert.equal(requests.at(-1),'/api/rag/prepare');assert.equal(requests.includes('/api/rag/answer'),false);assert.equal($('#rag-consent').innerHTML,'');
 $('#rag-clear').onclick();assert.equal($('#rag-chat').innerHTML,'');
 console.log('6 RAG UI no-auto-send/session assertions passed');
})();
