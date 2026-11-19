export type DemoAccount={username:string;role:string;department:string;job:string;password_required:boolean}
// 姓名与顺序只用于演示展示；认证和权限始终使用服务端的原账号与角色。
const displayNames:Record<string,string>={
 demo_manager:'程一舟',
 qichen_rd_head:'林岚',qichen_prd_head:'赵启铭',qichen_fin_head:'沈知微',qichen_hr_head:'顾清',qichen_adm_head:'韩朔',
 qichen_rd:'陈叙',qichen_qa:'苏晚',qichen_ops:'陆既明',
 qichen_prd:'何见山',qichen_fin:'纪云舒',qichen_hr:'白芷',qichen_adm:'任重',qichen_guest:'访客',
}
const displayOrder=Object.keys(displayNames)
const departmentTitles:Record<string,string>={'研发部':'研发','生产制造部':'生产','财务部':'财务','人力资源部':'人事','行政安全部':'行政'}
function description(a:DemoAccount){
 if(a.role==='boss')return '老板 · 管理层 · 全局资料与人员职责'
 if(a.role==='guest')return '只读访客 · 无部门读权'
 const title=a.job||departmentTitles[a.department]||'部门'
 return title+'岗位'+(a.role==='supervisor'?'主管':'员工')+' · '+a.department
}
export function DemoIdentityCards({accounts,busy,onSelect,selectedUsername=''}:{accounts:DemoAccount[];busy:boolean;onSelect:(a:DemoAccount)=>void;selectedUsername?:string}){
 const groups=[
  {name:'管理层',hint:'',match:(a:DemoAccount)=>a.role==='boss'},
  {name:'部门主管',hint:'仅本部门管理，可审核本人提交并留审计；机密仍须明确读权。',match:(a:DemoAccount)=>a.role==='supervisor'},
  {name:'研发部员工',hint:'研发 / 测试 / 运维三个专业岗位，同属研发部。',match:(a:DemoAccount)=>a.role==='employee'&&a.department==='研发部'},
  {name:'其他部门员工',hint:'',match:(a:DemoAccount)=>a.role==='employee'&&a.department!=='研发部'},
  {name:'访客',hint:'无部门读权',match:(a:DemoAccount)=>a.role==='guest'},
 ]
 return <section aria-label="演示身份" className="mt-6 space-y-6 border-t border-dashed border-border pt-4">
  <div><h2 className="text-sm font-semibold">选择演示身份</h2><p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">演示身份：点击填入账号和一次性临时口令，再点击登录。新员工使用自己的账号密码。</p></div>
  {groups.map(g=>{
   const items=accounts.filter(g.match).sort((a,b)=>{const rank=(u:string)=>displayOrder.includes(u)?displayOrder.indexOf(u):displayOrder.length;return rank(a.username)-rank(b.username)})
   if(!items.length)return null
   return <section key={g.name} aria-label={g.name+'身份'}>
    <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1"><h3 className="text-xs font-semibold tracking-[0.08em] text-muted-foreground">{g.name}</h3>{g.hint&&<p className="text-[11px] leading-relaxed text-muted-foreground">{g.hint}</p>}</div>
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">{items.map(a=>{
     const selected=selectedUsername===a.username
     return <button key={a.username} type="button" disabled={busy} aria-pressed={selected} onClick={()=>onSelect(a)} className={'group relative min-w-0 rounded-md border border-border bg-card px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] disabled:opacity-40 '+(selected?'!border-[hsl(12_74%_42%)] ring-2 ring-[hsl(12_74%_42%)]':'hover:border-[hsl(12_74%_42%/0.6)] hover:bg-[hsl(12_74%_42%/0.03)]')}>
      <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 pr-3"><span className="text-[13px] font-semibold">{displayNames[a.username]||a.username}</span><span className="break-all font-mono2 text-[11px] text-muted-foreground">{a.username}</span></span>
      <span className="mt-1 block text-[11px] leading-relaxed text-muted-foreground">{description(a)}</span>
      {selected&&<span aria-hidden="true" className="absolute right-3 top-4 size-1.5 rounded-full bg-[hsl(12_74%_42%)]"/>}
     </button>
    })}</div>
   </section>
  })}
 </section>
}
