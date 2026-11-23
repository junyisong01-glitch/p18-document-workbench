import {useRef,useState,type FormEvent} from 'react'
import {useSearchParams} from 'react-router'
import {api} from '@/lib/api'
import {useSession} from '@/lib/session'
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog'
import './InviteAccount.css'
export {MinorCorrection} from './MinorCorrection'
const departments=['研发部','生产制造部','财务部','人力资源部','行政安全部']

export function InvitationOverlay(){
 const {user,kbId}=useSession(),[params,setParams]=useSearchParams()
 if(kbId!=='business'||!user?.canCreateAccounts||params.get('invite')!=='1')return null
 return <InviteAccountDialog onClose={()=>{const next=new URLSearchParams(params);next.delete('invite');setParams(next,{replace:true})}}/>
}
function InviteAccountDialog({onClose}:{onClose:()=>void}){
 const [username,setUsername]=useState(''),[department,setDepartment]=useState('研发部'),[role,setRole]=useState('employee'),[job,setJob]=useState('')
 const [mode,setMode]=useState<'create'|'reinvite'>('create'),[invitation,setInvitation]=useState(''),[message,setMessage]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 const submitting=useRef(false)
 const valid=/^[A-Za-z][A-Za-z0-9_]{2,63}$/.test(username)
 async function submit(e:FormEvent){
  e.preventDefault();if(!valid||submitting.current)return
  submitting.current=true;setBusy(true);setError('');setMessage('');setInvitation('')
  try{const r=await api.post<{invitation_code:string;notice:string}>(mode==='create'?'/api/business/accounts':'/api/business/accounts/reinvite',mode==='create'?{username,department,role,job:role==='guest'?'':job}:{username});setInvitation(r.invitation_code);setMessage(r.notice)}catch(e){setError((e as Error).message)}finally{submitting.current=false;setBusy(false)}
 }
 return <Dialog open onOpenChange={open=>{if(!open&&!busy)onClose()}}><DialogContent className="invite-dialog" showCloseButton={!busy} onEscapeKeyDown={e=>{if(busy)e.preventDefault()}} onPointerDownOutside={e=>{if(busy||invitation)e.preventDefault()}}><DialogHeader><DialogTitle>邀请新人建号</DialogTitle><DialogDescription>创建员工或访客账号，由本人通过邀请设置密码。</DialogDescription></DialogHeader>
 {invitation?<div className="invite-result"><h3>邀请已生成</h3><p role="status">{message}</p><label>一次性邀请<input type="password" readOnly autoComplete="off" aria-label="一次性邀请" value={invitation} onFocus={e=>e.target.select()}/></label><p>有效期 24 小时。关闭后无法再次查看，请复制并通过可信渠道交给本人。</p><footer className="invite-actions"><button type="button" onClick={onClose}>完成</button><button type="button" className="dm-primary" onClick={async()=>{try{await navigator.clipboard.writeText(invitation);setMessage('邀请已复制，请交给本人。')}catch{setMessage('无法自动复制，请选中邀请后手动复制。')}}}>复制邀请</button></footer></div>:<form className="invite-form" onSubmit={submit}>
 <div className="invite-modes" role="group" aria-label="邀请方式">{([['create','邀请新账号'],['reinvite','重发邀请']]as const).map(([value,label])=><button type="button" key={value} aria-pressed={mode===value} disabled={busy} onClick={()=>{setMode(value);setError('')}}>{label}</button>)}</div>
 <fieldset disabled={busy}><label>账号<input aria-label="新人账号" required minLength={3} maxLength={64} pattern="[A-Za-z][A-Za-z0-9_]{2,63}" autoComplete="off" placeholder="例如：chen_xu" value={username} onChange={e=>setUsername(e.target.value)}/><span>字母开头，可使用字母、数字和下划线，3–64 位。</span></label>
 {mode==='create'?<><div className="invite-fields"><label>初始职责<select aria-label="初始职责" value={role} onChange={e=>setRole(e.target.value)}><option value="employee">普通员工</option><option value="guest">只读访客</option></select></label><label>所属部门<select aria-label="初始部门" value={department} onChange={e=>{setDepartment(e.target.value);setJob('')}}>{departments.map(d=><option key={d}>{d}</option>)}</select></label></div><p className="invite-note">{role==='guest'?'访客仅查阅获准对外公开的资料，所属部门不授予内部阅读权限。':'普通员工可以上传资料；部门主管由管理层在“人员职责”中任命。'}</p>{role==='employee'&&<details className="invite-advanced"><summary>专业岗位（选填）</summary><label><span className="sr-only">专业岗位</span><select aria-label="专业岗位" value={job} onChange={e=>setJob(e.target.value)}><option value="">不设置岗位例外</option>{(department==='研发部'?['研发','测试','运维']:department==='生产制造部'?['生产']:[]).map(j=><option key={j}>{j}</option>)}</select></label><p>沿用现有岗位例外权限；不确定时保留默认设置。</p></details>}</>:<p className="invite-note">仅重发尚未激活账号的邀请。旧邀请会失效，账号的部门与职责保持不变。</p>}
 </fieldset>{error&&<p role="alert" className="invite-error">{error}</p>}
 <footer className="invite-actions"><button type="button" disabled={busy} onClick={onClose}>取消</button><button type="submit" className="dm-primary" disabled={busy||!valid}>{busy?'正在生成…':mode==='create'?'生成邀请':'重新生成邀请'}</button></footer>
 </form>}</DialogContent></Dialog>
}
