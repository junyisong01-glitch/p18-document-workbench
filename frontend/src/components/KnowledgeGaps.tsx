import {useEffect,useState} from 'react'
import {Link} from 'react-router'
import {api} from '@/lib/api'
import {useSession} from '@/lib/session'
type Gap={id:string;question:string;status:string;note:string;updated:number;document:{id:string;name:string}|null}
const labels:Record<string,string>={open:'已记录',in_progress:'处理中',resolved:'已补充',closed:'已关闭'}
export function KnowledgeGapList(){
 const {user}=useSession(),head=user?.accessRole==='supervisor'
 const [rows,setRows]=useState<Gap[]>([]),[error,setError]=useState(''),[loaded,setLoaded]=useState(false)
 useEffect(()=>{let active=true;api.get<Gap[]>('/api/business/gaps').then(data=>{if(active){setRows(data);setLoaded(true)}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[])
 return <details className="rounded-xl border border-border bg-card p-5"><summary className="cursor-pointer text-sm">历史问题记录{loaded?' · '+rows.length+' 条':''}</summary><p className="my-3 text-xs leading-6 text-muted-foreground">旧记录及原处理结果保留，{head?'仅显示原本允许你查看的部门记录':'仅显示你记录的问题'}，不再按人数排行或作为补资料待办。新问题请从回答下提交反馈。</p>{error&&<p role="alert">{error}</p>}{!loaded&&!error?<p>正在读取历史记录…</p>:rows.map(row=><article key={row.id} className="space-y-2 border-t border-border py-4 text-sm"><h3>{row.question}</h3><p className="text-xs text-muted-foreground">{labels[row.status]} · {new Date(row.updated*1000).toLocaleDateString('zh-CN')}</p>{row.note&&<p className="whitespace-pre-wrap text-xs leading-6">原处理说明：{row.note}</p>}{row.document&&<Link className="text-xs text-primary" to={'/documents?search='+encodeURIComponent(row.document.id)}>原关联资料：{row.document.name}</Link>}</article>)}</details>
}
