const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const root=path.resolve(__dirname,'..'),ts=require(path.join(root,'node_modules/typescript')),React=require(path.join(root,'node_modules/react')),{renderToStaticMarkup}=require(path.join(root,'node_modules/react-dom/server'));
const file=path.join(root,'src/components/BusinessPresentation.tsx'),m=new Module(file,module);m.filename=file;m.paths=Module._nodeModulePaths(path.dirname(file));m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);const {WorkflowBadge,WorkflowTimeline}=m.exports;
const row=(workflow={},technical={})=>({workflow:{status:'published',archived:false,deleted:false,...workflow},technical_state:'ready',technical_index_ready:true,...technical});
test('发布件无有效索引不能显示可检索，历史和回收站不显示绿色现行资格',()=>{for(const r of[row({}, {technical_index_ready:false}),row({archived:true}),row({deleted:true})]){const html=renderToStaticMarkup(React.createElement(WorkflowBadge,{row:r}));assert.ok(!html.includes('可检索'))}});
test('待审核资料即使已有技术索引也不显示已发布；待发布区分索引是否就绪',()=>{let html=renderToStaticMarkup(React.createElement(WorkflowBadge,{row:row({status:'submitted'})}));assert.match(html,/待业务审核/);assert.ok(!html.includes('已发布'));html=renderToStaticMarkup(React.createElement(WorkflowBadge,{row:row({status:'approved'},{technical_index_ready:false})}));assert.match(html,/索引准备/);assert.ok(!html.includes('索引就绪'))});
test('勘误时间线独立展示免业务审批和旧版继续生效，不伪造审核节点',()=>{const html=renderToStaticMarkup(React.createElement(WorkflowTimeline,{row:row({status:'correction_pending',correction:true},{technical_index_ready:false})}));assert.match(html,/勘误免业务审批/);assert.match(html,/旧版本继续提供检索/);assert.ok(!html.includes('>业务审核<'))});

const af=path.join(root,'src/components/AnswerPresentation.tsx'),am=new Module(af,module);
am.filename=af;
am.paths=Module._nodeModulePaths(path.dirname(af));
const originalTs=Module._extensions['.ts'];
try {
 Module._extensions['.ts']=(unit,source)=>unit._compile(ts.transpileModule(fs.readFileSync(source,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,source);
 am._compile(ts.transpileModule(fs.readFileSync(af,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,af);
} finally {
 if(originalTs) Module._extensions['.ts']=originalTs;
 else delete Module._extensions['.ts'];
}
test('insufficient evidence has no invented citations; answer and source names are escaped',()=>{let html=renderToStaticMarkup(React.createElement(am.exports.AnswerPresentation,{answer:{answer_status:'insufficient_evidence',answer:'No evidence <script>unsafe</script>',citations:[]},onSource:()=>{}}));assert.equal((html.match(/<button/g)||[]).length,0);assert.ok(!html.includes('<script>'));html=renderToStaticMarkup(React.createElement(am.exports.AnswerPresentation,{answer:{answer_status:'answered',answer:'Fictional answer',citations:[{id:'S1',document_name:'Fictional source'}]},onSource:()=>{}}));assert.equal((html.match(/<button/g)||[]).length,1);assert.match(html,/S1/);assert.match(html,/Fictional source/)});

test('回答引用显示简洁标题和 EXT 编号，悬停保留原文件名',()=>{
 const html=renderToStaticMarkup(React.createElement(am.exports.AnswerPresentation,{answer:{answer_status:'answered',answer:'示例',citations:[{id:'S1',document_name:'EXT-14 V1.3.1版本发布说明（最终修正版）.docx'}]},onSource(){}}));
 assert.match(html,/title="EXT-14 V1\.3\.1版本发布说明（最终修正版）\.docx"/);
 assert.match(html,/\[S1\] V1\.3\.1 版本发布说明<span[^>]*>EXT-14<\/span>/);
});
