import {useEffect,useState} from 'react'
import {Link} from 'react-router'
import {ArrowUpRight,FileUp,ShieldCheck} from 'lucide-react'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {documentTitleParts} from '@/lib/document-title'
import {canReviewSubmission} from '@/lib/document-workflow'
import {api} from '@/lib/api'
import {useSession} from '@/lib/session'
import {BUSINESS_DEPARTMENTS,WorkflowBadge,type BusinessRow} from './BusinessPresentation'
export function BusinessDashboard(){
 const {user}=useSession(),boss=user?.accessRole==='boss',head=user?.accessRole==='supervisor',guest=user?.accessRole==='guest'
 const [rows,setRows]=useState<BusinessRow[]>([]),[loaded,setLoaded]=useState(false),[error,setError]=useState('')
 useEffect(()=>{let active=true;async function load(){try{const next=await api.get<BusinessRow[]>('/api/business/documents');if(active){setRows(next);setLoaded(true);setError('')}}catch(e){if(active)setError((e as Error).message)}}void load();const timer=setInterval(load,8000);return()=>{active=false;clearInterval(timer)}},[boss,head])
 const current=rows.filter(r=>r.workflow.status==='published'&&!r.workflow.archived&&!r.workflow.deleted)
 const manageable=rows.filter(r=>!r.workflow.deleted&&!r.workflow.archived&&(boss||head&&r.department===user?.role.dept))
 const parseIssues=manageable.filter(r=>r.publication_stage==='解析异常'),pending=manageable.filter(r=>canReviewSubmission(r,user?.username||'',!!boss,!!head,user?.role.dept||''))
 const cards=boss?[
  {label:'现行资料',value:current.length,hint:'已发布的公司资料',to:'/documents'},
  {label:'解析异常',value:parseIssues.length,hint:'更换文件、核对解析结果或重试',to:'/documents?view=部门异常'},
  {label:'待审核风险资料',value:pending.length,hint:'机密或命中风险检查',to:'/documents?view=待我审核'},
 ]:head?[
  {label:'内容待审',value:pending.length,hint:'判断能否发布：查看送审原因，批准或退回',to:'/documents?view=待我审核'},
  {label:'解析异常',value:parseIssues.length,hint:'处理文件读取问题：更换文件、核对或重试',to:'/documents?view=部门异常'},
 ]:[{label:'可查阅资料',value:current.length,hint:guest?'当前对外公开资料':'当前账号获准的已发布资料',to:'/documents'},...(!guest?[{label:'我的在途提交',value:rows.filter(r=>r.workflow.owner===user?.username&&!r.workflow.deleted&&!r.workflow.archived&&!['published','withdrawn','taken_down'].includes(r.workflow.status)).length,hint:'查看进度、退回原因和待发布资料',to:'/documents?view=我的提交'}]:[])]
 const queue=boss||head?[...pending,...parseIssues].slice(0,5):rows.filter(r=>r.workflow.owner===user?.username&&!r.workflow.deleted&&!r.workflow.archived&&!['published','withdrawn','taken_down'].includes(r.workflow.status)).slice(0,5)
 return <div className="mx-auto max-w-6xl space-y-8">
  <header className="flex flex-wrap items-end justify-between gap-5 border-b border-border pb-6"><div><p className="mb-2 text-xs text-muted-foreground">{boss?'管理层概览':head?user?.role.dept+' · 主管工作台':guest?'公开资料':'我的工作台'}</p><h1 className="text-2xl font-semibold">{boss?'掌握资料家底，关注待处理风险':head?'处理需要审核和核对的资料':'你好，'+(demoIdentityName(user?.username)||user?.role.name)}</h1><p className="mt-3 text-sm leading-7 text-muted-foreground">{boss?'处理跨部门授权、主管提交的风险资料和人员职责；普通资料无需逐份审批。':head?'普通资料由上传者发布，你主要处理风险资料和解析异常。':guest?'只能查看对外公开资料。':'直接提问，或继续处理你提交的资料。'}</p></div><div className="flex gap-3">{!guest&&<Link className="dm-primary" to="/documents?view=上传资料"><FileUp size={15}/>上传资料</Link>}</div></header>
  {error&&<p role="alert" className="text-sm text-red-700">{error}</p>}
  <section aria-label="业务统计" className={'grid gap-4 sm:grid-cols-2 '+(boss?'xl:grid-cols-3':'xl:grid-cols-2')}>{cards.map(card=><Link key={card.label} to={card.to} className="rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/50"><div className="flex items-center justify-between text-sm"><span>{card.label}</span><ArrowUpRight size={15} className="text-muted-foreground"/></div><p className="my-4 text-4xl font-semibold tabular-nums">{loaded?card.value:'—'}</p><p className="text-xs leading-6 text-muted-foreground">{card.hint}</p></Link>)}</section>
  {boss&&<Link to="/management" className="flex items-center justify-between rounded-xl border border-border bg-card px-6 py-5"><div><h2 className="text-base font-semibold">权限与人员管理</h2><p className="mt-2 text-xs text-muted-foreground">授权与公开范围、人员职责、紧急下架和资料记录</p></div><ArrowUpRight size={18}/></Link>}
  {boss&&<section id="department-overview" className="space-y-4"><h2 className="text-lg font-semibold">各部门资料概览</h2><div className="overflow-x-auto rounded-xl border border-border bg-card"><table className="w-full text-left text-sm"><thead className="border-b bg-secondary/40 text-xs text-muted-foreground"><tr>{['部门','现行资料','可检索'].map(t=><th className="p-4 font-normal" key={t}>{t}</th>)}</tr></thead><tbody>{BUSINESS_DEPARTMENTS.map(dept=><tr key={dept} className="border-b last:border-0"><th className="p-4 font-medium">{dept}</th><td className="p-4">{loaded?current.filter(r=>r.department===dept).length:'—'}</td><td className="p-4">{loaded?current.filter(r=>r.department===dept&&r.technical_index_ready).length:'—'}</td></tr>)}</tbody></table></div></section>}
  {!guest&&<section className="space-y-4"><div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{boss?'风险与异常待办':head?'需要你处理的资料':'我的提交进度'}</h2><Link className="text-xs text-primary" to={'/documents?view='+encodeURIComponent(boss||head?'待我审核':'我的提交')}>进入文档管理 →</Link></div><div className="divide-y rounded-xl border border-border bg-card">{!loaded?<p className="p-6 text-sm text-muted-foreground">正在读取状态…</p>:queue.length?queue.map(row=><Link key={row.id} to={'/documents?view='+encodeURIComponent(boss||head?(row.publication_stage==='解析异常'?'部门异常':'待我审核'):'我的提交')} className="flex flex-wrap items-center justify-between gap-4 p-5 hover:bg-secondary/20"><div><p className="text-sm font-medium">{documentTitleParts(row.name).title}</p><p className="mt-2 text-xs text-muted-foreground">{row.review_reasons?.join('；')||row.parse_reasons?.join('；')||row.department}</p></div><WorkflowBadge row={row}/></Link>):<p className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><ShieldCheck size={17}/>当前没有待处理事项。</p>}</div></section>}
 </div>
}
