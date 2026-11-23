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

test('three submission groups distinguish employee work from waiting for review',()=>{
 const {submissionGroup,submissionLabel,submissionDate}=m.exports;
 const review=row({}, {technical_state:'review',publication_stage:'解析异常'});
 assert.equal(submissionGroup(review,false),'处理中');assert.equal(submissionGroup(review,true),'需要处理');
 assert.equal(submissionLabel(review,false).label,'等待解析核对');
 assert.equal(submissionGroup(row({}, {publication_stage:'内容待审'}),false),'处理中');
 assert.equal(submissionGroup(row({}, {technical_state:'failed'}),false),'需要处理');
 for(const status of ['published','withdrawn','taken_down'])assert.equal(submissionGroup(row({status},{technical_state:'failed'}),false),'提交记录');
 assert.equal(submissionLabel(row({status:'published'},{technical_index_ready:false}),false).label,'已发布 · 暂不可检索');
 assert.equal(submissionDate(''),'提交时间未记录');assert.match(submissionDate('2026-11-22T16:30:00Z'),/2026\/11\/23 00:30/);
});


test('automatic publication is waiting, not an employee confirmation task',()=>{
 const {submissionGroup,submissionLabel}=m.exports;
 const auto=row({}, {publication_stage:'自动发布中'});
 assert.equal(submissionState(auto),'处理中');assert.equal(needsSubmissionAction(auto),false);
 assert.equal(submissionGroup(auto,false),'处理中');assert.equal(submissionLabel(auto,false).label,'正在自动发布');
 assert.equal(needsSubmissionAction({...auto,index_error:'索引失败'}),true);
 const blocked={...auto,workflow:{...auto.workflow,auto_publish_error:'原资料已变化'}};
 assert.equal(needsSubmissionAction(blocked),true);assert.equal(submissionLabel(blocked,false).label,'发布需要处理');
});

const {submissionProgress}=m.exports;
test('submission progress follows automatic publication without inventing content approval',()=>{
 const steps=submissionProgress(row({}, {publication_stage:'自动发布中',technical_index_ready:false}));
 assert.deepEqual(steps.map(s=>s.label),['已提交','解析检查','索引准备','自动发布']);
 assert.equal(steps[2].state,'current');assert.equal(steps[3].state,'waiting');
 const publishing=submissionProgress(row({}, {publication_stage:'自动发布中',technical_index_ready:true}));assert.equal(publishing.at(-1).state,'current');
 const corrected=submissionProgress(row({status:'published',correction:true}));assert.equal(corrected.at(-1).label,'已生效');assert.equal(corrected.at(-1).state,'done');
 const complete=submissionProgress(row({status:'published'}));assert.equal(complete.at(-1).label,'已发布');assert.equal(complete.at(-1).state,'done');
 const noIndex=submissionProgress(row({status:'published'},{technical_index_ready:false}));assert.equal(noIndex.at(-2).state,'error');assert.equal(noIndex.at(-1).state,'done');
});
test('submission progress distinguishes review, failures, stopped states and corrections',()=>{
 const review=submissionProgress(row({}, {publication_stage:'内容待审',review_reasons:['机密']}));assert.equal(review[2].label,'等待内容审核');assert.equal(review[2].state,'current');assert.equal(review[3].state,'waiting');
 const failed=submissionProgress(row({}, {technical_state:'failed'}));assert.equal(failed[1].label,'解析失败');assert.equal(failed[1].state,'error');
 for(const status of ['withdrawn','returned','taken_down']){const steps=submissionProgress(row({status},{technical_state:'failed'}));assert.equal(steps.length,2);assert.notEqual(steps[1].state,'done')}
 const correction=submissionProgress(row({correction:true,approved_by:'declarant'}, {publication_stage:'勘误处理中'}));assert(!correction.some(s=>s.label.includes('审核')));assert.equal(correction.at(-1).label,'正在自动生效');
 const approved=submissionProgress(row({status:'approved'},{publication_stage:'待发布',technical_index_ready:false}));assert.equal(approved[2].state,'done');assert.equal(approved[3].state,'current');
});
