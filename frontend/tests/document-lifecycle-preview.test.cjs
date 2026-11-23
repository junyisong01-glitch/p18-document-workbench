const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const root=path.resolve(__dirname,'..'),ts=require(path.join(root,'node_modules/typescript')),filename=path.join(root,'src/lib/document-lifecycle-preview.ts'),m=new Module(filename,module);
m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,filename);
const {previewDocumentLifecycle:preview}=m.exports;
test('仅隔离页的无流转记录历史资料生成稳定演示记录，人员匹配部门且时间有序',()=>{
 const first=preview('QC-HR-001','人力资源部',true,undefined,true);
 assert(first.simulated);assert.deepEqual(first,preview('QC-HR-001','人力资源部',true,undefined,true));
 assert.equal(first.facts.submitted.actor,'qichen_hr');assert.equal(first.facts.reviewed.actor,'qichen_hr_head');
 assert(first.facts.submitted.at<first.facts.reviewed.at);assert(first.facts.reviewed.at<first.facts.published.at);
 assert.equal(preview('x','研发部',true,undefined,false).simulated,false);
 assert.equal(preview('x','研发部',false,undefined,true).simulated,false);
});
test('真实或部分真实记录原样保留，不补造缺失审核或发布记录',()=>{
 for(const field of ['submitted','reviewed','published']){
 const actual={[field]:{actor:'real-user',at:123}};
 const result=preview('x','研发部',true,actual,true);assert.equal(result.facts,actual);assert.equal(result.simulated,false);
 }
});
