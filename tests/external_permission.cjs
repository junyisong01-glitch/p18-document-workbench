const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();let inputs=[],radio=null,domReady,requests=[],nextError=false;
function element(id){if(!elements.has(id))elements.set(id,{id,disabled:false,checked:false,textContent:'',handlers:{},open:false,
 addEventListener(n,fn){this.handlers[n]=fn;},showModal(){this.open=true;},close(){this.open=false;},focus(){this.focused=true;},
 querySelector(){return radio;},querySelectorAll(){return inputs;}});return elements.get(id);}
const document={querySelector:s=>element(s),addEventListener(n,fn){if(n==='DOMContentLoaded')domReady=fn;}};
const window={};let doc={id:'fictional-id',name:'虚构测试.pdf',revision:3,external_permission:{revision:3,fingerprint:'a'.repeat(64),can_review:true,allowed:false}};
const fetch=async(url,options)=>{requests.push({url,options});if(nextError)return {ok:false,json:async()=>({detail:{message:'版本已变化'}})};
 doc.external_permission.allowed=!url.endsWith('/revoke');return {ok:true,json:async()=>doc.external_permission};};
vm.runInNewContext(fs.readFileSync('web/external-permission.js','utf8'),{document,window,fetch,Object,Error});domReady();
const el=id=>element('#'+id);let refreshed=0;
const refresh=async()=>{refreshed++;window.P18ExternalPermission.render(doc,refresh);};
(async()=>{
 window.P18ExternalPermission.render(doc,refresh);assert(!el('external-review').disabled);assert(el('external-revoke').disabled);
 el('external-review').onclick();assert(el('external-review-dialog').open);assert(el('external-confirm').disabled);
 radio={value:'public_verified'};inputs=[radio,...['no_sensitive_content','third_party_terms_checked','no_restricted_content'].map(k=>el('external-'+k))];
 inputs[1].checked=inputs[2].checked=true;el('external-review-dialog').handlers.change();assert(el('external-confirm').disabled);
 inputs[3].checked=true;el('external-review-dialog').handlers.change();assert(!el('external-confirm').disabled);assert.equal(requests.length,0);
 await el('external-confirm').onclick();assert.equal(requests.length,1);assert.equal(refreshed,1);assert(el('external-success-dialog').open);
 let sent=JSON.parse(requests[0].options.body);assert.equal(sent.revision,3);assert.equal(sent.classification,'public_verified');
 assert.deepEqual(Object.values(sent.checks),[true,true,true]);assert.equal(sent.fingerprint,'a'.repeat(64));assert(!('text' in sent));assert(!('reviewer' in sent));
 assert.equal(requests[0].options.headers['X-P18-Client'],'workbench');assert(!el('external-review').disabled);assert(!el('external-revoke').disabled);
 el('external-success-ok').onclick();assert(!el('external-success-dialog').open);assert(el('external-review').focused);
 await el('external-revoke').onclick();assert.equal(requests.length,2);assert(requests[1].url.endsWith('/revoke'));assert(el('external-revoke').disabled);
 assert(!el('external-review').disabled);assert(el('external-inline-status').textContent.includes('已撤销'));
 el('external-review').onclick();assert(inputs.every(i=>i.checked===false));assert(el('external-confirm').disabled);el('external-cancel').onclick();assert(!el('external-review-dialog').open);
 doc.external_permission.can_review=false;window.P18ExternalPermission.render(doc,refresh);assert(el('external-review').disabled);
 console.log('外发权限前端：30项状态/请求/撤销/取消断言通过');
})().catch(e=>{console.error(e);process.exitCode=1;});
