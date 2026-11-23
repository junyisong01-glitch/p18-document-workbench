import {KnowledgeWelcome} from './KnowledgeWelcome'
import {RecentOperations} from './RecentOperations'
import {Link} from 'react-router'
import {ArrowRight,FileUp,Inbox,MessageSquareText,UserRoundPlus,Users,Check} from 'lucide-react'
import {useSession} from '@/lib/session'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {documentTitleParts} from '@/lib/document-title'
import {canReviewSubmission} from '@/lib/document-workflow'
import {BUSINESS_DEPARTMENTS,WorkflowBadge,type BusinessRow} from './BusinessPresentation'
import './ManagerDashboard.css'

export function ManagerDashboard({rows,loaded,error}:{rows:BusinessRow[];loaded:boolean;error:string}){
 const {user}=useSession()
 const current=rows.filter(r=>r.workflow.status==='published'&&!r.workflow.archived&&!r.workflow.deleted)
 const active=rows.filter(r=>!r.workflow.archived&&!r.workflow.deleted)
 const parseIssues=active.filter(r=>r.publication_stage==='解析异常')
 const pending=active.filter(r=>canReviewSubmission(r,user?.username||'',true,false,user?.role.dept||''))
 const stats=[
  {label:'已发布 · 全公司',value:current.length,hint:'当前生效资料，索引有效后可检索',view:'可查阅资料'},
  {label:'解析异常',value:parseIssues.length,hint:'核对文件读取失败或内容缺失的问题',view:'部门异常'},
  {label:'内容待审',value:pending.length,hint:'查看机密与敏感内容的送审原因',view:'待我审核'},
  {label:'回收站',value:rows.filter(r=>r.workflow.deleted).length,hint:'恢复已删除记录，或确认后彻底删除',view:'回收站'},
 ]
 const shortcuts=[
  {title:'上传资料',hint:'提交新资料，或更新已有资料的版本。',to:'/documents?view=上传资料',icon:FileUp},
  {title:'内容待审',hint:'审核机密或命中敏感检查的资料。',to:'/documents?view=待我审核',icon:Inbox},
  {title:'解析异常',hint:'核对解析失败、内容缺失和表格结构疑点。',to:'/documents?view=部门异常',icon:Inbox},
  {title:'知识问答',hint:'查找获准资料，查看回答、来源和原文。',to:'/qa',icon:MessageSquareText},
  ...(user?.canCreateAccounts?[{title:'邀请新人',hint:'为员工或访客生成一次性邀请。',to:'/workbench?invite=1',icon:UserRoundPlus}]:[]),
  {title:'人员职责',hint:'调整人员职责与所属部门。',to:'/management?view=people',icon:Users},
 ]
 const queue=[...pending,...parseIssues].filter((r,index,all)=>all.findIndex(item=>item.id===r.id)===index).slice(0,5)
 return <div className="manager-dashboard">
  <header className="manager-dashboard-heading"><p>工作台 / 全公司概览</p><h1>你好，{demoIdentityName(user?.username)||user?.role.name}</h1><div>查看团队知识动态，处理资料审核与协作事项。</div></header>
  <KnowledgeWelcome/>
  {error&&<p role="alert" className="text-sm text-red-700">{error}</p>}
  <section aria-label="业务统计" className="manager-stats">{stats.map(stat=><Link key={stat.label} to={'/documents?view='+encodeURIComponent(stat.view)} className="manager-stat"><h2>{stat.label}</h2><strong>{loaded?stat.value:'—'}</strong><p>{stat.hint}</p></Link>)}</section>
  <section aria-label="快捷入口" className="manager-shortcuts"><h2 className="lx-section-title">常用功能<span>让日常协作更简单</span></h2>{shortcuts.map(item=><Link to={item.to} key={item.title} className="manager-shortcut"><item.icon size={22} strokeWidth={1.7}/><div><h2>{item.title}</h2><p>{item.hint}</p></div><ArrowRight size={19}/></Link>)}</section>
  <section aria-labelledby="department-overview-title" className="manager-departments"><h2 id="department-overview-title">部门知识空间</h2><div>{BUSINESS_DEPARTMENTS.map(department=><Link key={department} to={'/documents?department='+encodeURIComponent(department)}><h3>{department}</h3><strong>{loaded?current.filter(r=>r.department===department).length:'—'}</strong><p>当前发布件</p></Link>)}</div><p>按部门查看当前发布资料；具体查看权限仍以文档授权为准。</p></section>
  <section className="manager-queue" aria-labelledby="manager-queue-title"><h2 id="manager-queue-title">待处理队列</h2><div>{!loaded?<p className="manager-empty">正在读取状态…</p>:queue.length?queue.map(row=><Link key={row.id} to={'/documents?view='+encodeURIComponent(row.publication_stage==='解析异常'?'部门异常':'待我审核')}><div><h3>{documentTitleParts(row.name).title}</h3><p>{row.review_reasons?.join('；')||row.parse_reasons?.join('；')||row.department}</p></div><WorkflowBadge row={row}/></Link>):<p className="manager-empty"><Check size={17}/>当前没有待处理事项。</p>}</div></section>
  <RecentOperations/>
 </div>
}
