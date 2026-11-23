const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const root=path.resolve(__dirname,'..'),ts=require(path.join(root,'node_modules/typescript')),{createElement}=require(path.join(root,'node_modules/react')),{renderToStaticMarkup}=require(path.join(root,'node_modules/react-dom/server'));
function load(file){const filename=path.join(root,'src',file),m=new Module(filename,module);m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));const native=m.require.bind(m);m.require=id=>id.endsWith('.css')?{}:id==='../lib/document-title'?load('lib/document-title.ts'):native(id);m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);return m.exports}
const {QaAnswerFirst}=load('components/QaAnswerFirst.tsx');
const render=(citations,documents=[])=>renderToStaticMarkup(createElement(QaAnswerFirst,{answer:{answer_status:'answered',answer:'核验结果 [S1] [S2] [S3]',citations},documents,examples:[],onAsk(){},onSource(){}}));
const source=(id,doc,revision=1)=>({id,document_id:doc,document_name:'资料 '+doc,chunk_id:id,index_token:'idx',revision});
test('资料卡合并同一版本多个引用，保留各引用编号并区分不同文件版本',()=>{const html=render([source('S1','a'),source('S2','a'),source('S3','a',2)]);assert.equal((html.match(/class="qa-source-title"/g)||[]).length,2);assert.match(html,/2 份/);assert.match(html,/aria-label="引用 1、2"/);assert.match(html,/aria-label="引用 3"/);assert.equal((html.match(/aria-label="查看引用 \d+"/g)||[]).length,3)});
test('资料卡不伪造发布日期、发布状态或未授权数量，文件名作为文本转义',()=>{const citation={...source('S1','a'),document_name:'<script>危险名称</script>'};let html=render([citation]);assert.ok(!html.includes('<script>'));assert.ok(!html.includes('已发布'));assert.ok(!html.includes('更新于'));assert.ok(!html.includes('无权查看'));html=render([source('S1','a')],[{id:'a',status:'archived',version:'V1.0'}]);assert.match(html,/历史版本/);assert.ok(!html.includes('已发布'))});


test('同一文档五处引用只展示一张资料卡并提供五个定位入口',()=>{
 const html=render(Array.from({length:5},(_,i)=>source('S'+(i+1),'a')));
 assert.equal((html.match(/class="qa-source-title"/g)||[]).length,1);
 assert.match(html,/1 份/);assert.match(html,/引用位置/);
 assert.equal((html.match(/aria-label="查看引用 \d+：资料 a"/g)||[]).length,5);
 assert.ok(!html.includes('qa-source-stack'));
});
