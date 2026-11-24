import {useCallback,useEffect,useRef,useState} from 'react'
import {FileQuestion,RefreshCw,ChevronDown,FileText,CheckCircle2,UserRound} from 'lucide-react'
import {api} from '@/lib/api'
import {documentTitleParts} from '@/lib/document-title'
import {useSession} from '@/lib/session'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {DocumentModal} from './DocumentLayout'
import {BUSINESS_DEPARTMENTS,type BusinessRow} from './BusinessPresentation'
import {BorrowFilePicker} from './BorrowFilePicker'
import './AccessRequests.css'

type Recommendation={id:string;name:string;document_version:number;excerpt:string;section:string;priority?:boolean;support_quote?:string;reason?:string}
type Recommendations={items:Recommendation[];notice:string;review_available?:boolean}

export type AccessRequest={id:string;owner:string;owner_department:string;department:string;question:string;purpose:string;status:'pending'|'approved'|'rejected'|'cancelled';version:number;can_review:boolean;reviewer_scope?:string|null;handled_by?:string|null;document:{id:string;name:string}|null;access_available:boolean;expires_at:number|null;updated:number}
export function useAccessRequests(enabled:boolean){
 const [rows,setRows]=useState<AccessRequest[]>([]),[error,setError]=useState(''),[loaded,setLoaded]=useState(false)
 const sequence=useRef(0)
 const load=useCallback(async()=>{
  if(!enabled)return
  const id=++sequence.current
  try{const data=await api.get<AccessRequest[]>('/api/business/access-requests');if(id===sequence.current){setRows(data);setError('');setLoaded(true)}}catch(e){if(id===sequence.current)setError((e as Error).message)}
 },[enabled])
 useEffect(()=>{setRows([]);setLoaded(false);setError('');void load();if(!enabled)return;const timer=setInterval(()=>void load(),5000);return()=>{sequence.current++;clearInterval(timer)}},[load])
 return {rows,error,loaded,load}
}

