import {useCallback,useEffect,useRef,useState} from 'react'
import {FileQuestion,RefreshCw,ChevronDown,FileText} from 'lucide-react'
import {api} from '@/lib/api'
import {documentTitleParts} from '@/lib/document-title'
import {useSession} from '@/lib/session'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {DocumentModal} from './DocumentLayout'
import {BUSINESS_DEPARTMENTS,type BusinessRow} from './BusinessPresentation'
import './AccessRequests.css'

type Recommendation={id:string;name:string;document_version:number;excerpt:string;section:string;priority?:boolean;support_quote?:string;reason?:string}
type Recommendations={items:Recommendation[];notice:string;review_available?:boolean}

export type AccessRequest={id:string;owner:string;owner_department:string;department:string;question:string;purpose:string;status:'pending'|'approved'|'rejected'|'cancelled';version:number;can_review:boolean;document:{id:string;name:string}|null;access_available:boolean;expires_at:number|null;updated:number}
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

export function AccessRequestList({rows,review=false,onChanged,onAsk}:{rows:AccessRequest[];review?:boolean;onChanged:()=>Promise<void>;onAsk?:(question:string)=>void}){
 const {user}=useSession()
 const [selected,setSelected]=useState<AccessRequest|null>(null),[docs,setDocs]=useState<BusinessRow[]>([]),[documentId,setDocumentId]=useState(''),[days,setDays]=useState(7),[busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState('')
 const [recommendations,setRecommendations]=useState<Recommendations|null>(null),[recommendationError,setRecommendationError]=useState('')
 const openSequence=useRef(0)
 useEffect(()=>()=>{openSequence.current++},[])
 const pending=rows.filter(r=>r.status==='pending').length
 async function open(row:AccessRequest){
  const seq=++openSequence.current
  setSelected(row);setDocumentId('');setDocs([]);setRecommendations(null);setRecommendationError('');setError('');setDays(7);setLoading(true)
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
 const candidates=(recommendations?.items||[]).filter(item=>available.some(d=>d.id===item.id))
 const primary=candidates.slice(0,2),more=candidates.slice(2)
 const renderRecommendation=(item:Recommendation)=>{const {title,number}=documentTitleParts(item.name);const version=available.find(d=>d.id===item.id)?.version;return <article key={item.id} className={'access-recommendation'+(documentId===item.id?' is-selected':'')}><details name="access-recommendation-preview"><summary><FileText size={18} aria-hidden="true"/><span className="access-recommendation-title"><strong title={item.name}>{title.replace(/\s+[vV]\d+(?:\.\d+)*$/,'')}{version&&<span className="access-document-version">{version}</span>}</strong>{item.priority&&<span className="access-priority">优先核对</span>}<small>{item.section||'相关片段'} · <span className="access-show-excerpt">查看片段</span><span className="access-hide-excerpt">收起片段</span></small></span><ChevronDown size={15} className="access-recommendation-chevron" aria-hidden="true"/></summary>{number&&<p className="access-document-number">文档编号：{number}</p>}<blockquote>{item.excerpt}</blockquote></details><button type="button" disabled={busy} aria-pressed={documentId===item.id} onClick={()=>setDocumentId(item.id)}>{documentId===item.id?'已选此文件':'选择此文件'}</button><div className="access-recommendation-reason"><p>{item.reason}</p>{item.support_quote&&<p className="access-support-quote">原文依据：{item.support_quote}</p>}</div></article>}
 return <div className="access-requests"><div className="access-intro"><strong>{review?'借阅申请':'我的申请'}{pending>0&&` · ${pending} 条待处理`}</strong><p>{review?'申请按资料相关部门送达。选择文件批准后，系统会授予申请人只读借阅权限。':'批准表示文件可以查阅，不保证包含问题答案。重新提问后仍缺少依据，可继续申请资料支持或反馈资料缺口。'}</p></div>
  {error&&!selected&&<p role="alert">{error}</p>}
  {!rows.length&&<p className="access-empty">{review?'暂无需要处理的借阅申请。':'暂无资料支持申请。'}</p>}
  {rows.map(row=><article key={row.id} className="access-request"><div className="access-request-heading"><strong>{row.question}</strong><span className={'access-status '+row.status}>{({pending:'待处理',approved:row.access_available?'已批准 · 可查阅':'已批准 · 当前不可查阅',rejected:'未批准',cancelled:'已撤回'})[row.status]}</span></div>
   <p>{review?`${demoIdentityName(row.owner)||row.owner} · ${row.owner_department} → `:''}{row.department} · {new Date(row.updated*1000).toLocaleString('zh-CN')}</p><p>用途：{row.purpose}</p>
   {row.document&&<p className="access-document">获准资料：{row.document.name}{row.expires_at&&<small>借阅有效至 {new Date(row.expires_at*1000).toLocaleString('zh-CN')}</small>}</p>}
   {row.status==='approved'&&!row.access_available&&<p>资料权限或状态已变化，请联系相关部门确认。</p>}
   {row.status==='rejected'&&<p>相关部门本次未批准借阅，可补充用途后重新申请。</p>}
   <div className="access-actions">{review&&row.can_review&&row.status==='pending'&&<button className="dm-primary" disabled={busy} onClick={()=>void open(row)}>处理申请</button>}
    {!review&&row.status==='pending'&&<button disabled={busy} onClick={()=>void decide(row,'cancel')}>撤回申请</button>}
    {!review&&row.status==='approved'&&row.access_available&&(onAsk?<button className="dm-primary" onClick={()=>onAsk(row.question)}>重新提问</button>:<a href={'/qa?question='+encodeURIComponent(row.question)}>去知识问答重新提问 →</a>)}
   </div>
  </article>)}
  {selected&&<DocumentModal open title="处理借阅申请" description="仅批准本次需要的文件；阅读授权不包含修改、发布或再次授权。" busy={busy} onClose={()=>{openSequence.current++;setSelected(null)}}><div className="access-form"><strong>{selected.question}</strong><p>{demoIdentityName(selected.owner)||selected.owner} · {selected.owner_department}</p><p>用途：{selected.purpose}</p>
   <section className="access-recommendations" aria-label="相关资料推荐"><strong>相关资料推荐</strong><p>优先核对原文依据，再结合用途选择一份文件。仅展示你可授权的本部门资料。</p>
    {loading?<p role="status">正在检索并核对原文依据…</p>:recommendationError?<p role="alert">{recommendationError}；可使用下方列表手动选择。</p>:<>{(!recommendations?.items.length||!recommendations.review_available)&&<p>{recommendations?.notice}</p>}{primary.map(renderRecommendation)}{more.length>0&&<details className="access-more"><summary>更多相关资料 · {more.length} 份{more.some(item=>item.id===documentId)?' · 含已选文件':''}<ChevronDown size={14}/></summary><div>{more.map(renderRecommendation)}</div></details>}</>}
   </section>
   <label>选择借阅文件<select disabled={loading||busy} value={documentId} onChange={e=>setDocumentId(e.target.value)}><option value="">{loading?'正在读取可授权资料…':'请选择一份已发布资料'}</option>{available.map(d=><option key={d.id} value={d.id}>{d.name} · {d.version}</option>)}</select></label>
   {!loading&&!available.length&&<p>该部门暂无你可授权的已发布且可检索资料。</p>}
   <label>借阅期限<select value={days} disabled={busy} onChange={e=>setDays(Number(e.target.value))}>{[1,3,7,30].map(n=><option key={n} value={n}>{n} 天</option>)}</select></label>
   {error&&<p role="alert">{error}</p>}<div className="dm-modal-actions"><button className="dm-primary" disabled={busy||loading||!documentId} onClick={()=>void decide(selected,'approve')}>批准并授权</button><button disabled={busy} onClick={()=>void decide(selected,'reject')}>不批准</button></div>
  </div></DocumentModal>}
 </div>
}

export function MyAccessRequests({rows,error,loaded,onRefresh,onAsk}:{rows:AccessRequest[];error:string;loaded:boolean;onRefresh:()=>Promise<void>;onAsk:(question:string)=>void}){
 const [open,setOpen]=useState(false)
 const available=rows.filter(r=>r.status==='approved'&&r.access_available).length
 return <><button type="button" className="access-inbox-button" onClick={()=>{setOpen(true);void onRefresh()}}><FileQuestion size={15}/>我的申请{available>0&&<span>{available} 项可查阅</span>}</button>{open&&<DocumentModal open title="我的资料支持申请" description="结果每5秒更新，可刷新查看最新权限。" onClose={()=>setOpen(false)}><button className="access-refresh" onClick={()=>void onRefresh()}><RefreshCw size={14}/>刷新</button>{error&&<p role="alert">{error}</p>}{!loaded?<p>正在加载申请…</p>:<AccessRequestList rows={rows} onChanged={onRefresh} onAsk={question=>{setOpen(false);onAsk(question)}}/>}</DocumentModal>}</>
}
