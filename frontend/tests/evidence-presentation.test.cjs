const{test}=require('node:test'),assert=require('assert/strict'),fs=require('fs'),path=require('path'),Module=require('module');
const root=path.resolve(__dirname,'..'),ts=require(path.join(root,'node_modules/typescript')),file=path.join(root,'src/lib/evidence-presentation.ts'),m=new Module(file,module);m.filename=file;m.paths=Module._nodeModulePaths(path.dirname(file));m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,file);const{evidenceFiles,candidateIdentity}=m.exports;
const source=(id,revision=1)=>({document_id:id,document_name:'相同名称.docx',revision,index_token:'token-'+revision,chunk_id:'chunk-'+id,text:'完整正文'});
const candidate=(id,s)=>({candidate_id:id,evidence:s,selectable:true});
test('文件分组不混合相同名称的不同文件、版本或索引，并保留原候选ID与排名',()=>{
 const rows=[candidate('a',source('one')),candidate('b',source('two')),candidate('c',{...source('one'),chunk_id:'other'}),candidate('d',source('one',2))],before=JSON.stringify(rows),groups=evidenceFiles(rows);
 assert.equal(groups.length,3);assert.deepEqual(groups[0].items.map(item=>[item.candidate.candidate_id,item.rank]),[['a',1],['c',3]]);assert.equal(JSON.stringify(rows),before);
});
test('原子证据组保持原组，不把组内成员变成独立可选项',()=>{
 const s={...source('a'),members:[source('a'),source('b')]},rows=[candidate('atomic',s)],groups=evidenceFiles(rows);assert.equal(groups[0].items.length,1);assert.equal(groups[0].items[0].candidate.evidence.members.length,2);assert.equal(groups[0].items[0].candidate.candidate_id,'atomic');
});
test('重新检索恢复选择只认相同来源快照，拒绝新版本及同名不同文件',()=>{
 const old=candidate('old',source('a')),fresh=candidate('new',source('a'));assert.equal(candidateIdentity(old),candidateIdentity(fresh));assert.notEqual(candidateIdentity(old),candidateIdentity(candidate('v2',source('a',2))));assert.notEqual(candidateIdentity(old),candidateIdentity(candidate('same-name',source('b'))));
});
