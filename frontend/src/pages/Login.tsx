// 页面一：登录（已有登录功能的视觉升级）
// 演示账号由数据层提供；登录成功进入工作台，退出后回到本页。
import { useEffect, useState } from 'react'
import { ArrowRight, Check, Eye, EyeOff, KeyRound, Loader2, LockKeyhole, UserRound } from 'lucide-react'
import { LogoLockup, LogoMark } from '@/components/Logo'
import {DemoIdentityCards} from '@/components/DemoIdentityCards'
import {api} from '@/lib/api'
import { useSession } from '@/lib/session'
import './LoginFlow.css'

export default function LoginPage() {
  const { login } = useSession()
  const [activate,setActivate]=useState(false),[invite,setInvite]=useState(''),[newPassword,setNewPassword]=useState('')
  const [activationError,setActivationError]=useState('')
  const [activationSuccess,setActivationSuccess]=useState(false)
  const [username, setUsername] = useState('')
  const [selectedDemo,setSelectedDemo]=useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [fieldError, setFieldError] = useState<{ u?: string; p?: string }>({})
  const [loading, setLoading] = useState(false)
  const [accounts,setAccounts]=useState<Array<{username:string;role:string;department:string;job:string;password_required:boolean}>>([])
  useEffect(()=>{api.get<typeof accounts>('/api/library/demo-accounts').then(setAccounts).catch(()=>setAccounts([]))},[])
  async function quick(account:typeof accounts[number]){
    setLoading(true);setError('');setFieldError({});setSelectedDemo('');try{const filled=await api.post<{username:string;password:string}>('/api/library/demo-fill',{username:account.username});setUsername(filled.username);setPassword(filled.password);setSelectedDemo(filled.username);setShowPw(false);document.getElementById('password')?.focus()}catch(e){setError((e as Error).message)}finally{setLoading(false)}
  }


  function changeMode(next:boolean){
    if(loading)return
    setActivate(next);setActivationSuccess(false);setSelectedDemo('');setError('');setActivationError('')
    setInvite('');setNewPassword('');setUsername('');setPassword('');setShowPw(false);setFieldError({})
  }
  async function activateAccount(e:React.FormEvent){
    e.preventDefault()
    if(loading)return
    setLoading(true);setError('');setActivationError('')
    try{
      const response=await api.post<{activated:boolean}>('/api/library/activate-account',{invitation_code:invite.trim(),password:newPassword})
      if(!response.activated)throw Error('激活未完成，请重试。')
      setInvite('');setNewPassword('');setPassword('');setUsername('');setShowPw(false);setFieldError({})
      setActivate(false);setActivationSuccess(true);setSelectedDemo('')
    }catch(e){setActivationError((e as Error).message)}finally{setLoading(false)}
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (loading) return
    const fe: { u?: string; p?: string } = {}
    if (!username.trim()) fe.u = '请输入账号'
    if (!password) fe.p = '请输入密码'
    setFieldError(fe)
    setError('')
    if (fe.u || fe.p) return
    setLoading(true)
    try {
      const res = await login(username, password)
      if (!res.ok) {
        setError(password.startsWith('p18-demo-')?'临时演示口令已失效，请重新点击身份卡片填入后登录。':res.error ?? '登录失败')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-dvh lg:h-dvh lg:overflow-hidden">
      {/* 品牌区 */}
      <div className="relative hidden h-dvh w-[46%] shrink-0 flex-col justify-between overflow-hidden bg-[hsl(36_16%_9%)] p-12 lg:flex">
        {/* 背景迹线装饰 */}
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.10]"
          aria-hidden="true"
        >
          <defs>
            <pattern id="trace" width="56" height="56" patternUnits="userSpaceOnUse">
              <path d="M0 28 H56 M28 0 V56" stroke="#EDE6D8" strokeWidth="0.5" />
              <circle cx="28" cy="28" r="1.5" fill="#EDE6D8" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#trace)" />
        </svg>

        <LogoLockup dark />

        <div className="relative">
          <div className="font-mono2 text-[10px] font-medium uppercase tracking-[0.32em] text-[hsl(12_74%_58%)]">
            Enterprise R&D Intelligence
          </div>
          <h1 className="mt-5 font-display text-[44px] font-semibold leading-[1.15] tracking-tight text-[#EDE6D8]">
            企业研发
            <br />
            智能工作台
          </h1>
          <p className="mt-5 max-w-sm text-[14px] leading-relaxed text-[#a89f8c]">
            让每一份信息，都有迹可循。
          </p>

          <div className="mt-10 space-y-4 border-t border-[hsl(36_10%_20%)] pt-8">
            {[
              ['找得到', '混合检索定位技术资料，Top-5 结果直达来源'],
              ['查得清', '每条结论都有证据片段，可人工核对原文'],
              ['管得住', '岗位权限约束访问范围，外发授权严格受控'],
            ].map(([t, d], i) => (
              <div key={t} className="flex items-baseline gap-4">
                <span className="font-mono2 text-[11px] font-medium text-[hsl(12_74%_58%)]">
                  0{i + 1}
                </span>
                <div>
                  <span className="text-[14px] font-semibold text-[#EDE6D8]">{t}</span>
                  <span className="ml-3 text-[12px] text-[#8f8674]">{d}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative flex items-center gap-2 font-mono2 text-[10px] uppercase tracking-[0.2em] text-[#6e6656]">
          <LogoMark size={14} ink="#6e6656" trace="hsl(12 74% 58%)" />
          P18 · JUNYI WORKBENCH
        </div>
      </div>

      {/* 激活与登录互斥展示；验证与会话仍由原生后端处理。 */}
      <main data-login-scroll="true" className={'login-flow-scroll min-w-0 flex-1'+(!activate&&!activationSuccess?' login-flow-normal':'')} aria-label="账号登录与激活">
        <div className="login-flow-body">
          <div className="lg:hidden"><LogoLockup /></div>
          {(activate||activationSuccess)&&<nav className="login-flow-steps" aria-label="激活与登录步骤">
            <span className={activate?'login-flow-step current':'login-flow-step complete'} aria-current={activate?'step':undefined}><i>{activationSuccess?<Check size={13}/>: '01'}</i>激活账号</span>
            <span className="login-flow-step-line"/>
            <span className={activationSuccess?'login-flow-step current':'login-flow-step'} aria-current={activationSuccess?'step':undefined}><i>02</i>登录工作台</span>
          </nav>}
          <header className="login-flow-heading">
            <div className="kicker">{activate?'Activate Account':'Sign In'}</div>
            <h2>{activate?'激活你的账号':'登录均易工作台'}</h2>
            <p>{activate?'首次使用？通过管理员提供的一次性邀请，设置你的登录密码。':activationSuccess?'使用管理员分配的企业账号和你刚设置的密码登录工作台。':'使用已授权的企业账号登录，系统将按你的岗位确定可访问范围。'}</p>
          </header>
          {activate?<>
            <form aria-label="邀请激活" aria-busy={loading} className="login-flow-form" onSubmit={activateAccount}>
              <label htmlFor="activation-invite">一次性邀请</label>
              <div className="login-flow-input"><KeyRound aria-hidden="true"/><input id="activation-invite" aria-label="激活邀请" required type="password" autoComplete="off" maxLength={128} placeholder="粘贴你收到的一次性邀请" value={invite} onChange={e=>setInvite(e.target.value)} disabled={loading} aria-describedby="invite-help"/></div>
              <p id="invite-help" className="login-flow-note">由管理层负责人或人事主管提供，有效期24小时，仅可使用一次。</p>
              <label htmlFor="activation-password" className="login-flow-next">设置自己的密码（至少12字符）</label>
              <div className="login-flow-input"><LockKeyhole aria-hidden="true"/><input id="activation-password" aria-label="新密码" required type={showPw?'text':'password'} autoComplete="new-password" minLength={12} maxLength={1024} placeholder="至少12个字符" value={newPassword} onChange={e=>setNewPassword(e.target.value)} disabled={loading}/><button type="button" className="login-flow-eye" aria-label={showPw?'隐藏密码':'显示密码'} onClick={()=>setShowPw(!showPw)}>{showPw?<EyeOff/>:<Eye/>}</button></div>
              <p className="login-flow-note">以后登录时使用这个密码，激活成功后请使用自己的账号登录。</p>
              {activationError&&<p role="alert" className="login-flow-error">{activationError}</p>}
              <button type="submit" disabled={loading} className="login-flow-primary">{loading?<Loader2 className="size-4 animate-spin"/>:null}{loading?'正在激活…':'激活账号'}{!loading&&<ArrowRight size={17}/>}</button>
            </form>
            <div className="login-flow-switch">已经激活过账号？<button type="button" disabled={loading} onClick={()=>changeMode(false)} aria-label="返回正常登录">返回正常登录<ArrowRight size={14}/></button></div>
          </>:<>
            {activationSuccess&&<div className="login-flow-success" role="status"><Check size={18} aria-hidden="true"/><div><strong>账号已激活，请登录</strong><p>使用管理员分配的账号，以及你刚设置的密码。无需再次填写邀请。</p></div></div>}
            <form onSubmit={submit} className="login-flow-form" noValidate aria-label="账号登录" aria-busy={loading}>
              <label htmlFor="username">账号</label>
              <div className="login-flow-input"><UserRound aria-hidden="true"/><input id="username" type="text" autoComplete="username" value={username} onChange={e=>{setUsername(e.target.value);setSelectedDemo('')}} placeholder="请输入账号" disabled={loading} aria-invalid={!!fieldError.u} aria-describedby={fieldError.u?'username-error':undefined}/></div>
              {fieldError.u&&<p id="username-error" className="login-flow-field-error">{fieldError.u}</p>}
              <label htmlFor="password" className="login-flow-next">密码</label>
              <div className="login-flow-input"><LockKeyhole aria-hidden="true"/><input id="password" type={showPw?'text':'password'} autoComplete="current-password" value={password} onChange={e=>{setPassword(e.target.value);setSelectedDemo('')}} placeholder="请输入密码" disabled={loading} aria-invalid={!!fieldError.p} aria-describedby={fieldError.p?'password-error':undefined}/><button type="button" className="login-flow-eye" onClick={()=>setShowPw(!showPw)} aria-label={showPw?'隐藏密码':'显示密码'}>{showPw?<EyeOff/>:<Eye/>}</button></div>
              {fieldError.p&&<p id="password-error" className="login-flow-field-error">{fieldError.p}</p>}
              {error&&<div role="alert" className="login-flow-error">{error}</div>}
              <button type="submit" disabled={loading} className="login-flow-primary">{loading&&<Loader2 className="size-4 animate-spin"/>}{loading?'正在登录…':'登 录'}</button>
            </form>
            <div className="login-flow-switch">{activationSuccess?'使用其他账号？':'新人首次使用？'}<button type="button" disabled={loading} onClick={()=>changeMode(!activationSuccess)}>{activationSuccess?'返回正常登录':'新人：使用一次性邀请激活账号'}{!activationSuccess&&<ArrowRight size={14}/>}</button></div>
            {!activationSuccess&&accounts.length>0&&<DemoIdentityCards accounts={accounts} selectedUsername={selectedDemo} busy={loading} onSelect={a=>void quick(a)}/>}
            <p className="login-flow-footer">请使用管理员提供的本机账号与密码，登录后由服务端决定岗位和文档权限。</p>
          </>}
        </div>
      </main>
    </div>
  )
}
