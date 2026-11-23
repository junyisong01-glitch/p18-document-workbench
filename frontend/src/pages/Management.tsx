import {Link,useSearchParams} from 'react-router'
import {PageHeader} from '@/components/bits'
import {PersonnelRoles} from '@/components/PersonnelRoles'
const sections=[
 {title:'授权与公开范围',items:[['跨部门授权与公开设置','选择资料，在“更多”中授权指定人员、设置公司内部共享或对外公开。','/documents'],['查看我的身份','查看当前账号与权限信息。','/identity']]},
 {title:'人员管理',items:[['人员职责','设置部门主管、员工职责与所属部门。','/management?view=people'],['邀请建号','邀请员工或访客使用知识库。','/management?invite=1']]},
 {title:'资料管理与追溯',items:[['紧急下架与操作记录','找到资料，在“更多”中紧急下架或查看操作记录；下架须填写原因。','/documents'],['已下架资料','查看已经停止提供检索的资料与操作记录。','/documents?view=已下架'],['回收站','恢复记录，或按要求确认后彻底删除。','/documents?view=回收站'],['历史归档','查看旧版资料与历史内容。','/documents?view=历史归档']]},
]
export default function Management(){
 const [params]=useSearchParams()
 if(params.get('view')==='people')return <div className="mx-auto max-w-6xl space-y-6">
  <Link to="/management" className="inline-flex text-xs text-muted-foreground hover:text-primary">← 权限与人员管理</Link>
  <PageHeader kicker="Management" title="人员职责" desc="管理人员的职责分工与所属部门。" extra={<Link to="/management?view=people&invite=1" className="dm-primary">邀请新人</Link>}/>
  <PersonnelRoles/>
 </div>
 return <div className="mx-auto max-w-6xl space-y-8"><PageHeader kicker="Management" title="权限与人员管理" desc="管理全公司授权、人员职责和资料处置。普通资料检查通过后自动发布，风险资料由审核人处理。"/>
 <p className="border-l-2 border-primary/50 pl-3 text-sm leading-7 text-muted-foreground">部门主管可将本部门普通资料授权给指定内部人员；机密资料授权、全公司共享与对外公开由管理层处理。阅读授权不包含修改、发布或再次授权。</p>
 {sections.map(section=><section key={section.title} className="space-y-3"><h2 className="text-base font-semibold">{section.title}</h2><div className="divide-y rounded-xl border border-border bg-card">{section.items.map(([title,description,to])=><Link key={title} to={to} className="flex items-center justify-between gap-6 px-6 py-5 hover:bg-secondary/30"><div><h3 className="text-sm font-medium">{title}</h3><p className="mt-2 text-xs leading-6 text-muted-foreground">{description}</p></div><span aria-hidden="true">→</span></Link>)}</div></section>)}
 </div>}
