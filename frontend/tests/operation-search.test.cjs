const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const root=path.resolve(__dirname,'..'),ts=require(path.join(root,'node_modules/typescript'));
function load(file){const filename=path.join(root,'src/lib',file),m=new Module(filename,module);m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));const native=m.require.bind(m);m.require=id=>id==='./demo-identity-names'?load('demo-identity-names.ts'):native(id);m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,filename);return m.exports}
const {operationSearchParams:query,emptyOperationFilters:empty}=load('operation-search.ts');
test('operation filters map Chinese display names and combine filename with full Beijing date',()=>{
 const p=new URLSearchParams(query({...empty,actor:' 陈叙 ',document:' 技术方案 ',mode:'date',date:'2026-11-23'}));
 assert.equal(p.get('actor_accounts'),'qichen_rd');assert.equal(p.get('document'),'技术方案');
 assert.equal(Number(p.get('start_at')),Date.parse('2026-11-22T16:00:00Z')/1000);
 assert.equal(Number(p.get('end_at')),Date.parse('2026-11-23T16:00:00Z')/1000);
 assert.equal(query(empty),'');
});
test('custom time ranges include final minute and reject missing or reversed dates',()=>{
 const p=new URLSearchParams(query({...empty,mode:'range',start:'2026-11-22T23:30',end:'2026-11-23T01:15'}));
 assert.equal(Number(p.get('end_at'))-Number(p.get('start_at')),106*60);
 assert.throws(()=>query({...empty,mode:'date'}),/查询日期/);
 assert.throws(()=>query({...empty,mode:'range'}),/开始和结束/);
 assert.throws(()=>query({...empty,mode:'range',start:'2026-11-23T02:00',end:'2026-11-23T01:00'}),/不能早于/);
});
