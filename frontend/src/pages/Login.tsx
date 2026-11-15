// 页面一：登录（已有登录功能的视觉升级）
// 演示账号由数据层提供；登录成功进入工作台，退出后回到本页。
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { Eye, EyeOff, Loader2, LockKeyhole, UserRound } from 'lucide-react'
import { LogoLockup, LogoMark } from '@/components/Logo'
import { useSession } from '@/lib/session'

export default function LoginPage() {
  const { login } = useSession()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [fieldError, setFieldError] = useState<{ u?: string; p?: string }>({})
  const [loading, setLoading] = useState(false)

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
      if (res.ok) {
        navigate('/', { replace: true })
      } else {
        setError(res.error ?? '登录失败')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-dvh">
      {/* 品牌区 */}
      <div className="relative hidden w-[46%] flex-col justify-between overflow-hidden bg-[hsl(36_16%_9%)] p-12 lg:flex">
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

      {/* 登录表单区 */}
      <div className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-[400px]">
          <div className="lg:hidden">
            <LogoLockup />
          </div>

          <div className="mt-8 lg:mt-0">
            <div className="kicker">Sign In</div>
            <h2 className="mt-2 font-display text-[24px] font-semibold tracking-tight">
              登录均易工作台
            </h2>
            <p className="mt-2 text-[13px] text-muted-foreground">
              使用已授权的企业账号登录，系统将按你的岗位确定可访问范围。
            </p>
          </div>

          <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
            <div>
              <label htmlFor="username" className="mb-1.5 block text-[12px] font-medium">
                账号
              </label>
              <div className="relative">
                <UserRound className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="请输入账号"
                  className="ease-junyi h-11 w-full rounded-md border border-input bg-card pl-9 pr-3 text-[14px] outline-none transition-colors duration-200 placeholder:text-muted-foreground/60 focus:border-[hsl(12_74%_42%)] focus:ring-2 focus:ring-[hsl(12_74%_42%/0.18)]"
                />
              </div>
              {fieldError.u && (
                <p className="mt-1.5 text-[12px] text-[hsl(4_72%_40%)]">{fieldError.u}</p>
              )}
            </div>

            <div>
              <label htmlFor="password" className="mb-1.5 block text-[12px] font-medium">
                密码
              </label>
              <div className="relative">
                <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  id="password"
                  type={showPw ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="请输入密码"
                  className="ease-junyi h-11 w-full rounded-md border border-input bg-card pl-9 pr-10 text-[14px] outline-none transition-colors duration-200 placeholder:text-muted-foreground/60 focus:border-[hsl(12_74%_42%)] focus:ring-2 focus:ring-[hsl(12_74%_42%/0.18)]"
                />
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  aria-label={showPw ? '隐藏密码' : '显示密码'}
                  className="ease-junyi absolute right-2 top-1/2 -translate-y-1/2 rounded p-1.5 text-muted-foreground transition-colors duration-200 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
                >
                  {showPw ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              {fieldError.p && (
                <p className="mt-1.5 text-[12px] text-[hsl(4_72%_40%)]">{fieldError.p}</p>
              )}
            </div>

            {error && (
              <div
                role="alert"
                className="rounded-md border border-[hsl(4_72%_40%/0.4)] bg-[hsl(4_72%_40%/0.06)] px-3.5 py-2.5 text-[13px] text-[hsl(4_72%_36%)]"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="ease-junyi flex h-11 w-full items-center justify-center gap-2 rounded-md bg-[hsl(12_74%_42%)] text-[14px] font-semibold text-[hsl(44_40%_97%)] transition-all duration-200 hover:bg-[hsl(12_74%_38%)] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              {loading && <Loader2 className="size-4 animate-spin" />}
              {loading ? '正在登录…' : '登 录'}
            </button>
          </form>

          <p className="mt-8 text-sm">请使用管理员提供的本机账号与密码，登录后由服务端决定岗位和文档权限。</p>
        </div>
      </div>
    </div>
  )
}
