import { useState } from 'react'
import { Check, ArrowUpRight } from 'lucide-react'
import { demoIdentityName, demoIdentityNames } from '../lib/demo-identity-names'
import './DemoIdentityCards.css'

export type DemoAccount={username:string;role:string;department:string;job:string;password_required:boolean}
const displayOrder=Object.keys(demoIdentityNames)
const roles=[{key:'all',name:'全部'},{key:'boss',name:'管理层'},{key:'supervisor',name:'主管'},{key:'employee',name:'员工'},{key:'guest',name:'访客'}]
const departmentTitles:Record<string,string>={'研发部':'研发','生产制造部':'生产','财务部':'财务','人力资源部':'人事','行政安全部':'行政'}
function description(a:DemoAccount){
 if(a.role==='boss')return '管理层 · 全局资料与人员管理'
 if(a.role==='guest')return '只读访问 · 获准公开资料'
 return a.department+' · '+(a.job||departmentTitles[a.department]||'部门')+(a.role==='supervisor'?'主管':'岗位')
}
export function DemoIdentityCards({accounts,busy,onSelect,selectedUsername=''}:{accounts:DemoAccount[];busy:boolean;onSelect:(a:DemoAccount)=>void;selectedUsername?:string}){
 const [filter,setFilter]=useState('all')
 const active=roles.some(r=>r.key===filter&&(r.key==='all'||accounts.some(a=>a.role===r.key)))?filter:'all'
 const rank=(u:string)=>displayOrder.includes(u)?displayOrder.indexOf(u):displayOrder.length
 const items=accounts.filter(a=>active==='all'||a.role===active).sort((a,b)=>rank(a.username)-rank(b.username))
 return <section aria-label="本机演示身份" className="demo-identities">
  <header className="demo-identities-heading"><h2>选择演示身份</h2><span>{accounts.length} 个身份</span></header>
  <p className="demo-identities-help">选择身份填入临时账号，再点击登录体验。</p>
  <div className="demo-identity-filters" role="group" aria-label="按身份筛选">
   {roles.map(r=>{const count=r.key==='all'?accounts.length:accounts.filter(a=>a.role===r.key).length
    return count>0&&<button key={r.key} type="button" aria-pressed={active===r.key} onClick={()=>setFilter(r.key)}>{r.name}<span>{count}</span></button>
   })}
  </div>
  <div className="demo-identity-grid">
   {items.map(a=>{const selected=selectedUsername===a.username;const name=demoIdentityName(a.username)||a.username
    return <button key={a.username} type="button" disabled={busy} aria-pressed={selected} onClick={()=>onSelect(a)} className="demo-identity-card">
     <span className="demo-identity-avatar" aria-hidden="true">{name.slice(0,1)}</span>
     <span className="demo-identity-copy"><span className="demo-identity-name">{name}<span className="demo-identity-role">{roles.find(r=>r.key===a.role)?.name||a.role}</span></span><span className="demo-identity-description">{description(a)}</span></span>
     <span className="demo-identity-indicator" aria-hidden="true">{selected?<Check size={15}/>:<ArrowUpRight size={15}/>}</span>
    </button>
   })}
  </div>
  <p className="demo-identity-note">仅供本机演示 · 新员工请使用自己的账号密码</p>
 </section>
}
