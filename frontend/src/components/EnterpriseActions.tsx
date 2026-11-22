import {useState} from 'react'
import {api} from '@/lib/api'
export {MinorCorrection} from './MinorCorrection'
const input='rounded-md border border-border bg-card px-3 py-2 text-sm disabled:opacity-40'
const departments=['研发部','生产制造部','财务部','人力资源部','行政安全部']
export function InviteAccount(){
 const [username,setUsername]=useState(''),[department,setDepartment]=useState('研发部'),[role,setRole]=useState('employee'),[job,setJob]=useState(''),[invitation,setInvitation]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false)
 return <form className="grid max-w-xl gap-4 border border-border bg-card p-5" onSubmit={async e=>{e.preventDefault();setBusy(true);setMessage('');setInvitation('');try{const r=await api.post<{invitation_code:string;notice:string}>('/api/business/accounts',{username,department,role,job});setInvitation(r.invitation_code);setMessage(r.notice)}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}}>
 <h2 className="font-semibold">邀请新人建号</h2><p className="text-sm text-muted-foreground">仅管理层负责人与指定人事主管。只能创建员工或访客；主管任命仍由管理层负责人办理。邀请有效24小时，仅显示一次，请通过可信渠道交给本人，不要公开截图。</p>
 <label className="grid gap-1">新人账号<input aria-label="新人账号" required minLength={3} maxLength={64} pattern="[A-Za-z][A-Za-z0-9_]{2,63}" autoComplete="off" className={input} value={username} onChange={e=>setUsername(e.target.value)}/></label>
 <label className="grid gap-1">初始部门<select aria-label="初始部门" className={input} value={department} onChange={e=>{setDepartment(e.target.value);setJob('')}}>{departments.map(d=><option key={d}>{d}</option>)}</select></label>
 <label className="grid gap-1">初始职责<select aria-label="初始职责" className={input} value={role} onChange={e=>setRole(e.target.value)}><option value="employee">普通员工</option><option value="guest">只读访客（无部门自动读权）</option></select></label>
 <label className="grid gap-1">专业岗位<select aria-label="专业岗位" className={input} value={job} onChange={e=>setJob(e.target.value)}><option value="">无旧岗位例外</option>{(department==='研发部'?['研发','测试','运维']:department==='生产制造部'?['生产']:[]).map(j=><option key={j}>{j}</option>)}</select></label>
 <button className={input} disabled={busy}>创建一次性邀请</button><button type="button" className={input} disabled={busy||!username} onClick={async()=>{setBusy(true);setInvitation('');setMessage('');try{const r=await api.post<{invitation_code:string;notice:string}>('/api/business/accounts/reinvite',{username});setInvitation(r.invitation_code);setMessage(r.notice)}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}}>重发未激活账号的邀请（不改部门职责）</button>{message&&<p role="status" className="text-sm">{message}</p>}{invitation&&<label className="grid gap-1 text-sm">一次性邀请（请妥善交接）<input readOnly type="password" autoComplete="off" aria-label="一次性邀请" className={input} value={invitation} onFocus={e=>e.target.select()}/><button type="button" className={input} onClick={async()=>{try{await navigator.clipboard.writeText(invitation);setMessage('邀请已复制，请通过可信方式交给本人。')}catch{setMessage('无法自动复制，请选中邀请后手动复制。')}}}>复制邀请</button></label>}
 </form>
}
