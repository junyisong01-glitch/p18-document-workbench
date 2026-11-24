import {RequestSupport,MyAccessRequests,useAccessRequests} from '@/components/AccessRequests'
import {useSearchParams,Link} from 'react-router'
import {RecordFeedback,type FeedbackTurn} from '@/components/QuestionFeedback'
import {useCallback,useEffect,useRef,useState} from 'react'
import {Cpu,Flag,Check} from 'lucide-react'
import {ModelConfigDialog} from '@/components/ModelConfigDialog'
import {loadModelConfig,type ModelConfigStatus} from '@/lib/modelConfig'
import {QaWorkspace,QaChatTurn} from '@/components/QaWorkspace'
import {DocPreviewDialog} from '@/components/DocView'
import {QaAnswerActions} from '@/components/QaAnswerActions'
import {AnswerPresentation} from '@/components/AnswerPresentation'
import {QaAnswerFirst, QaAnswerLoading, QaNoEvidence, citationLocations, type QaCitation, type QaResult} from '@/components/QaAnswerFirst'
import {answerRoute} from '@/lib/qa-answer-first'
import {QaConfirmation} from '@/components/QaConfirmation'
import {QaModelRoute} from '@/components/QaModelRoute'
import {ExternalModelAdmin} from '@/components/ExternalModelAdmin'
import {EvidenceStack} from '@/components/EvidenceStack'
import {candidateIdentity} from '@/lib/evidence-presentation'
import {qaExamples} from '@/lib/qa-examples'
import {api, ApiError} from '@/lib/api'
import {useKnowledgeBase,useSession} from '@/lib/session'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {documentTitleParts} from '@/lib/document-title'
const button='inline-flex items-center justify-center gap-2 rounded-md border border-border bg-card px-4 py-2.5 text-xs font-medium transition-colors hover:border-[hsl(12_74%_42%/0.5)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] disabled:cursor-not-allowed disabled:opacity-45'
type Turn = {
 question:string
 answer:QaResult|null
 empty:boolean
 error:string
 notice:string
 feedbackContextId?:string
}
type Conversation = { id:string; title:string; turns:Turn[] }

