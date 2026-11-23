import {useEffect,useState} from 'react'
import {Search,ChevronLeft,ChevronRight,ArrowRight,FileText,Check,KeyRound,Undo2,Trash2,Upload,History} from 'lucide-react'
import {api} from '@/lib/api'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {documentTitleParts} from '@/lib/document-title'
import {operationSearchParams,emptyOperationFilters,type OperationFilters} from '../lib/operation-search'
import {eventNames} from './BusinessDocumentTools'
import './RecentOperations.css'
import {OperationTimePicker} from './OperationTimePicker'
type Operation={id:number;at:number;actor:string;actor_department?:string;action:string;document_name:string;note:string;recipient:string}
type Results={items:Operation[];total:number;page:number;page_size:number}
// Color and icon describe the recorded action, not the document's current state.
function operationAppearance(action:string){
 if(['publish','publish_version','approve','approve_publish','minor_correction_activated','restore'].includes(action))return {tone:'success',Icon:Check}
 if(['share','make_public','make_internal'].includes(action))return {tone:'access',Icon:KeyRound}
 if(['return','auto_publish_blocked','minor_correction_conflict'].includes(action))return {tone:'attention',Icon:Undo2}
 if(['purge','purged','purge_started','trash'].includes(action))return {tone:'removal',Icon:Trash2}
 if(['submitted','resubmit','minor_correction_declared'].includes(action))return {tone:'neutral',Icon:Upload}
 return {tone:'neutral',Icon:History}
}
function OperationRecord({event}:{event:Operation}){
 const name=demoIdentityName(event.actor)||event.actor
 const date=new Date(event.at*1000)
 const {tone,Icon}=operationAppearance(event.action)
 return <tr>
  <td><time className="operation-record-time" dateTime={date.toISOString()}><span>{date.toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'})}</span><strong>{date.toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})}</strong></time></td>
  <td><div className="operation-record-person" title={event.actor}><span className="operation-person-avatar" aria-hidden="true">{Array.from(name)[0]}</span><div className="operation-person-info"><span>{name}</span>{event.actor_department&&<span className="operation-person-department" title="当前所属部门">{event.actor_department}</span>}</div></div></td>
  <td><span className={'operation-record-badge operation-record-badge--'+tone}><Icon size={13} aria-hidden="true"/>{eventNames[event.action]||'资料处理'}</span></td>
  <td><div className="operation-record-document"><FileText size={17} aria-hidden="true"/><div><p className="operation-record-title">{documentTitleParts(event.document_name).title}</p>{(event.recipient||event.note)&&<div className="operation-record-details">{event.recipient&&<p>{event.action==='revoke_share'?'撤销借阅：':'授权给：'}{demoIdentityName(event.recipient)||event.recipient}</p>}{event.note&&<p>{event.note}</p>}</div>}</div></div></td>
 </tr>
}
export function RecentOperations(){
 const [events,setEvents]=useState<Operation[]>([]),[loaded,setLoaded]=useState(false),[error,setError]=useState('')
 const [filters,setFilters]=useState<OperationFilters>(emptyOperationFilters),[query,setQuery]=useState(''),[page,setPage]=useState(1),[total,setTotal]=useState(0),[validation,setValidation]=useState('')
 const pages=Math.max(1,Math.ceil(total/8))
 useEffect(()=>{let active=true,sequence=0;setLoaded(false);setError('');async function load(){const request=++sequence;try{const data=await api.get<Results>('/api/business/operations?'+query+'&page='+page);if(active&&request===sequence){const last=Math.max(1,Math.ceil(data.total/8));if(page>last){setPage(last);return}setEvents(data.items);setTotal(data.total);setLoaded(true);setError('')}}catch(e){if(active&&request===sequence){setError((e as Error).message);setLoaded(true)}}}void load();const timer=setInterval(load,8000);return()=>{active=false;clearInterval(timer)}},[query,page])
 function update<K extends keyof OperationFilters>(key:K,value:OperationFilters[K]){setFilters(current=>({...current,[key]:value}));setValidation('')}
 function search(){try{setQuery(operationSearchParams(filters));setPage(1);setValidation('')}catch(e){setValidation((e as Error).message)}}
 return <section className="recent-operations" aria-labelledby="recent-operations-heading">
 <header><h2 id="recent-operations-heading">最近操作记录</h2><span>{loaded&&!error?`共 ${total} 条文档操作`:'文档操作记录'}</span></header>
 <form className="operation-search" onSubmit={e=>{e.preventDefault();search()}}>
   <div className="operation-search-fields">
     <label>操作人<input placeholder="搜索姓名或账号" value={filters.actor} maxLength={100} onChange={e=>update('actor',e.target.value)}/></label>
     <label>文件<input placeholder="搜索文件名称、编号或文件 ID" value={filters.document} maxLength={200} onChange={e=>update('document',e.target.value)}/></label>
     <label className="operation-time-mode">时间（北京时间）<select aria-label="时间（北京时间）" value={filters.mode} onChange={e=>update('mode',e.target.value as OperationFilters['mode'])}><option value="all">全部时间</option><option value="date">指定日期</option><option value="range">自选时间段</option></select></label>
     <div className="operation-search-actions"><button type="submit" className="dm-primary"><Search size={14}/>查询</button><button type="button" onClick={()=>{setFilters(emptyOperationFilters);setQuery('');setPage(1);setValidation('')}}>重置</button></div>
   </div>
   {filters.mode==='date'&&<div className="operation-date-fields"><OperationTimePicker label="查询日期" value={filters.date} onChange={value=>update('date',value)}/></div>}
   {filters.mode==='range'&&<div className="operation-date-fields"><OperationTimePicker label="开始时间" value={filters.start} onChange={value=>update('start',value)} withTime/><ArrowRight className="operation-range-arrow" size={16} aria-hidden="true"/><OperationTimePicker label="结束时间" value={filters.end} onChange={value=>update('end',value)} withTime end/></div>}
   {validation&&<p role="alert" className="operation-filter-error">{validation}</p>}
 </form>
 <div className="recent-operations-list" aria-busy={!loaded}>{error?<p role="alert" className="recent-operations-empty">暂时无法读取记录：{error}</p>:!loaded?<p role="status" className="recent-operations-empty">正在读取操作记录…</p>:!events.length?<p className="recent-operations-empty">{query?'没有符合条件的操作记录，可调整筛选条件。':'暂无文档操作记录。'}</p>:<table className="operation-record-table" aria-label="文档操作记录"><colgroup><col className="operation-column-time"/><col className="operation-column-person"/><col className="operation-column-action"/><col/></colgroup><thead><tr><th scope="col">操作时间 <span>· 北京时间</span></th><th scope="col">操作人</th><th scope="col">操作类型</th><th scope="col">相关文件 / 说明</th></tr></thead><tbody>{events.map(event=><OperationRecord key={event.id} event={event}/>)}</tbody></table>}</div>
 {loaded&&!error&&total>0&&<nav className="operation-pagination" aria-label="操作记录分页"><span>第 {page} / {pages} 页 · 每页 8 条</span><button type="button" aria-label="上一页操作记录" disabled={page<=1} onClick={()=>setPage(p=>p-1)}><ChevronLeft size={14}/>上一页</button><button type="button" aria-label="下一页操作记录" disabled={page>=pages} onClick={()=>setPage(p=>p+1)}>下一页<ChevronRight size={14}/></button></nav>}
 </section>
}
