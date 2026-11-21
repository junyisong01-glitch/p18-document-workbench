const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),Module=require('module');
const root=path.resolve(__dirname,'..'),ts=require(path.join(root,'node_modules/typescript'));
const oldTs=Module._extensions['.ts'],oldTsx=Module._extensions['.tsx'],oldCss=Module._extensions['.css'];
const compile=(m,file)=>m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,file);
Module._extensions['.ts']=compile;Module._extensions['.tsx']=compile;Module._extensions['.css']=()=>{};
const {parseConfirmation,isLocalAnswerEndpoint}=require(path.join(root,'src/lib/confirmation-presentation.ts'));
const {QaConfirmation}=require(path.join(root,'src/components/QaConfirmation.tsx'));
const {answerRoute}=require(path.join(root,'src/lib/qa-answer-first.ts'));
Module._extensions['.ts']=oldTs;Module._extensions['.tsx']=oldTsx;Module._extensions['.css']=oldCss;
const React=require(path.join(root,'node_modules/react')),{renderToStaticMarkup}=require(path.join(root,'node_modules/react-dom/server'));
const make=(evidence,history=[])=>[{role:'system',content:'实际完整系统指令。'},{role:'user',content:JSON.stringify({question:'问题😀',untrusted_evidence:evidence,history_for_reference_only:history})}];
const render=(messages,extra={})=>renderToStaticMarkup(React.createElement(QaConfirmation,{pending:{messages,provider:'Ollama（本机）',request_endpoint:'http://localhost:11434/api/chat',model:'test',configured:true,...extra},consent:false,busy:false,onConsent(){},onSend(){},onCancel(){}}));
test('展示以实际消息为准，保留共享/不同成员正文、风险与未知原始字段且不修改输入',()=>{
 const text='完整正文😀\n'+'资料'.repeat(1500),other='不同成员全文。';
 const messages=make([{id:'S7',text,document_name:'原文',risk:['需要复核'],unknown:'原始保留',members:[{document_name:'共享源'},{document_name:'独立源',text:other}]}],[{question:'原问题',answer:'原回答',extra:'历史额外字段'}]);
 const before=JSON.stringify(messages),view=parseConfirmation(messages);assert.equal(view.evidence[0].text,text);assert.equal(view.evidence[0].members[1].text,other);assert.equal(view.history[0].extra,'历史额外字段');
 const html=render(messages);assert(html.includes(text));assert(html.includes(other));assert(html.includes('共享源'));assert(html.includes('需要复核'));assert(html.includes('原始保留'));assert(html.includes('历史额外字段'));assert.equal(JSON.stringify(messages),before);
});
test('空历史不显示历史区，系统规则和原始请求默认折叠',()=>{
 const html=render(make([{text:'正文'}]));assert(!html.includes('本轮携带的历史对话'));assert(!html.includes('open=""'));assert(html.includes('实际完整消息'));assert(html.includes('disabled=""'));assert(html.includes('生成回答'));
});
test('DeepSeek显示实际域名、明确外发同意与确认发送，不误标本机',()=>{
 const html=render(make([{text:'正文'}]),{provider:'DeepSeek',request_endpoint:'https://api.deepseek.com/chat/completions',model:'deepseek-flash'});
 assert(html.includes('api.deepseek.com'));assert(html.includes('同意本轮发送至 DeepSeek'));assert(html.includes('确认发送'));assert(!html.includes('资料不外发'));
 assert.equal(isLocalAnswerEndpoint('http://localhost.evil:11434/api/chat'),false);assert.equal(isLocalAnswerEndpoint('https://api.deepseek.com/chat/completions'),false);
});
test('不认识的消息结构自动展开完整请求，不编造结构化证据',()=>{
 const messages=[{role:'system',content:'规则'},{role:'user',content:'不是JSON的原始消息'}];assert.equal(parseConfirmation(messages),null);const html=render(messages);assert(html.includes('open=""'));assert(html.includes('不是JSON的原始消息'));assert(html.includes('无法转换为分组视图'));
});
test('资料和系统指令中的HTML只作文本显示，模型未配置时不能勾选或发送',()=>{
 const html=render(make([{text:'<script>danger()</script>',document_name:'<img onerror="danger()">'}]),{configured:false});assert(!html.includes('<script>danger'));assert(html.includes('&lt;script&gt;danger()'));assert(html.includes('模型尚不可用'));assert((html.match(/disabled=""/g)||[]).length>=2);
});
test('云访问明确表示部署环境私有模型，不声称资料在访客电脑上推理',()=>{
 const messages=make([{text:'公开虚构资料'}]),before=JSON.stringify(messages);
 const html=renderToStaticMarkup(React.createElement(QaConfirmation,{privateDeployment:true,pending:{messages,provider:'Ollama',request_endpoint:'http://localhost:11434/api/chat',model:'test',configured:true},consent:false,busy:false,onConsent(){},onSend(){},onCancel(){}}));
 assert(html.includes('私有模型处理'));assert(html.includes('当前部署环境'));assert(!html.includes('这台电脑'));assert(!html.includes('同意在本机'));assert.equal(JSON.stringify(messages),before);
});

test('one-click QA can send only to an explicit Ollama loopback endpoint',()=>{
 const local={provider:'Ollama（本机）',request_endpoint:'http://localhost:11434/api/chat'};
 assert.equal(answerRoute(local),'local');
 assert.equal(answerRoute({...local,request_endpoint:'http://127.0.0.1:11434/api/chat'}),'local');
 assert.equal(answerRoute({...local,request_endpoint:'https://localhost.evil.test/api/chat'}),'unavailable');
 assert.equal(answerRoute({...local,provider:'DeepSeek'}),'unavailable');
 const external={request_endpoint:'https://api.deepseek.com/chat/completions',messages:[{role:'user',content:'问题'}]};
 assert.equal(answerRoute(external),'confirm_external');
 assert.equal(answerRoute({...external,messages:[{role:'system',content:'unexpected'},...external.messages]}),'unavailable');
});
