import {useEffect,useState} from 'react'
import {Search,ChevronLeft,ChevronRight} from 'lucide-react'
import {api} from '@/lib/api'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {documentTitleParts} from '@/lib/document-title'
import {operationSearchParams,emptyOperationFilters,type OperationFilters} from '../lib/operation-search'
import {eventNames} from './BusinessDocumentTools'
import './RecentOperations.css'
type Operation={id:number;at:number;actor:string;action:string;document_name:string;note:string;recipient:string}
type Results={items:Operation[];total:number;page:number;page_size:number}
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
   {filters.mode==='date'&&<div className="operation-date-fields"><label>查询日期<input type="date" value={filters.date} onChange={e=>update('date',e.target.value)}/></label></div>}
   {filters.mode==='range'&&<div className="operation-date-fields"><label>开始时间<input type="datetime-local" value={filters.start} onChange={e=>update('start',e.target.value)}/></label><span>至</span><label>结束时间<input type="datetime-local" value={filters.end} onChange={e=>update('end',e.target.value)}/></label></div>}
   {validation&&<p role="alert" className="operation-filter-error">{validation}</p>}
 </form>
 <div className="recent-operations-list" aria-busy={!loaded}>{error?<p role="alert" className="recent-operations-empty">暂时无法读取记录：{error}</p>:!loaded?<p role="status" className="recent-operations-empty">正在读取操作记录…</p>:!events.length?<p className="recent-operations-empty">{query?'没有符合条件的操作记录，可调整筛选条件。':'暂无文档操作记录。'}</p>:<ol>{events.map(event=><li key={event.id}><time dateTime={new Date(event.at*1000).toISOString()}>{new Date(event.at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})}</time><strong title={event.actor}>{demoIdentityName(event.actor)||event.actor}</strong><span className="recent-operation-action">{eventNames[event.action]||'资料处理'}</span><p><span>《{documentTitleParts(event.document_name).title}》</span>{event.recipient&&<span> · {event.action==='revoke_share'?'撤销':'授权给'}{demoIdentityName(event.recipient)||event.recipient}</span>}{event.note&&<span className="recent-operation-note"> · {event.note}</span>}</p></li>)}</ol>}</div>
 {loaded&&!error&&total>0&&<nav className="operation-pagination" aria-label="操作记录分页"><span>第 {page} / {pages} 页 · 每页 8 条</span><button type="button" aria-label="上一页操作记录" disabled={page<=1} onClick={()=>setPage(p=>p-1)}><ChevronLeft size={14}/>上一页</button><button type="button" aria-label="下一页操作记录" disabled={page>=pages} onClick={()=>setPage(p=>p+1)}>下一页<ChevronRight size={14}/></button></nav>}
 </section>
}
