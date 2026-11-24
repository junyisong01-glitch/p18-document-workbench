import {useEffect,useRef,useState,type FormEvent} from 'react'
import {ArrowRight,Check,Search,Users,ChevronDown} from 'lucide-react'
import {api} from '@/lib/api'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog'
import './PersonnelRoles.css'

type Person={username:string;role:string;department:string;job?:string}
const departments=['研发部','生产制造部','财务部','人力资源部','行政安全部']
const roleNames:Record<string,string>={employee:'员工',supervisor:'部门主管',guest:'只读访客',boss:'管理层负责人'}
const roleHints:Record<string,string>={employee:'查阅获准资料，上传并发布符合规则的普通资料。',supervisor:'管理本部门资料，审核风险内容，并为普通资料设置跨部门授权。',guest:'仅查阅获准对外公开的资料，不具备上传和管理权限。'}
const nameOf=(p:Person)=>demoIdentityName(p.username)||'未登记姓名'
const departmentOf=(p:Person)=>p.role==='guest'?'不适用':p.department||'未分配部门'

export function PersonnelRoles(){
 const [people,setPeople]=useState<Person[]>([]),[loaded,setLoaded]=useState(false),[loadError,setLoadError]=useState(''),[attempt,setAttempt]=useState(0)
 const [query,setQuery]=useState(''),[roleFilter,setRoleFilter]=useState(''),[selected,setSelected]=useState<Person|null>(null)
 const [role,setRole]=useState('employee'),[department,setDepartment]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
 const submitting=useRef(false)
 useEffect(()=>{let active=true;setLoadError('');setLoaded(false);api.get<Person[]>('/api/business/people').then(data=>{if(active){setPeople(data);setLoaded(true)}}).catch(e=>{if(active)setLoadError(e.message)});return()=>{active=false}},[attempt])
 const term=query.trim().toLowerCase()
 const filtered=people.filter(p=>(!roleFilter||p.role===roleFilter)&&(!term||[nameOf(p),p.username,p.department,roleNames[p.role]].some(value=>value?.toLowerCase().includes(term))))
 const nextDepartment=role==='guest'?'':department
 const changed=!!selected&&(role!==selected.role||nextDepartment!==selected.department)
 const valid=role==='guest'||departments.includes(department)
 function edit(p:Person){setSelected(p);setRole(p.role);setDepartment(departments.includes(p.department)?p.department:'');setError('');setNotice('')}
 async function save(event:FormEvent){
  event.preventDefault();if(!selected||!changed||!valid||submitting.current)return
  submitting.current=true;setBusy(true);setError('')
  try{
   await api.put('/api/business/people',{username:selected.username,role,department:nextDepartment})
   setPeople(current=>current.map(p=>p.username===selected.username?{...p,role,department:nextDepartment}:p))
   setNotice(nameOf(selected)+'的职责已更新，下次使用需要重新登录。');setSelected(null)
  }catch(e){setError((e as Error).message)}finally{submitting.current=false;setBusy(false)}
 }
 return <section className="personnel" aria-label="人员职责管理">
  <header className="personnel-heading"><div><h2>人员列表 <span>{loaded?people.length:'—'} 人</span></h2><p>按姓名找到同事，再调整职责与所属部门。</p></div><span className="personnel-access">仅管理层可调整</span></header>
  <div className="personnel-toolbar"><label className="personnel-search"><Search size={18} aria-hidden="true"/><input aria-label="搜索人员" placeholder="搜索姓名、账号或部门" value={query} onChange={e=>setQuery(e.target.value)}/></label><span className="personnel-role-filter"><select aria-label="筛选职责" value={roleFilter} onChange={e=>setRoleFilter(e.target.value)}><option value="">全部职责</option>{Object.entries(roleNames).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><ChevronDown size={15} aria-hidden="true"/></span></div>
  {notice&&<p className="personnel-success" role="status"><Check size={16}/>{notice}</p>}
  {loadError?<div className="personnel-empty" role="alert"><p>{loadError}</p><button onClick={()=>setAttempt(n=>n+1)}>重新加载</button></div>:!loaded?<div className="personnel-loading" role="status" aria-label="正在读取人员">{[0,1,2].map(i=><div key={i}/>)}</div>:<div className="personnel-table-wrap"><table className="personnel-table"><thead><tr><th scope="col">姓名 / 账号</th><th scope="col">所属部门</th><th scope="col">当前职责</th><th scope="col"><span className="sr-only">操作</span></th></tr></thead><tbody>{filtered.map(p=><tr key={p.username}><td><div className="personnel-identity"><span className={'personnel-avatar '+(p.role==='boss'?'is-manager':'')} aria-hidden="true">{nameOf(p)==='未登记姓名'?<Users size={18}/>:nameOf(p).charAt(0)}</span><div><strong>{nameOf(p)}</strong><span>{p.username}</span></div></div></td><td>{departmentOf(p)}</td><td><span className={'personnel-role role-'+p.role}>{roleNames[p.role]||'未分配职责'}</span></td><td>{p.role==='boss'?<span className="personnel-fixed">固定职责</span>:<button className="personnel-edit" aria-label={'调整'+nameOf(p)+'的职责'} onClick={()=>edit(p)}>调整职责 <ArrowRight size={14}/></button>}</td></tr>)}</tbody></table>{!filtered.length&&<div className="personnel-empty"><Users size={24}/><p>{people.length?'没有找到匹配的人员':'暂无人员记录'}</p>{people.length>0&&<button onClick={()=>{setQuery('');setRoleFilter('')}}>清除筛选</button>}</div>}</div>}
  <p className="personnel-footnote">文档单独授权与岗位例外权限，在对应入口管理。</p>
  <Dialog open={!!selected} onOpenChange={open=>{if(!open&&!busy)setSelected(null)}}><DialogContent className="personnel-dialog" showCloseButton={!busy} onEscapeKeyDown={e=>{if(busy)e.preventDefault()}} onPointerDownOutside={e=>{if(busy)e.preventDefault()}}><DialogHeader><DialogTitle>调整人员职责</DialogTitle><DialogDescription>选择新的职责与部门，核对后保存。</DialogDescription></DialogHeader>{selected&&<form onSubmit={save}>
   <div className="personnel-selected"><span className="personnel-avatar" aria-hidden="true">{nameOf(selected)==='未登记姓名'?<Users size={18}/>:nameOf(selected).charAt(0)}</span><div><strong>{nameOf(selected)}</strong><span>{selected.username}</span></div></div>
   <fieldset disabled={busy} className="personnel-fields"><label>职责<select aria-label="调整职责" value={role} onChange={e=>setRole(e.target.value)}>{Object.entries(roleNames).filter(([value])=>value!=='boss').map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><label>所属部门<select aria-label="所属部门" disabled={role==='guest'} value={role==='guest'?'':department} onChange={e=>setDepartment(e.target.value)}><option value="">{role==='guest'?'访客不分配部门':'请选择部门'}</option>{role!=='guest'&&departments.map(d=><option key={d}>{d}</option>)}</select></label></fieldset>
   <p className="personnel-role-hint">{roleHints[role]}</p>
   {changed&&<div className="personnel-change" aria-label="本次调整"><span>本次调整</span>{role!==selected.role&&<p><span>{roleNames[selected.role]}</span><ArrowRight size={14} aria-label="改为"/><strong>{roleNames[role]}</strong></p>}{nextDepartment!==selected.department&&<p><span>{departmentOf(selected)}</span><ArrowRight size={14} aria-label="改为"/><strong>{role==='guest'?'不分配部门':department||'请选择部门'}</strong></p>}</div>}
   <p className="personnel-save-note">保存后，该人员需重新登录。已有的文档单独授权与岗位例外权限仍独立生效。</p>
   {error&&<p role="alert" className="personnel-error">{error}</p>}
   <footer className="personnel-actions"><button type="button" disabled={busy} onClick={()=>setSelected(null)}>取消</button><button type="submit" className="dm-primary" disabled={!changed||!valid||busy}>{busy?'正在保存…':'保存调整'}</button></footer>
  </form>}</DialogContent></Dialog>
 </section>
}
