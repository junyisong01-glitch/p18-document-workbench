import {useEffect,useState} from 'react'
import {Link} from 'react-router'
import {ArrowUpRight,FileUp,ShieldCheck} from 'lucide-react'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {documentTitleParts} from '@/lib/document-title'
import {canReviewSubmission} from '@/lib/document-workflow'
import {api} from '@/lib/api'
import {useSession} from '@/lib/session'
import {ManagerDashboard} from './ManagerDashboard'
import {WorkflowBadge,type BusinessRow} from './BusinessPresentation'
export function BusinessDashboard(){
 const {user}=useSession(),boss=user?.accessRole==='boss',head=user?.accessRole==='supervisor',guest=user?.accessRole==='guest'
 const [rows,setRows]=useState<BusinessRow[]>([]),[loaded,setLoaded]=useState(false),[error,setError]=useState('')
 useEffect(()=>{let active=true;async function load(){try{const next=await api.get<BusinessRow[]>('/api/business/documents');if(active){setRows(next);setLoaded(true);setError('')}}catch(e){if(active)setError((e as Error).message)}}void load();const timer=setInterval(load,8000);return()=>{active=false;clearInterval(timer)}},[boss,head])
 const current=rows.filter(r=>r.workflow.status==='published'&&!r.workflow.archived&&!r.workflow.deleted)
 const manageable=rows.filter(r=>!r.workflow.deleted&&!r.workflow.archived&&(boss||head&&r.department===user?.role.dept))
 const parseIssues=manageable.filter(r=>r.publication_stage==='解析异常'),pending=manageable.filter(r=>canReviewSubmission(r,user?.username||'',!!boss,!!head,user?.role.dept||''))
 const cards=head?[
  {label:'内容待审',value:pending.length,hint:'判断能否发布：查看送审原因，批准或退回',to:'/documents?view=待我审核'},
  {label:'解析异常',value:parseIssues.length,hint:'处理文件读取问题：更换文件、核对或重试',to:'/documents?view=部门异常'},
 ]:[{label:'可查阅资料',value:current.length,hint:guest?'当前对外公开资料':'当前账号获准的已发布资料',to:'/documents'},...(!guest?[{label:'我的在途提交',value:rows.filter(r=>r.workflow.owner===user?.username&&!r.workflow.deleted&&!r.workflow.archived&&!['published','withdrawn','taken_down'].includes(r.workflow.status)).length,hint:'查看进度、处理异常或修改退回资料',to:'/documents?view=我的提交'}]:[])]
 const queue=boss||head?[...pending,...parseIssues].slice(0,5):rows.filter(r=>r.workflow.owner===user?.username&&!r.workflow.deleted&&!r.workflow.archived&&!['published','withdrawn','taken_down'].includes(r.workflow.status)).slice(0,5)
 if(boss)return <ManagerDashboard rows={rows} loaded={loaded} error={error}/>
 return <div className="mx-auto max-w-6xl space-y-8">
  <header className="flex flex-wrap items-end justify-between gap-5 border-b border-border pb-6"><div><p className="mb-2 text-xs text-muted-foreground">{head?user?.role.dept+' · 主管工作台':guest?'公开资料':'我的工作台'}</p><h1 className="text-2xl font-semibold">{head?'处理需要审核和核对的资料':'你好，'+(demoIdentityName(user?.username)||user?.role.name)}</h1><p className="mt-3 text-sm leading-7 text-muted-foreground">{head?'普通资料检查通过后自动发布，你主要处理风险资料和解析异常。':guest?'只能查看对外公开资料。':'直接提问，或继续处理你提交的资料。'}</p></div><div className="flex gap-3">{user?.canCreateAccounts&&<Link className="rounded-md border border-border px-4 py-2 text-sm" to="/workbench?invite=1">邀请新人</Link>}{!guest&&<Link className="dm-primary" to="/documents?view=上传资料"><FileUp size={15}/>上传资料</Link>}</div></header>
  {error&&<p role="alert" className="text-sm text-red-700">{error}</p>}
  <section aria-label="业务统计" className="grid gap-4 sm:grid-cols-2">{cards.map(card=><Link key={card.label} to={card.to} className="rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/50"><div className="flex items-center justify-between text-sm"><span>{card.label}</span><ArrowUpRight size={15} className="text-muted-foreground"/></div><p className="my-4 text-4xl font-semibold tabular-nums">{loaded?card.value:'—'}</p><p className="text-xs leading-6 text-muted-foreground">{card.hint}</p></Link>)}</section>
  {!guest&&<section className="space-y-4"><div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{boss?'风险与异常待办':head?'需要你处理的资料':'我的提交进度'}</h2><Link className="text-xs text-primary" to={'/documents?view='+encodeURIComponent(boss||head?'待我审核':'我的提交')}>进入文档管理 →</Link></div><div className="divide-y rounded-xl border border-border bg-card">{!loaded?<p className="p-6 text-sm text-muted-foreground">正在读取状态…</p>:queue.length?queue.map(row=><Link key={row.id} to={'/documents?view='+encodeURIComponent(boss||head?(row.publication_stage==='解析异常'?'部门异常':'待我审核'):'我的提交')} className="flex flex-wrap items-center justify-between gap-4 p-5 hover:bg-secondary/20"><div><p className="text-sm font-medium">{documentTitleParts(row.name).title}</p><p className="mt-2 text-xs text-muted-foreground">{row.review_reasons?.join('；')||row.parse_reasons?.join('；')||row.department}</p></div><WorkflowBadge row={row}/></Link>):<p className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><ShieldCheck size={17}/>当前没有待处理事项。</p>}</div></section>}
 </div>
}
