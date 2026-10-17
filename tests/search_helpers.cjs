const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const window={};vm.runInNewContext(fs.readFileSync('web/search.js','utf8'),{window});
const {sourcePage,indexLabel,hitIsCurrent}=window.P18Search;
assert.equal(indexLabel({status:'complete',searchable:false}),'索引已失效');
assert.equal(indexLabel({status:'building',searchable:false}),'正在构建');
assert.equal(sourcePage({}, {ext:'.pdf'}, {page:2}),2);
assert.equal(sourcePage({}, {ext:'.pdf'}, {page:0}),null);
assert.equal(sourcePage({}, {ext:'.docx'}, {page:2}),null); // Word paragraph positions are not PDF pages.
assert.equal(sourcePage({}, {ext:'.docx'}, {preview_pages:{original:3}}),3);
assert.equal(sourcePage({}, {ext:'.docx',result:{blocks:[{id:'p1',preview_pages:{original:4}}]}}, {block_id:'p1'}),4);
const hit={document_id:'d1',revision:2,index_token:'current'};
const docs=[{id:'d1',revision:2,index:{status:'complete',searchable:true,token:'current'}}];
assert.equal(hitIsCurrent(hit,docs),true);
assert.equal(hitIsCurrent({...hit,index_token:'old'},docs),false);
assert.equal(hitIsCurrent({...hit,revision:1},docs),false);
assert.equal(hitIsCurrent(hit,[]),false);
console.log('11 retrieval status/source/version assertions passed');
// Controller error-state test: no network or fabricated embedding response.
const elements=new Map();
const element=selector=>{
 if(!elements.has(selector))elements.set(selector,{value:'',innerHTML:'',textContent:'',hidden:false,disabled:false,addEventListener(){},setAttribute(){}});
 return elements.get(selector);
};
const secondWindow={};vm.runInNewContext(fs.readFileSync('web/search.js','utf8'),{window:secondWindow,document:{querySelector:element}});
const controller=secondWindow.P18Search.create({api(){throw new Error('unexpected network');},esc:String,onShow(){}});
controller.offline('本地服务暂时无法连接');
assert.equal(element('#semantic-submit').disabled,true);
assert.equal(element('#semantic-results').innerHTML,'');
assert.match(element('#semantic-preview-content').innerHTML,/原文预览将在此显示/);
console.log('3 offline controller assertions passed');
