const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const root=path.resolve(__dirname,'..'),ts=require(path.join(root,'node_modules/typescript'));
const file=path.join(root,'src/lib/document-workflow.ts'),m=new Module(file,module);m.filename=file;m.paths=Module._nodeModulePaths(path.dirname(file));m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,file);
const {submissionState,matchesSubmission,needsSubmissionAction,canRetryParse,canReviewSubmission}=m.exports;
const row=(workflow={},extra={})=>({workflow:{owner:'employee',department:'研发部',status:'submitted',archived:false,deleted:false,...workflow},technical_state:'ready',technical_index_ready:true,...extra});
test('terminal states override stale parsing failures and are never an employee task',()=>{
 for(const [status,label] of [['withdrawn','已撤回'],['published','已发布'],['taken_down','已下架']]){const r=row({status},{technical_state:'failed',publication_stage:'解析异常',index_error:'old failure'});assert.equal(submissionState(r),label);assert.equal(needsSubmissionAction(r),false)}
 assert.equal(submissionState(row({status:'returned'},{technical_state:'failed'})),'已退回');
 assert.equal(needsSubmissionAction(row({archived:true},{publication_stage:'待发布'})),false);
 assert.equal(needsSubmissionAction(row({deleted:true},{index_error:'failed'})),false);
});
test('publish readiness and retryable index failure distinguish waiting from action',()=>{
 const waiting=row({}, {publication_stage:'待发布',technical_index_ready:false});assert.equal(submissionState(waiting),'处理中');assert.equal(matchesSubmission(waiting,'待发布'),false);assert.equal(needsSubmissionAction(waiting),false);
 assert.equal(needsSubmissionAction({...waiting,index_error:'索引失败'}),true);
 assert.equal(matchesSubmission({...waiting,technical_index_ready:true},'待我处理'),true);
 assert.equal(matchesSubmission(row({}, {publication_stage:'内容待审'}),'待审核'),true);
});
test('only explicit transient parse failures offer retry, not corrupt or unknown failures',()=>{
 for(const error of ['扩展名与实际文件格式不一致','文件损坏','密码保护','不支持的格式','未知错误','缺少依赖，初始化超时',''])assert.equal(canRetryParse(row({}, {technical_state:'failed',technical_error:error})),false,error);
 for(const error of ['OCR 初始化等待超时，请重试。','Connection reset','temporarily unavailable'])assert.equal(canRetryParse(row({}, {technical_state:'failed',technical_error:error})),true,error);
 assert.equal(canRetryParse(row({}, {technical_error:'timeout'})),false);
});
test('review queue excludes supervisor own risky submissions and other departments',()=>{
 const r=row({}, {publication_stage:'内容待审',review_reasons:['机密']});
 assert.equal(canReviewSubmission(r,'employee',false,true,'研发部'),false);
 assert.equal(canReviewSubmission(r,'head',false,true,'研发部'),true);
 assert.equal(canReviewSubmission(r,'head',false,true,'财务部'),false);
 assert.equal(canReviewSubmission(r,'employee',false,false,'研发部'),false);
 assert.equal(canReviewSubmission(r,'boss',true,false,'管理层'),true);
 assert.equal(canReviewSubmission({...r,workflow:{...r.workflow,archived:true}},'boss',true,false,'管理层'),false);
});