export default function QaPage(){
 const {kbId,visibleDocs,searchableDocs,ready,user,refresh}=useSession()
 const [params]=useSearchParams()
 const requests=useAccessRequests(kbId==='business'&&!!user&&user.accessRole!=='guest')
 const [requestQuestion,setRequestQuestion]=useState<string|null>(null)
 const [requestSaved,setRequestSaved]=useState(false)
 useEffect(()=>{if(!requestSaved)return;const timer=setTimeout(()=>setRequestSaved(false),5000);return()=>clearTimeout(timer)},[requestSaved])
 const [feedbackTurn,setFeedbackTurn]=useState<FeedbackTurn|null>(null),[feedbackSaved,setFeedbackSaved]=useState(false)
 const [feedbackContextId,setFeedbackContextId]=useState<string|undefined>()
 const [reported,setReported]=useState<string[]>([])
 const kb=useKnowledgeBase()
 const questionInput=useRef<HTMLTextAreaElement>(null)
 const turnAnchor=useRef<HTMLElement>(null)
 const [conversations,setConversations]=useState<Conversation[]>([])
 const [active,setActive]=useState<string|null>(null)
 const nextConversation=useRef(0)
 const backendSessions=useRef(new Map<string,string>())
 const [routeError,setRouteError]=useState(false)
 const [routeAttempt,setRouteAttempt]=useState(0)
 const [askedQuestion,setAskedQuestion]=useState('')
 const [phase,setPhase]=useState<'search'|'answer'|null>(null)
 const [empty,setEmpty]=useState(false)
 const [answerNotice,setAnswerNotice]=useState('')
 const examples=ready?qaExamples(kbId,searchableDocs):[]
 const [route,setRoute]=useState<any>(null),[fallbackConsent,setFallbackConsent]=useState(false)
 useEffect(()=>{let mounted=true;setRoute(null);setRouteError(false);setFallbackConsent(false);api.get<any>('/api/rag').then(r=>{if(mounted)setRoute(r)}).catch(()=>{if(mounted)setRouteError(true)});return()=>{mounted=false}},[kbId,routeAttempt])
 const [modelConfig,setModelConfig]=useState<ModelConfigStatus|null>(null),[configOpen,setConfigOpen]=useState(false),[configLoading,setConfigLoading]=useState(false),[configError,setConfigError]=useState('')
 const closeConfig=useCallback(()=>setConfigOpen(false),[])
 useEffect(()=>{let active=true;setConfigOpen(false);setModelConfig(null);setConfigError('');setConfigLoading(kbId==='demo');if(kbId==='demo')loadModelConfig().then(value=>{if(active)setModelConfig(value)}).catch(()=>{if(active)setConfigError('无法读取当前模型配置，可打开配置窗口重试；本地检索不受影响。')}).finally(()=>{if(active)setConfigLoading(false)});return()=>{active=false}},[kbId])
 const [question,setQuestion]=useState(''),[draft,setDraft]=useState<any>(null),[selected,setSelected]=useState<string[]>([]),[version,setVersion]=useState(0),[pending,setPending]=useState<any>(null),[consent,setConsent]=useState(false),[answer,setAnswer]=useState<QaResult|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 const [preview,setPreview]=useState<{locations:QaCitation[];index:number;visit:number}|null>(null)
 const activeSource=preview?.locations[preview.index]
 const previewDoc=activeSource&&visibleDocs.find(doc=>doc.id===activeSource.document_id)
 const [dockPreview,setDockPreview]=useState(false)
 const syncQaWidth=useCallback((width:number)=>setDockPreview(width>=1100),[])
 const previewTrigger=useRef<HTMLElement|null>(null)

 useEffect(()=>{backendSessions.current.clear();setFeedbackTurn(null);setFeedbackSaved(false);setReported([]);setConversations([]);setActive(null);setQuestion('');setFeedbackContextId(undefined);setAskedQuestion('');setEmpty(false);setAnswerNotice('');setDraft(null);setPending(null);setAnswer(null);setSelected([]);setConsent(false);setPreview(null);setError('')},[kbId,user?.username])
 useEffect(()=>{const preset=params.get('question');if(preset)setQuestion(preset.slice(0,2000))},[params])
 const currentTurn:Turn={question:askedQuestion,answer,empty,error,notice:answerNotice,feedbackContextId}
 const previousTurns=conversations.find(conversation=>conversation.id===active)?.turns||[]
 const turnCount=previousTurns.length
 useEffect(()=>{turnAnchor.current?.scrollIntoView({block:'start'})},[active,askedQuestion,turnCount])

 function archiveTurn(){
  if(!active||!askedQuestion)return
  const turn=answer||empty||error?currentTurn:{...currentTurn,error:'这轮未生成回答。'}
  setConversations(items=>items.map(item=>item.id===active?{...item,turns:[...item.turns,turn]}:item))
 }

 function selectConversation(id:string|null){
  if(busy||id!==null&&id===active)return
  archiveTurn()
  setActive(id);setFeedbackContextId(undefined);setAskedQuestion('');setQuestion('');setAnswer(null);setDraft(null);setPending(null);setConsent(false)
  setEmpty(false);setError('');setAnswerNotice('');setPreview(null)
  requestAnimationFrame(()=>questionInput.current?.focus())
 }
 function finishAnswer(result:QaResult){
  setAnswer(result)
  setFeedbackContextId(result.feedback_context_id)
  setPending(null)
 }

 async function runQuestion(value:string,fresh=false){
  const current=value.trim()
  if(!current||busy||!route)return
  archiveTurn()
  const id=active??String(++nextConversation.current)
  if(!active){
   setConversations(items=>[{id,title:current,turns:[]},...items])
   setActive(id)
  }
  setFeedbackContextId(undefined);setQuestion('');setAskedQuestion(current);setEmpty(false);setAnswerNotice('')
  setBusy(true);setError('');setPending(null);setConsent(false);setAnswer(null);setDraft(null);setSelected([])
  if(questionOnly)setPhase('search')
  try{
   const sessionId=questionOnly&&!fresh?backendSessions.current.get(id):undefined
   const next=await api.post<any>('/api/rag/drafts',{question:current,...(sessionId&&{session_id:sessionId})})
   if(questionOnly&&next.session_id)backendSessions.current.set(id,next.session_id)
   if(next.status!=='drafted'){
    setError(next.message||'请补全问题。')
    return
   }
   setFeedbackContextId(next.feedback_context_id)
   const ids=next.default_candidate_ids||[]
   if(!questionOnly){
    setDraft(next);setSelected(ids);setVersion(next.selection_version||0)
    return
   }
   const candidates: Array<{selectable: boolean}> = next.candidates || []
   if(!ids.length){
    if(candidates.some(candidate=>candidate.selectable)){
     setError('命中的资料超出本地模型的可用容量。请缩小问题范围后再试。')
    }else{
     setEmpty(true)
    }
    return
   }
   const prepared=await api.post<any>('/api/rag/selection',{
    draft_id:next.draft_id,selection_version:next.selection_version,candidate_ids:ids,
   })
   const destination=answerRoute(prepared)
   if(destination==='confirm_external'){
    setPending(prepared)
    requestAnimationFrame(()=>document.getElementById('qa-final-confirmation')?.scrollIntoView({block:'nearest'}))
    return
   }
   if(destination!=='local')throw new Error('无法确认本轮的模型接收地址，请重新检索。')
   if(!prepared.configured)throw new Error('本地 Ollama 或模型暂不可用。')
   if(prepared.notice?.includes('本轮使用本地 Ollama'))setAnswerNotice(prepared.notice)
   setPhase('answer')
   finishAnswer(await api.post<QaResult>('/api/rag/answer',{ticket:prepared.ticket,consent:true}))
  }catch(cause){
   if(cause instanceof ApiError&&['session_expired','history_invalid'].includes(cause.code??''))backendSessions.current.delete(id)
   setError((cause as Error).message)
  }finally{
   setPhase(null);setBusy(false)
  }
 }
 function ask(event:React.FormEvent){event.preventDefault();void runQuestion(question)}
 async function prepare(){setBusy(true);setError('');try{const p=await api.post<any>('/api/rag/selection',{draft_id:draft.draft_id,selection_version:version,candidate_ids:selected});setVersion(p.selection_version??version+1);setPending(p);setConsent(false);requestAnimationFrame(()=>document.getElementById('qa-final-confirmation')?.scrollIntoView({block:'start'}))}catch(e){setPending(null);setError((e as Error).message)}finally{setBusy(false)}}
 async function send(){if(!pending||!consent||!pending.configured||busy)return;setBusy(true);setError('');try{finishAnswer(await api.post<QaResult>('/api/rag/answer',{ticket:pending.ticket,consent:true}));requestAnimationFrame(()=>document.getElementById('qa-answer')?.scrollIntoView({block:'start'}))}catch(e){setPending(null);setConsent(false);setError((e as Error).message);if(e instanceof ApiError&&e.code==='external_blocked')void api.get('/api/rag').then(setRoute).catch(()=>{})}finally{setBusy(false)}}
 async function adjustEvidence(){if(busy||!draft)return;const keys=new Set(draft.candidates.filter((c:any)=>selected.includes(c.candidate_id)).map(candidateIdentity));setBusy(true);setAnswer(null);setPending(null);setConsent(false);setError('');try{const next=await api.post<any>('/api/rag/drafts',{question:askedQuestion});setDraft(next);setSelected((next.candidates||[]).filter((c:any)=>c.selectable&&keys.has(candidateIdentity(c))).map((c:any)=>c.candidate_id));setVersion(next.selection_version||0)}catch(e){setDraft(null);setSelected([]);setError((e as Error).message)}finally{setBusy(false)}}
 async function switchProvider(provider:'ollama'|'deepseek'){
  if(busy||(!route?.question_only_external&&kbId!=='demo'))return
  archiveTurn()
  backendSessions.current.clear()
  setFeedbackContextId(undefined);setAskedQuestion('')
  setBusy(true);setError('');setDraft(null);setPending(null);setAnswer(null);setEmpty(false);setAnswerNotice('');setSelected([]);setConsent(false);setPreview(null)
  try{await api.post('/api/rag/provider',{provider,confirm_external:provider==='deepseek'});const next=await api.get<any>('/api/rag');setRoute(next);const credential=await loadModelConfig();setModelConfig(credential);if(provider==='deepseek'&&!credential.configured)setConfigOpen(true)}catch(e){void api.get('/api/rag').then(setRoute).catch(()=>{});throw e}finally{setBusy(false)}
 }
 function openSource(source:QaCitation){
  previewTrigger.current=document.activeElement instanceof HTMLElement?document.activeElement:null
  const locations=citationLocations(source)
  setPreview(previous=>({locations,index:0,visit:(previous?.visit??0)+1}))
 }
 function closePreview(){
  setPreview(null)
  if(dockPreview)previewTrigger.current?.focus({preventScroll:true})
 }
 const questionOnly=route?.question_only_external===true
 const local=kbId!=='demo'&&!route?.local&&!questionOnly
 const cls='rounded-lg border border-border bg-card p-4'
 const name=demoIdentityName(user?.username)??user?.role.name??'用户'
 const guest=user?.accessRole==='guest'
 const documentIds=new Set(searchableDocs.map(doc=>doc.id))
 const settings=<>
  <QaModelRoute local={questionOnly?!route.external_selected:route?!!route.local:kbId!=='demo'} ready={!!route}
    supported={!!route?.provider_switch_supported} qichen={kbId!=='demo'&&!questionOnly}
    questionOnly={questionOnly} externalEnabled={route?.external_model_enabled} busy={busy} onChange={switchProvider}/>
  {route?.local&&<p className="text-xs text-muted-foreground">Ollama · {route.model} · {route.configured?'本地推理':'服务或模型不可用'}</p>}
  {route&&(kbId==='demo'&&!route.local||questionOnly&&route.external_model_enabled)&&
    <button type="button" aria-label="配置模型API" disabled={busy||configLoading} onClick={()=>setConfigOpen(true)} className={button}>
      <Cpu className="size-4"/>{configLoading?'正在读取模型配置…':modelConfig?.configured?`DeepSeek 已配置 · ${modelConfig.model}`:'配置 DeepSeek API'}
    </button>}
  {configError&&!local&&<p role="alert" className="text-xs text-destructive">{configError}</p>}
  {route?.fallback_available&&!route?.provider_switch_supported&&kbId==='demo'&&<section className={cls}><p className="text-sm">Ollama不可用。可在确认后切换本次登录到DeepSeek；旧证据与确认将作废。</p><label className="my-3 flex gap-2 text-xs"><input type="checkbox" checked={fallbackConsent} onChange={e=>setFallbackConsent(e.target.checked)}/>我确认改用外部DeepSeek，随后重新选择获准证据并确认外发。</label><button className={button} disabled={busy||!fallbackConsent} onClick={async()=>{setBusy(true);setError('');try{await api.post('/api/rag/fallback',{confirm_external_fallback:true});setDraft(null);setPending(null);setAnswer(null);setSelected([]);setConsent(false);setRoute(await api.get('/api/rag'));setModelConfig(await loadModelConfig())}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>确认切换到DeepSeek</button></section>}
  {questionOnly&&user?.accessRole==='boss'&&<ExternalModelAdmin onChanged={()=>{setPending(null);setConsent(false);void api.get('/api/rag').then(setRoute).catch(()=>{})}}/>}
 </>

 function renderResult(turn:Turn, isCurrent:boolean){
  const suggestions=isCurrent?examples.filter(example=>example.question!==turn.question).slice(0,2):[]
  const noEvidence=turn.empty||turn.answer?.answer_status==='insufficient_evidence'
  const citations=turn.answer?.citations||[]
  const sourcesAvailable=citations.every(source=>
   documentIds.has(source.document_id)&&(source.members||[]).every(member=>documentIds.has(member.document_id)))
  const actions=(turn.answer||noEvidence)&&<QaAnswerActions provider={sourcesAvailable?turn.answer?.provider:undefined}>
   {kbId==='business'&&!guest&&turn.feedbackContextId&&(turn.answer||noEvidence)&&<button type="button" disabled={reported.includes(turn.feedbackContextId)||!sourcesAvailable} className="qa-answer-action" onClick={()=>{setFeedbackSaved(false);setFeedbackTurn({contextId:turn.feedbackContextId!,question:turn.question,answer:turn.answer?.answer||'没找到可靠依据',citations})}}>{reported.includes(turn.feedbackContextId)?<Check size={14}/>:<Flag size={14}/>}<span>{reported.includes(turn.feedbackContextId)?'已反馈':'反馈答案问题'}</span></button>}
   {kbId==='business'&&!guest&&<button type="button" className="qa-answer-action" onClick={()=>{setRequestSaved(false);setRequestQuestion(turn.question)}}><Flag size={14}/><span>申请资料支持</span></button>}
   </QaAnswerActions>
  return <>
   {turn.error&&<p role="alert" className="qa-chat-error">{turn.error}{turn.error.includes('历史归档 → 查正文')&&
    <> <a className="underline" href={`/documents?view=${encodeURIComponent('历史归档')}`}>打开历史归档</a></>}</p>}
   {questionOnly&&noEvidence&&<QaNoEvidence supportAvailable={kbId==='business'&&!guest} question={turn.question} examples={suggestions} onAsk={runQuestion} />}
   {turn.answer&&(!questionOnly||!noEvidence)&&<div id={isCurrent?'qa-answer':undefined}>
    {!sourcesAvailable?<p className="qa-chat-error">引用资料已变更或当前不可查看，请重新提问。</p>:
    noEvidence?<AnswerPresentation answer={turn.answer} onSource={openSource}/>:
      <QaAnswerFirst answer={turn.answer} notice={turn.notice} examples={suggestions} onAsk={runQuestion}
        onSource={openSource} documents={searchableDocs} guest={guest} actions={actions}/>}
   </div>}
   {(!turn.answer||noEvidence||!sourcesAvailable)&&actions}
  </>
 }

 return <>
  <QaWorkspace onWidthChange={syncQaWidth} guest={guest} library={kb.name} name={name} role={guest?'外部参观':user?.role.name??''} settings={kbId==='business'&&user?.accessRole!=='boss'?null:settings} tools={<>{kbId==='business'&&!guest&&<MyAccessRequests rows={requests.rows.filter(r=>r.owner===user?.username)} error={requests.error} loaded={requests.loaded} onRefresh={requests.load} onAsk={value=>{void refresh().then(()=>runQuestion(value,true))}}/>}<Link to="/documents">{guest?'公开资料':'我的资料'}</Link></>}
    previewDocked={dockPreview&&!!previewDoc} preview={preview&&activeSource&&previewDoc&&
      <DocPreviewDialog presentation={dockPreview?'panel':'drawer'} sourceRef={activeSource} sourceVisit={preview.visit}
        doc={previewDoc} open onClose={closePreview} navigation={preview.locations.length>1&&
          <label className="qa-preview-selector">
            引用位置
            <select value={preview.index} onChange={event=>{
              const index=Number(event.currentTarget.value)
              setPreview(current=>current&&{...current,index})
            }}>
              {preview.locations.map((source,index)=><option key={index} value={index}>
                {index+1}. {documentTitleParts(source.document_name).title}{source.section&&' · '+source.section}
              </option>)}
            </select>
          </label>}/> }
    history={conversations} active={active} hasTurns={!!askedQuestion||previousTurns.length>0} busy={busy}
    ready={!!route} question={question} inputRef={questionInput} examples={examples.slice(0,3)}
    externalSelected={!!route?.external_selected||!!route&&!route.local&&kbId==='demo'}
    onChange={setQuestion} onAsk={ask} onNew={()=>selectConversation(null)} onSelect={selectConversation}>
    {previousTurns.map((turn,index)=><QaChatTurn key={active+'/'+index} question={turn.question}
      anchor={index===previousTurns.length-1&&!askedQuestion?turnAnchor:undefined}>{renderResult(turn,false)}</QaChatTurn>)}
    {askedQuestion&&<QaChatTurn key={active+'/'+previousTurns.length} anchor={turnAnchor} question={askedQuestion}>
      {phase&&<QaAnswerLoading phase={phase}/>}
      {renderResult(currentTurn,true)}
      {!questionOnly&&draft?.status==='drafted'&&<EvidenceStack draft={draft} selected={selected} busy={busy} localOnly={local}
        readOnly={!!answer} onSelection={ids=>{setPending(null);setAnswer(null);setConsent(false);setSelected(ids)}}
        onSource={openSource} onPrepare={prepare} onAdjust={adjustEvidence}/>}
      {pending?.notice?.includes('本轮使用本地 Ollama')&&<p role="status" className="qa-first-notice">{pending.notice}</p>}
      {pending&&<QaConfirmation privateDeployment={!['localhost','127.0.0.1','::1','[::1]'].includes(location.hostname)}
        key={pending.ticket} pending={pending} consent={consent} busy={busy} onConsent={setConsent} onSend={send}
        onCancel={()=>{setPending(null);setConsent(false);if(questionOnly){setError('已取消本轮外部请求。');questionInput.current?.focus()}else document.getElementById('qa-evidence-selection')?.scrollIntoView({block:'start'})}}/>}
    </QaChatTurn>}
    {routeError&&<p role="alert" className="qa-chat-error">问答服务暂不可用。 <button type="button" onClick={()=>setRouteAttempt(attempt=>attempt+1)}>重试</button></p>}
  </QaWorkspace>
  {requestQuestion!==null&&<RequestSupport question={requestQuestion} onClose={()=>setRequestQuestion(null)} onSaved={()=>{setRequestQuestion(null);setRequestSaved(true);void requests.load()}}/>}
  {requestSaved&&<div role="status" className="dm-feedback"><span>申请已提交至相关部门，可在“我的申请”查看结果。</span><button aria-label="关闭申请提示" onClick={()=>setRequestSaved(false)}>×</button></div>}
  {feedbackTurn&&<RecordFeedback turn={feedbackTurn} onClose={()=>setFeedbackTurn(null)} onSaved={()=>{setReported(ids=>[...ids,feedbackTurn.contextId]);setFeedbackTurn(null);setFeedbackSaved(true)}}/>}
  {feedbackSaved&&<div role="status" className="dm-feedback"><span>反馈已记录。</span><Link to="/knowledge-gaps" className="underline">查看反馈记录</Link><button aria-label="关闭反馈提示" onClick={()=>setFeedbackSaved(false)}>×</button></div>}
  {(kbId==='demo'||questionOnly)&&<ModelConfigDialog open={configOpen} onClose={closeConfig} onStatus={setModelConfig}
    onChanged={()=>{setPending(null);setConsent(false);setConfigError('')}}/>}
 </>
}
