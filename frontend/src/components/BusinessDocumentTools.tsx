import {useEffect,useState} from 'react'
import * as Menu from '@radix-ui/react-dropdown-menu'
import {Check,MoreHorizontal,Search} from 'lucide-react'
import {api} from '@/lib/api'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {DocumentModal} from './DocumentLayout'
import {businessRoleName,type BusinessRow} from './BusinessPresentation'

export type DocumentAction={label:string;run:()=>void;danger?:boolean;disabled?:boolean}
export function DocumentMore({actions,compact=false}:{actions:DocumentAction[];compact?:boolean}){
 if(!actions.length)return null
 return <Menu.Root><Menu.Trigger asChild><button type="button" className={"dm-more-trigger "+(compact?"dm-more-compact":"")} aria-label="更多操作"><MoreHorizontal size={16}/>{!compact&&<span>更多</span>}</button></Menu.Trigger><Menu.Portal><Menu.Content align="end" sideOffset={6} className="dm-action-menu">{actions.map(a=><Menu.Item key={a.label} disabled={a.disabled} onSelect={a.run} className={'dm-menu-item '+(a.danger?'dm-menu-danger':'')}>{a.label}</Menu.Item>)}</Menu.Content></Menu.Portal></Menu.Root>
}

export function documentScope(row:BusinessRow){
 const b=row.workflow
 if(b.status!=='published'||b.archived||b.deleted)return {key:'unpublished',label:'未对检索开放',description:'仅上传者及有管理权限的人员查看；不进入当前问答。'}
 if(b.company_public)return {key:'external',label:'对外公开 · 含访客',description:'内部员工和外部访客均可检索、阅读与下载。'}
 if(b.company_internal)return {key:'company',label:'全公司内部 · 不含访客',description:'所有内部账号可查看，访客不可查看。'}
 if(b.restricted)return {key:'restricted',label:'机密 · 指定授权',description:'仅上传者、管理层负责人及明确获准人员查看；不自动向部门开放。'}
 if(b.legacy||b.read_jobs)return {key:'job',label:'岗位范围 · 按授权查看',description:'按照资料的岗位、部门规则及有效借阅授权查看。'}
 return {key:'department',label:'部门内部 · 可单独借阅',description:'归属部门内部可查看，其他部门需单独授权借阅；访客不可查看。'}
}
export const scopeOptions=[['','全部查看范围'],['external','对外公开（含访客）'],['company','全公司内部（不含访客）'],['department','部门内部（跨部门须授权）'],['job','岗位范围（按授权查看）'],['restricted','机密资料（指定授权）'],['unpublished','未对检索开放']]

type Person={username:string;role:string;department:string;job:string;granted:boolean;expires_at:number|null}
export function BorrowerPicker({id,revoke,value,onChange}:{id:string;revoke:boolean;value:string;onChange:(value:string)=>void}){
 const [people,setPeople]=useState<Person[]>([]),[query,setQuery]=useState(''),[loaded,setLoaded]=useState(false),[error,setError]=useState('')
 useEffect(()=>{let alive=true;api.get<Person[]>('/api/business/documents/'+id+'/borrowers').then(rows=>{if(alive){setPeople(rows);setLoaded(true)}}).catch(e=>{if(alive)setError((e as Error).message)});return()=>{alive=false}},[id])
 const eligible=people.filter(p=>revoke?p.granted:!p.granted),q=query.trim().toLowerCase()
 const filtered=eligible.filter(p=>[p.username,demoIdentityName(p.username)||'',p.department,p.job,businessRoleName(p.role)].join(' ').toLowerCase().includes(q))
 return <div className="space-y-3"><label className="dm-people-search"><Search size={16}/><input aria-label="搜索借阅人员" placeholder="搜索姓名、账号、部门或岗位" value={query} onChange={e=>setQuery(e.target.value)}/></label><p className="text-xs text-muted-foreground">{revoke?'只显示已有有效借阅授权的人员。撤销借阅不会取消其部门或岗位本身的读权。':'选择一名内部成员。授权后可阅读、检索和下载这份资料，不获得修改或发布权。'}</p>{error?<p role="alert" className="dm-form-error">{error}</p>:<div className="dm-people-list" role="group" aria-label={revoke?'可撤销借阅的人员':'可借阅人员'}>{!loaded?<p>正在读取人员…</p>:!filtered.length?<p>{eligible.length?'没有匹配的人员。':revoke?'这份资料暂无有效借阅授权。':'暂无可添加的内部成员。'}</p>:filtered.map(p=><button type="button" key={p.username} className="dm-person-option" aria-pressed={value===p.username} onClick={()=>onChange(p.username)}><span><strong>{demoIdentityName(p.username)||p.username}</strong><small>{p.username} · {p.department||'管理层'} · {p.job||businessRoleName(p.role)}</small></span>{value===p.username&&<Check size={17}/>}</button>)}</div>}{value&&<p className="text-xs">已选择：{demoIdentityName(value)||value}（{value}）</p>}</div>
}

const eventNames:Record<string,string>={submitted:'提交资料',approve:'审核通过',approve_publish:'审核并发布',publish:'发布入库',withdraw:'撤回提交',take_down:'下架资料',return:'退回修改',resubmit:'重新提交',retry_parse:'重试解析',retry_index:'重试索引',share:'授权借阅',revoke_share:'撤销借阅',make_public:'设为对外公开',revoke_public:'撤销对外公开',make_internal:'设为全公司内部可见',revoke_internal:'撤销公司内部共享',archive:'归档资料',trash:'移入回收站',restore:'从回收站恢复',purge:'彻底删除',purged:'彻底删除',minor_correction_declared:'提交轻量勘误',minor_correction_activated:'勘误已生效',minor_correction_conflict:'勘误与原版本冲突',cancel_correction:'取消勘误',replaced_submission:'已由重新上传的文件接续处理'}
type Audit={at:number;actor:string;action:string;body:string}
export function DocumentAudit({row,onClose}:{row:BusinessRow;onClose:()=>void}){
 const [events,setEvents]=useState<Audit[]>([]),[loaded,setLoaded]=useState(false),[error,setError]=useState('')
 useEffect(()=>{let alive=true;api.get<Audit[]>('/api/business/documents/'+row.id+'/audit').then(data=>{if(alive){setEvents(data);setLoaded(true)}}).catch(e=>{if(alive)setError((e as Error).message)});return()=>{alive=false}},[row.id])
 return <DocumentModal open title="操作记录" description={'查看“'+row.name+'”的处理人、时间和处理原因。'} onClose={onClose}>{error?<p role="alert">{error}</p>:!loaded?<p>正在读取记录…</p>:!events.length?<p className="text-sm text-muted-foreground">暂无操作记录。</p>:<ol className="dm-audit-list">{[...events].reverse().map((event,i)=>{let detail:{note?:string;reason?:string;username?:string}={};try{detail=JSON.parse(event.body)}catch{/* Legacy event without structured details. */}return <li key={i}><strong>{eventNames[event.action]||'资料处理'}</strong><p>{demoIdentityName(event.actor)||event.actor} · {new Date(event.at*1000).toLocaleString('zh-CN')}</p>{detail.username&&<p>借阅人员：{demoIdentityName(detail.username)||detail.username}（{detail.username}）</p>}{(detail.note||detail.reason)&&<p className="dm-audit-note">{detail.note||detail.reason}</p>}</li>})}</ol>}<div className="dm-modal-actions"><button type="button" className="dm-primary" onClick={onClose}>关闭</button></div></DocumentModal>
}
