// 应用外壳：左侧深色窄边栏（品牌、知识库切换、导航、用户）+ 右侧内容区。
import {useEffect,useState} from 'react'
import {Menu,X} from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router'
import {
  Database,
  FileStack,
  KeyRound,
  LogOut,
  MessageSquareText,
  LayoutDashboard,
} from 'lucide-react'
import { LogoLockup } from './Logo'
import { DemoTag } from './bits'
import { useKnowledgeBase, useSession } from '@/lib/session'
import { demoIdentityName } from '@/lib/demo-identity-names'
import { KNOWLEDGE_BASES } from '@/lib/types'
import type { KbId } from '@/lib/types'

const NAV = [
  { to: '/workbench', label: '工作台', en: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/documents', label: '文档管理', en: 'Documents', icon: FileStack },
  { to: '/qa', label: '知识问答', en: 'Ask', icon: MessageSquareText },
  { to: '/knowledge-gaps', label: '未解决问题', en: 'Questions', icon: MessageSquareText },
  { to: '/identity', label: '权限与身份', en: 'Identity', icon: KeyRound },
] as const

function KbSwitcher() {
  const { kbId, setKb, kbStats, availableKbs } = useSession()
  return (
    <div className="px-4">
      <div className="font-mono2 text-[9px] font-medium uppercase tracking-[0.28em] text-[#6e6656]">
        Knowledge Base
      </div>
      <div className="mt-2 space-y-1">
        {(Object.keys(KNOWLEDGE_BASES) as KbId[]).filter(id=>availableKbs.includes(id)).map((id) => {
          const kb = KNOWLEDGE_BASES[id]
          const active = id === kbId
          return (
            <button
              key={id}
              onClick={() => setKb(id)}
              className={`ease-junyi w-full rounded-md border px-3 py-2.5 text-left transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_50%)] ${
                active
                  ? 'border-[hsl(12_74%_50%/0.6)] bg-[hsl(12_74%_50%/0.12)]'
                  : 'border-transparent hover:bg-[hsl(36_12%_15%)]'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className={`text-[13px] font-medium ${
                    active ? 'text-[#EDE6D8]' : 'text-[#a89f8c]'
                  }`}
                >
                  {kb.name}
                </span>
                <span
                  className={`size-1.5 shrink-0 rounded-full ${
                    active ? 'bg-[hsl(12_74%_55%)]' : 'bg-[#4a4436]'
                  }`}
                />
              </div>
              <div className="mt-1 font-mono2 text-[9px] uppercase tracking-[0.14em] text-[#6e6656]">
                {kb.readonly ? 'READ ONLY' : 'MANAGED'} · {kbStats[id]?.totalDocs<0?'待加载':kbStats[id]?.totalDocs??'—'} DOCS
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default function AppShell() {
  const { user, logout, searchableDocs, visibleDocs } = useSession()
  const name = demoIdentityName(user?.username) ?? user?.role.name ?? '用户'
  const kb = useKnowledgeBase()
  const navigate = useNavigate()
  const [menuOpen,setMenuOpen]=useState(false)
  useEffect(()=>setMenuOpen(false),[kb.id])

  return (
    <div className="flex min-h-dvh">
      {/* 深色窄边栏 */}
      {menuOpen&&<button aria-label="关闭导航遮罩" className="fixed inset-0 z-20 bg-black/30 lg:hidden" onClick={()=>setMenuOpen(false)}/>}
      <aside className={`fixed inset-y-0 left-0 z-30 flex w-[236px] flex-col overflow-y-auto bg-[hsl(36_16%_9%)] text-[#a89f8c] transition-transform lg:translate-x-0 ${menuOpen?'translate-x-0':'-translate-x-full'}`}>
        <div className="px-5 pb-6 pt-6">
          <LogoLockup dark />
        </div>

        <KbSwitcher />

        <nav className="mt-6 flex-1 space-y-0.5 px-3">
          <div className="px-2 pb-2 font-mono2 text-[9px] font-medium uppercase tracking-[0.28em] text-[#6e6656]">
            Workspace
          </div>
          {NAV.filter(item=>item.to!=='/knowledge-gaps'||kb.id==='business'&&['employee','supervisor'].includes(user?.accessRole||'')).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={()=>setMenuOpen(false)}
              end={'end' in item}
              className={({ isActive }) =>
                `ease-junyi group flex items-center gap-3 rounded-md px-3 py-2.5 transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_50%)] ${
                  isActive
                    ? 'bg-[hsl(36_12%_15%)] text-[#EDE6D8]'
                    : 'text-[#a89f8c] hover:bg-[hsl(36_12%_13%)] hover:text-[#d8d0bd]'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon
                    className={`size-4 shrink-0 ${isActive ? 'text-[hsl(12_74%_58%)]' : ''}`}
                    strokeWidth={1.8}
                  />
                  <span className="text-[13px] font-medium">{item.label}</span>
                  <span className="ml-auto font-mono2 text-[9px] uppercase tracking-[0.14em] text-[#5d5647]">
                    {item.en}
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* 用户区 */}
        <div className="border-t border-[hsl(36_10%_18%)] p-4">
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-full border border-[hsl(36_10%_24%)] font-display text-[13px] font-semibold text-[#EDE6D8]">
              {Array.from(name)[0]}
            </div>
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-[13px] font-medium text-[#EDE6D8]">{name}</div>
              <div className="mt-0.5 truncate font-mono2 text-[10px] tracking-wide text-[#6e6656]">
                {user?.role.name} · {user?.role.dept}
                {user?.admin ? ' · 文档管理员' : ''}
              </div>
            </div>
            <button
              onClick={() => {
                logout()
                navigate('/login', { replace: true })
              }}
              title="退出登录"
              className="ease-junyi rounded-md p-2 text-[#8f8674] transition-colors duration-200 hover:bg-[hsl(36_12%_15%)] hover:text-[#EDE6D8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_50%)]"
            >
              <LogOut className="size-4" strokeWidth={1.8} />
            </button>
          </div>
        </div>
      </aside>

      {/* 内容区 */}
      <div className="flex min-h-dvh min-w-0 flex-1 flex-col lg:ml-[236px]">
        <header className="sticky top-0 z-20 flex min-h-14 flex-wrap items-center justify-between gap-3 py-3 border-b border-border bg-[hsl(44_22%_94%/0.92)] px-4 sm:px-8 backdrop-blur-sm">
          <div className="flex items-center gap-3 text-[12px] text-muted-foreground">
            <button type="button" aria-label={menuOpen?"关闭导航":"打开导航"} onClick={()=>setMenuOpen(!menuOpen)} className="mr-1 rounded-md border border-border p-2 lg:hidden">{menuOpen?<X className="size-4"/>:<Menu className="size-4"/>}</button>
            <Database className="size-3.5" strokeWidth={1.8} />
            <span className="font-medium text-foreground">{kb.name}</span>
            <span className="text-border">/</span>
            <span className="font-mono2 text-[11px]">
              可见 {visibleDocs.length} · 可检索 {searchableDocs.length}
            </span>
            <span className="text-border">/</span>
            <span className="hidden xl:inline">{kb.modeLabel}</span>
          </div>
          <div className="flex flex-wrap items-center gap-3"><span className="text-[11px] text-muted-foreground">{user?.username} · {user?.role.name} · {user?.role.dept}</span><DemoTag /></div>
        </header>
        <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">
          <Outlet />
        </main>
        <footer className="border-t border-border px-8 py-4">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>均易 · 企业研发智能工作台（P18）</span>
            <span className="font-mono2 tracking-wide">让每一份信息，都有迹可循。</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