export function RequestSupport({question,onClose,onSaved}:{question:string;onClose:()=>void;onSaved:()=>void}){
 const [text,setText]=useState(question),[purpose,setPurpose]=useState(''),[department,setDepartment]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('')
 async function submit(e:React.FormEvent){e.preventDefault();if(busy)return;setBusy(true);setError('');try{await api.post('/api/business/access-requests',{question:text.trim(),purpose:purpose.trim(),department});onSaved()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <DocumentModal open title="申请资料支持" description="说明你需要解决的问题，由相关部门主管选择可借阅的资料。主管会核对相关资料；资料不足时也可能需要补充内容。" busy={busy} onClose={onClose}><form className="access-form" onSubmit={submit}>
  <label>需要解决的问题<textarea required maxLength={2000} value={text} onChange={e=>setText(e.target.value)} /></label>
  <label>相关部门<select required value={department} onChange={e=>setDepartment(e.target.value)}><option value="">请选择资料相关部门</option>{BUSINESS_DEPARTMENTS.map(d=><option key={d}>{d}</option>)}</select></label>
  <label>使用用途<textarea required maxLength={1000} placeholder="例如：排查生产现场的设备接口报错" value={purpose} onChange={e=>setPurpose(e.target.value)}/></label>
  {error&&<p role="alert">{error}</p>}<div className="dm-modal-actions"><button className="dm-primary" disabled={busy||!text.trim()||!purpose.trim()||!department}>{busy?'提交中…':'提交申请'}</button><button type="button" onClick={onClose} disabled={busy}>取消</button></div>
 </form></DocumentModal>
}

export function AccessRequestList({rows,review=false,onChanged,onAsk,showIntro=true,emptyText}:{rows:AccessRequest[];review?:boolean;showIntro?:boolean;emptyText?:string;onChanged:()=>Promise<void>;onAsk?:(question:string)=>void}){
 const {user}=useSession()
 const [selected,setSelected]=useState<AccessRequest|null>(null),[docs,setDocs]=useState<BusinessRow[]>([]),[documentId,setDocumentId]=useState(''),[days,setDays]=useState(7),[busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState('')
 const [recommendations,setRecommendations]=useState<Recommendations|null>(null),[recommendationError,setRecommendationError]=useState('')
 const [manualOpen,setManualOpen]=useState(false)
 const manualToggle=useRef<HTMLButtonElement>(null)
 const openSequence=useRef(0)
 useEffect(()=>()=>{openSequence.current++},[])
 const pending=rows.filter(r=>r.status==='pending').length
 async function open(row:AccessRequest){
  const seq=++openSequence.current
  setSelected(row);setDocumentId('');setManualOpen(false);setDocs([]);setRecommendations(null);setRecommendationError('');setError('');setDays(7);setLoading(true)
  const results=await Promise.allSettled([api.get<BusinessRow[]>('/api/business/documents'),api.get<Recommendations>('/api/business/access-requests/'+row.id+'/recommendations')])
  if(seq!==openSequence.current)return
  if(results[0].status==='fulfilled')setDocs(results[0].value);else setError((results[0].reason as Error).message)
  if(results[1].status==='fulfilled')setRecommendations(results[1].value);else setRecommendationError((results[1].reason as Error).message)
  setLoading(false)
 }
 async function decide(row:AccessRequest,action:'approve'|'reject'|'cancel'){
  if(busy)return
  setBusy(true);setError('')
  const doc=docs.find(d=>d.id===documentId)
  try{await api.post('/api/business/access-requests/'+row.id+'/decision',{expected:row.version,action,...(action==='approve'?{document_id:doc?.id,document_version:doc?.workflow.version,days}:{})});setSelected(null);await onChanged()}catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 const available=docs.filter(d=>d.department===selected?.department&&d.workflow.status==='published'&&!d.workflow.deleted&&!d.workflow.archived&&d.technical_index_ready&&(!d.workflow.restricted||user?.accessRole==='boss'))
 const documentGroups=Array.from(available.reduce((groups,doc)=>{
  const category=doc.docType?.trim()||'未分类'
  const group=groups.get(category)||[];group.push(doc);groups.set(category,group);return groups
 },new Map<string,BusinessRow[]>())).sort(([a],[b])=>a===b?0:a==='未分类'?1:b==='未分类'?-1:a.localeCompare(b,'zh-CN')).map(([category,items])=>({category,items:items.sort((a,b)=>a.name.localeCompare(b.name,'zh-CN',{numeric:true}))}))
 const candidates=(recommendations?.items||[]).filter(item=>available.some(d=>d.id===item.id))
 const primary=candidates.slice(0,2),more=candidates.slice(2)
 const selectedDocument=available.find(d=>d.id===documentId)
 function chooseDocument(id:string){setDocumentId(id);if(id)setManualOpen(false)}
 const renderRecommendation=(item:Recommendation)=>{const {title,number}=documentTitleParts(item.name);const version=available.find(d=>d.id===item.id)?.version;return <article key={item.id} className={'access-recommendation'+(documentId===item.id?' is-selected':'')}><details name="access-recommendation-preview"><summary><FileText size={18} aria-hidden="true"/><span className="access-recommendation-title"><strong title={item.name}>{title.replace(/\s+[vV]\d+(?:\.\d+)*$/,'')}{version&&<span className="access-document-version">{version}</span>}</strong>{item.priority&&<span className="access-priority">优先核对</span>}<small className="access-excerpt-meta"><span>{item.section||'相关片段'}</span><span className="access-excerpt-toggle"><span className="access-show-excerpt">查看片段</span><span className="access-hide-excerpt">收起片段</span><ChevronDown size={13} className="access-recommendation-chevron" aria-hidden="true"/></span></small></span></summary>{number&&<p className="access-document-number">文档编号：{number}</p>}<blockquote>{item.excerpt}</blockquote></details><button type="button" className="access-select-file" disabled={busy} aria-pressed={documentId===item.id} onClick={()=>chooseDocument(item.id)}>{documentId===item.id&&<CheckCircle2 size={14} aria-hidden="true"/>}{documentId===item.id?'已选此文件':'选择此文件'}</button><div className="access-recommendation-reason"><p>{item.reason}</p>{item.support_quote&&<p className="access-support-quote">原文依据：{item.support_quote}</p>}</div></article>}
 return <div className="access-requests">{showIntro&&<div className="access-intro"><strong>{review?'借阅申请':'我的申请'}{pending>0&&` · ${pending} 条待处理`}</strong><p>{review?'申请按资料相关部门送达。选择文件批准后，系统会授予申请人只读借阅权限。':'批准表示文件可以查阅，不保证包含问题答案。重新提问后仍缺少依据，可继续申请资料支持或反馈资料缺口。'}</p></div>}
  {error&&!selected&&<p role="alert">{error}</p>}
  {!rows.length&&<p className="access-empty">{emptyText||(review?'暂无需要处理的借阅申请。':'暂无资料支持申请。')}</p>}
  {rows.map(row=><article key={row.id} className="access-request"><div className="access-request-heading"><strong>{row.question}</strong><span className={'access-status '+row.status}>{({pending:'待处理',approved:row.access_available?'已批准 · 可查阅':'已批准 · 当前不可查阅',rejected:'未批准',cancelled:'已撤回'})[row.status]}</span></div>
   <p>{review?`${demoIdentityName(row.owner)||row.owner} · ${row.owner_department} → `:''}{row.department} · {new Date(row.updated*1000).toLocaleString('zh-CN')}</p><p>用途：{row.purpose}</p>
   <div className="access-handler-row"><div className="access-handler"><UserRound size={14} aria-hidden="true"/><span>{row.status==='pending'?<><span className="access-handler-label">待处理方</span>{row.reviewer_scope||`${row.department}主管或管理层`}<small>按部门送达，尚未指定个人</small></>:<><span className="access-handler-label">{row.status==='approved'?'批准人':row.status==='rejected'?'处理人':'撤回人'}</span>{row.handled_by?demoIdentityName(row.handled_by):'暂无处理人记录'}</>}</span></div>{!review&&row.status==='pending'&&<button type="button" className="access-withdraw" disabled={busy} onClick={()=>void decide(row,'cancel')}>撤回申请</button>}</div>
   {(row.document||(!review&&row.status==='approved'&&row.access_available))&&<div className="access-approved-row">{row.document&&<p className="access-document">获准资料：{row.document.name}{row.expires_at&&<small>借阅有效至 {new Date(row.expires_at*1000).toLocaleString('zh-CN')}</small>}</p>}{!review&&row.status==='approved'&&row.access_available&&(onAsk?<button className="dm-primary" onClick={()=>onAsk(row.question)}>重新提问</button>:<a href={'/qa?question='+encodeURIComponent(row.question)}>去知识问答重新提问 →</a>)}</div>}
   {row.status==='approved'&&!row.access_available&&<p>资料权限或状态已变化，请联系相关部门确认。</p>}
   {row.status==='rejected'&&<p>相关部门本次未批准借阅，可补充用途后重新申请。</p>}
   <div className="access-actions">{review&&row.can_review&&row.status==='pending'&&<button className="dm-primary" disabled={busy} onClick={()=>void open(row)}>处理申请</button>}
   </div>
  </article>)}
  {selected&&<DocumentModal open title="处理借阅申请" description="按用途授予只读借阅，不包含修改、发布或再次授权。" busy={busy} onClose={()=>{openSequence.current++;setSelected(null)}}><div className="access-form">
   <section className="access-request-summary" aria-label="申请详情">
    <div className="access-applicant"><span className="access-applicant-avatar" aria-hidden="true">{(demoIdentityName(selected.owner)||selected.owner).slice(0,1)}</span><div><span className="access-summary-label">申请人</span><div className="access-applicant-meta"><strong>{demoIdentityName(selected.owner)||selected.owner}</strong><span>{selected.owner_department}</span></div></div></div>
    <div className="access-request-question"><span className="access-summary-label">申请问题</span><h3>{selected.question}</h3></div>
    <div className="access-request-purpose"><span className="access-summary-label">使用用途</span><p>{selected.purpose}</p></div>
   </section>
   <section className="access-recommendations" aria-label="相关资料推荐"><strong>相关资料推荐</strong><p>优先核对原文依据，再结合用途选择一份文件。仅展示你可授权的本部门资料。</p>
    {loading?<p role="status">正在检索并核对原文依据…</p>:recommendationError?<p role="alert">{recommendationError}；可点击下方“手动选择文件”查找。</p>:<>{(!recommendations?.items.length||!recommendations.review_available)&&<p>{recommendations?.notice}</p>}{primary.map(renderRecommendation)}{more.length>0&&<details className="access-more"><summary>更多相关资料 · {more.length} 份{more.some(item=>item.id===documentId)?' · 含已选文件':''}<ChevronDown size={14}/></summary><div>{more.map(renderRecommendation)}</div></details>}</>}
   </section>
   <section className="access-settings" aria-label="借阅设置"><strong className="access-settings-title">借阅设置</strong>
    <div className="access-choice-row"><div className="access-selection" aria-live="polite">{selectedDocument?<><CheckCircle2 size={18} aria-hidden="true"/><div><span>已选文件</span><strong title={selectedDocument.name}>{documentTitleParts(selectedDocument.name).title.replace(/\s+[vV]\d+(?:\.\d+)*$/,'')}{selectedDocument.version&&<small>{selectedDocument.version}</small>}</strong></div></>:<><FileText size={18} aria-hidden="true"/><div><strong>尚未选择文件</strong><span>从推荐资料选择，或手动查找</span></div></>}</div>
     <div className="access-manual"><button type="button" className="access-manual-toggle" ref={manualToggle} aria-haspopup="dialog" disabled={loading||busy} onClick={()=>setManualOpen(true)}><FileText size={15} aria-hidden="true"/>手动选择文件<ChevronDown size={14} aria-hidden="true"/></button></div>
    </div>

    {!loading&&!available.length&&<p>该部门暂无你可授权的已发布且可检索资料。</p>}
    <label className="access-duration"><span>借阅期限<small>仅授予只读权限</small></span><span className="access-duration-control"><select value={days} disabled={busy} onChange={e=>setDays(Number(e.target.value))}>{[1,3,7,30].map(n=><option key={n} value={n}>{n} 天</option>)}</select><ChevronDown size={14} aria-hidden="true"/></span></label>
   </section>
   {error&&<p role="alert">{error}</p>}<div className="dm-modal-actions access-review-actions"><button type="button" className="access-reject" disabled={busy} onClick={()=>void decide(selected,'reject')}>不予批准</button><button type="button" className="dm-primary" disabled={busy||loading||!selectedDocument} onClick={()=>void decide(selected,'approve')}>批准并授权</button></div>
  </div>{manualOpen&&<BorrowFilePicker groups={documentGroups} department={selected.department} value={documentId} onSelect={chooseDocument} onClose={()=>setManualOpen(false)} returnFocus={manualToggle}/>}</DocumentModal>}
 </div>
}

type RequestFilter='all'|'pending'|'available'|'history'
const requestCategory=(row:AccessRequest):Exclude<RequestFilter,'all'>=>row.status==='pending'?'pending':row.status==='approved'&&row.access_available?'available':'history'
const requestFilters:{id:RequestFilter;label:string;empty:string}[]=[
 {id:'all',label:'全部',empty:'暂无资料支持申请。'},
 {id:'pending',label:'待处理',empty:'暂无待处理申请，可切换到“可查阅”查看已获准的资料。'},
 {id:'available',label:'可查阅',empty:'暂无当前可查阅的申请。主管批准后，可在这里重新提问。'},
 {id:'history',label:'历史申请',empty:'暂无历史申请。已撤回、未批准或当前不可查阅的记录会保留在这里。'},
]
export function MyAccessRequests({rows,error,loaded,onRefresh,onAsk}:{rows:AccessRequest[];error:string;loaded:boolean;onRefresh:()=>Promise<void>;onAsk:(question:string)=>void}){
 const [open,setOpen]=useState(false),[filter,setFilter]=useState<RequestFilter>('all'),[refreshing,setRefreshing]=useState(false)
 const counts={all:rows.length,pending:0,available:0,history:0}
 for(const row of rows)counts[requestCategory(row)]++
 const priority={pending:0,available:1,history:2}
 const filtered=rows.filter(row=>filter==='all'||requestCategory(row)===filter).sort((a,b)=>(filter==='all'?priority[requestCategory(a)]-priority[requestCategory(b)]:0)||b.updated-a.updated||a.id.localeCompare(b.id))
 async function refresh(){if(refreshing)return;setRefreshing(true);try{await onRefresh()}finally{setRefreshing(false)}}
 return <><button type="button" className="access-inbox-button" onClick={()=>{setFilter('all');setOpen(true);void onRefresh()}}><FileQuestion size={15}/>我的申请{counts.available>0&&<span>{counts.available} 项可查阅</span>}</button>{open&&<DocumentModal open title="我的资料支持申请" description="跟进审批进度，查看获准资料；申请状态会自动更新。" onClose={()=>setOpen(false)}>
  <div className="access-inbox-toolbar"><div className="access-filter-group" role="group" aria-label="申请分类">{requestFilters.map(item=><button type="button" key={item.id} aria-pressed={filter===item.id} onClick={()=>setFilter(item.id)}>{item.label}<span>{loaded?counts[item.id]:'—'}</span></button>)}</div><button type="button" className="access-inbox-refresh" disabled={refreshing} onClick={()=>void refresh()}><RefreshCw size={14} aria-hidden="true"/>{refreshing?'刷新中':'刷新'}</button></div>
  <p className="access-inbox-note">批准后可查阅获准资料，并重新提问；回答仍以资料中的实际依据为准。</p>
  {error&&<p role="alert">{error}</p>}{!loaded?<p role="status">正在加载申请…</p>:<div className="access-filter-results" aria-label={requestFilters.find(item=>item.id===filter)?.label+'申请列表'}><AccessRequestList rows={filtered} showIntro={false} emptyText={requestFilters.find(item=>item.id===filter)?.empty} onChanged={onRefresh} onAsk={question=>{setOpen(false);onAsk(question)}}/></div>}
 </DocumentModal>}</>
}
