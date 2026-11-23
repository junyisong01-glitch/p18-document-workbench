import {useEffect,useState} from 'react'
import {api} from '@/lib/api'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {documentTitleParts} from '@/lib/document-title'
import {eventNames} from './BusinessDocumentTools'
type Operation={id:number;at:number;actor:string;action:string;document_name:string;note:string;recipient:string}
export function RecentOperations(){
 const [events,setEvents]=useState<Operation[]>([]),[loaded,setLoaded]=useState(false),[error,setError]=useState('')
 useEffect(()=>{let active=true;async function load(){try{const data=await api.get<Operation[]>('/api/business/recent-operations');if(active){setEvents(data);setLoaded(true);setError('')}}catch(e){if(active)setError((e as Error).message)}}void load();const timer=setInterval(load,8000);return()=>{active=false;clearInterval(timer)}},[])
 return <section className="recent-operations" aria-labelledby="recent-operations-heading"><header><h2 id="recent-operations-heading">最近操作记录</h2><span>最近 8 条文档操作</span></header><div className="recent-operations-list">{error?<p role="alert" className="recent-operations-empty">暂时无法读取记录：{error}</p>:!loaded?<p role="status" className="recent-operations-empty">正在读取操作记录…</p>:!events.length?<p className="recent-operations-empty">暂无文档操作记录。</p>:<ol>{events.map(event=><li key={event.id}><time dateTime={new Date(event.at*1000).toISOString()}>{new Date(event.at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})}</time><strong title={event.actor}>{demoIdentityName(event.actor)||event.actor}</strong><span className="recent-operation-action">{eventNames[event.action]||'资料处理'}</span><p><span>《{documentTitleParts(event.document_name).title}》</span>{event.recipient&&<span> · {event.action==='revoke_share'?'撤销':'授权给'}{demoIdentityName(event.recipient)||event.recipient}</span>}{event.note&&<span className="recent-operation-note"> · {event.note}</span>}</p></li>)}</ol>}</div></section>
}
