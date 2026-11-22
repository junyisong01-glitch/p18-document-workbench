const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const root=path.resolve(__dirname,'..'),ts=require(path.join(root,'node_modules/typescript')),{createElement}=require(path.join(root,'node_modules/react')),{renderToStaticMarkup}=require(path.join(root,'node_modules/react-dom/server'));
function load(file){const filename=path.join(root,'src',file),m=new Module(filename,module);m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));const native=m.require.bind(m);m.require=id=>id==='@/lib/api'?{api:{}}:id==='@/lib/session'?{useSession:()=>({})}:id==='@/lib/source-presentation'?load('lib/source-presentation.ts'):id.endsWith('.css')?{}:id==='./SourceContent'?load('components/SourceContent.tsx'):id==='./ExcelPreview'?load('components/ExcelPreview.tsx'):native(id);m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,filename);return m.exports}
const {MatchedSearchContent}=load('components/SearchEvidence.tsx');const render=(source,blocks=[])=>renderToStaticMarkup(createElement(MatchedSearchContent,{source,blocks}));
test('列表只使用命中表格，不将整份文档的未命中行补入结果',()=>{const html=render({text:'列\n命中值',tables:[{rows:[['列'],['命中值']]}]},[{id:'full',kind:'table',text:'全部原文',tables:[{rows:[['列'],['命中值'],['未命中机密行']]}]}]);assert.match(html,/<table/);assert.match(html,/命中值/);assert.ok(!html.includes('未命中机密行'));assert.match(html,/tabindex="0"/)});
test('表格前正文只按Unicode来源区间截取，不混入前后未命中段落',()=>{const html=render({text:'😀乙\n列\n值',section:'章节',sources:[{block_id:'p',raw_start:1,raw_end:3}],tables:[{rows:[['列'],['值']]}]},[{id:'p',kind:'paragraph',text:'甲😀乙尾'},{id:'unmatched',kind:'paragraph',text:'未命中的后文'}]);assert.match(html,/😀乙/);assert.ok(!html.includes('甲'));assert.ok(!html.includes('尾'));assert.ok(!html.includes('未命中的后文'))});
test('普通段落里的空格和制表符不被猜成表格，也不执行原文HTML',()=>{const html=render({text:'甲  乙\t丙\n\n<script>原文</script>'});assert.ok(!html.includes('<table'));assert.match(html,/甲  乙\t丙/);assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/)});
test('命中表格保留跨行跨列与空值，合并区只渲染一次',()=>{const html=render({text:'原文',tables:[{rows:[['跨列',null],['跨行','B'],[null,'C']],cells:[{row:1,column:1,colspan:2,text:'跨列'},{row:2,column:1,rowspan:2,text:'跨行'},{row:2,column:2,text:'B'},{row:3,column:2,text:'C'}]}]});assert.match(html,/colSpan="2"/);assert.match(html,/rowSpan="2"/);assert.equal((html.match(/>跨行</g)||[]).length,1);assert.equal((html.match(/>跨列</g)||[]).length,1)});

const {ExcelCitationEvidence}=load('components/ExcelPreview.tsx');
test('Excel 引用按命中行展示字段和时间，保留精度并排除未命中记录',()=>{
  const cells=(row,id,time)=>[{coordinate:'A'+row,text:id},{coordinate:'B'+row,text:time}];
  const table={id:'ledger',header_confirmed:true,headers:['工单编号','转单时间'],rows:[
    {row:5,cells:cells(5,'工单甲','2026-11-18T08:50:00')},
    {row:6,cells:cells(6,'工单乙','2026-11-18T10:22:05')},
    {row:7,cells:cells(7,'未命中工单','2026-11-18T11:32:00')},
  ],summary_rows:[]};
  const blocks=table.rows.map(({row})=>({id:'record-'+row,table_id:table.id,sheet:'工单台账',row_start:row}));
  const locations=blocks.slice(0,2).map(block=>({block_id:block.id,sheet:block.sheet,row_start:block.row_start,row_end:block.row_start}));
  const renderRows=(sheets,refs)=>renderToStaticMarkup(createElement(ExcelCitationEvidence,{
    sheets,locations:refs,blocks,fallback:createElement('p',null,'检索原始文本'),
  }));
  const sheets=[{name:'工单台账',tables:[table]}];
  const html=renderRows(sheets,locations);
  assert.match(html,/第 5 行.*工单甲.*2026-11-18 08:50<.*第 6 行.*工单乙.*2026-11-18 10:22:05/);
  assert.equal((html.match(/<dt>工单编号<\/dt>/g)||[]).length,2);
  assert.doesNotMatch(html,/未命中工单|检索原始文本/);
  assert.equal(renderRows(sheets,[{...locations[0],row_start:7,row_end:7}]),'<p>检索原始文本</p>');
  assert.equal(renderRows([{name:'工单台账',tables:[{...table,header_confirmed:false}]}],locations),'<p>检索原始文本</p>');
});
