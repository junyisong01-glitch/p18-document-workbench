import { demoIdentityName } from '@/lib/demo-identity-names'
import {useEffect,useState} from 'react'
import {Link} from 'react-router'
import {ArrowRight,FileUp,Inbox,MessageSquareText,UserRoundPlus} from 'lucide-react'
import {api} from '@/lib/api'
import {useSession} from '@/lib/session'
import {PageHeader} from './bits'
import {BUSINESS_DEPARTMENTS,WorkflowBadge,businessRoleName,type BusinessRow} from './BusinessPresentation'
export function BusinessDashboard(){
 const {user}=useSession(),boss=user?.accessRole==='boss',head=user?.accessRole==='supervisor',guest=user?.accessRole==='guest'
 const [rows,setRows]=useState<BusinessRow[]>([]),[loaded,setLoaded]=useState(false),[error,setError]=useState('')
 useEffect(()=>{let active=true;async function load(){try{const next=await api.get<BusinessRow[]>('/api/business/documents');if(active){setRows(next);setLoaded(true);setError('')}}catch(e){if(active)setError((e as Error).message)}}void load();const timer=setInterval(load,8000);return()=>{active=false;clearInterval(timer)}},[])
 const current=rows.filter(r=>r.workflow.status==='published'&&!r.workflow.archived&&!r.workflow.deleted)
 const mine=rows.filter(r=>r.workflow.owner===user?.username&&!r.workflow.deleted&&!r.workflow.archived)
 const manageable=rows.filter(r=>!r.workflow.deleted&&!r.workflow.archived&&(boss||head&&r.department===user?.role.dept))
 const parseIssues=manageable.filter(r=>r.publication_stage==='解析异常')
 const pending=manageable.filter(r=>r.publication_stage==='内容待审')
 const ready=manageable.filter(r=>r.publication_stage==='待发布')
 const cards=boss||head?[
  {label:boss?'已发布 · 全公司':'已发布 · 获准范围',value:current.length,hint:'当前生效资料，索引有效后才可检索'},
  {label:'解析异常',value:parseIssues.length,hint:'检查提取失败或结构不确定的资料'},
  {label:'内容待审',value:pending.length,hint:'查看密级和敏感检查的送审原因'},
  {label:'待发布',value:ready.length,hint:'审核与索引均就绪后发布'},
  {label:'回收站',value:rows.filter(r=>r.workflow.deleted).length,hint:boss?'先软删、完整ID确认后才可彻底删除':'本部门维护，物理删除仅管理层负责人可操作'},
 ]:[{label:'当前获准发布件',value:current.length,hint:'按实际读权返回，不代表全库数量'},{label:'可检索',value:current.filter(r=>r.technical_index_ready).length,hint:'当前发布且索引有效'},{label:'我的在途提交',value:mine.filter(r=>r.workflow.status!=='published').length,hint:guest?'访客没有提交权限':'处理状态与退回原因可随时查看'},{label:'历史资料',value:rows.filter(r=>r.workflow.archived&&!r.workflow.deleted).length,hint:'仅供高级查阅，不参与RAG'}]
 const queues=boss||head?[...parseIssues,...pending,...ready].slice(0,5):mine.filter(r=>r.workflow.status!=='published').slice(0,5)
 const entries=[...(!guest?[{to:'/documents?view='+encodeURIComponent('上传资料'),icon:FileUp,title:'上传资料',desc:boss?'选择五部门之一提交，保留原件和版本。':'上传本部门资料，检查通过后可发布。'}]:[]),...(boss||head?[{to:'/documents?view='+encodeURIComponent('内容待审'),icon:Inbox,title:'内容待审',desc:'审核机密或命中敏感检查的资料。'},{to:'/documents?view='+encodeURIComponent('解析异常'),icon:Inbox,title:'解析异常',desc:'核对解析失败、内容缺失和表格结构疑点。'}]:!guest?[{to:'/documents?view='+encodeURIComponent('我的提交'),icon:Inbox,title:'我的提交',desc:'查看进度、退回原因、勘误和新版本。'}]:[]),{to:'/qa',icon:MessageSquareText,title:'知识问答',desc:'提问后自动查找获准资料，查看回答、来源和原文。'},...(user?.canCreateAccounts?[{to:'/documents?view='+encodeURIComponent('邀请建号'),icon:UserRoundPlus,title:'邀请新人',desc:'为员工或访客发一次性邀请，不直接授予主管权限。'}]:[])]
 return <div className="space-y-7"><PageHeader kicker="Dashboard · 启辰智造知识库" title={demoIdentityName(user?.username) ?? user?.role.name ?? '工作台'} desc={`${businessRoleName(user?.accessRole)} · ${user?.role.dept}。${boss?'全公司资料按部门组织，支持上传、审核和发布。':head?'处理本部门资料。本人提交的高风险文档由管理层负责人审核。':guest?'只读公司公开和单独获准资料。':'提交本部门资料，追踪本人进度；跨部门读取须明确获准。'}`}/>
 {error&&<p role="alert" className="text-sm text-[hsl(4_72%_36%)]">{error}</p>}
 <section aria-label="业务统计" className="grid grid-cols-2 gap-4 xl:grid-cols-4">{cards.map(c=><div key={c.label} className="rounded-lg border border-border bg-card p-5"><p className="text-xs text-muted-foreground">{c.label}</p><p className="mt-3 font-mono2 text-3xl font-semibold">{loaded?c.value:'—'}</p><p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">{c.hint}</p></div>)}</section>
 <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{entries.map(e=><Link key={e.title} to={e.to} className="group flex items-start gap-4 rounded-lg border border-border bg-card p-5 transition-colors hover:border-[hsl(12_74%_42%/0.5)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"><e.icon className="mt-0.5 size-5 shrink-0 text-[hsl(12_74%_42%)]"/><div><h2 className="text-sm font-semibold">{e.title}</h2><p className="mt-2 text-xs leading-relaxed text-muted-foreground">{e.desc}</p></div><ArrowRight className="ml-auto mt-1 size-4 shrink-0 text-muted-foreground"/></Link>)}</section>
 {boss&&<section className="space-y-3"><h2 className="text-sm font-semibold">五部门资料概览</h2><div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">{BUSINESS_DEPARTMENTS.map(d=><div key={d} className="rounded-lg border border-border bg-card p-4"><h3 className="text-xs font-medium">{d}</h3><p className="mt-3 font-mono2 text-xl">{loaded?current.filter(r=>r.department===d).length:'—'}</p><p className="mt-1 text-[10px] text-muted-foreground">当前发布件</p></div>)}</div><p className="text-[11px] text-muted-foreground">部门用于组织浏览，不替代文档级读取权限。完整分类见文档管理。</p></section>}
 {!guest&&<section className="space-y-3"><h2 className="text-sm font-semibold">{boss||head?'待处理队列':'我的提交进度'}</h2><div className="overflow-hidden rounded-lg border border-border bg-card">{!loaded?<p className="p-6 text-xs text-muted-foreground">正在读取服务端状态…</p>:!queues.length?<p className="p-6 text-xs text-muted-foreground">当前没有待处理事项。上传新资料后可在这里跟踪。</p>:queues.map(r=><Link key={r.id} to={'/documents?view='+encodeURIComponent(boss||head?r.publication_stage||'我的提交':'我的提交')} className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4 last:border-0 hover:bg-secondary/20"><div><p className="text-sm font-medium">{r.name}</p><p className="mt-1 text-[11px] text-muted-foreground">{r.department} · {r.version} · {r.workflow.owner}</p></div><WorkflowBadge row={r}/></Link>)}</div></section>}
 <p className="border-l-2 border-border pl-4 text-xs leading-relaxed text-muted-foreground">统计仅来自当前账号获准的服务端记录。启辰资料全员禁止外部AI；公开、借阅和管理层负责人身份均不豁免。</p>
 </div>
}
