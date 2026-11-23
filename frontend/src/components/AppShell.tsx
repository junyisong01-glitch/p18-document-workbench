// 应用外壳：左侧深色窄边栏（品牌、知识库切换、导航、用户）+ 右侧内容区。
import {useEffect,useState} from 'react'
import {InvitationOverlay} from './EnterpriseActions'
import {Menu,X,PanelLeftClose,PanelLeftOpen} from 'lucide-react'
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router'
import {
  Database,
  FileStack,
  KeyRound,
  LogOut,
  MessageSquareText,
  LayoutDashboard,
} from 'lucide-react'
import './AppShell.css'
import { LogoLockup, LogoMark } from './Logo'
import { DemoTag } from './bits'
import { useKnowledgeBase, useSession } from '@/lib/session'
import { demoIdentityName } from '@/lib/demo-identity-names'
import { KNOWLEDGE_BASES } from '@/lib/types'
import type { KbId } from '@/lib/types'

const NAV = [
  { to: '/workbench', label: '工作台', en: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/documents', label: '文档管理', en: 'Documents', icon: FileStack },
  { to: '/qa', label: '知识问答', en: 'Ask', icon: MessageSquareText },
  { to: '/knowledge-gaps', label: '问答反馈', en: 'Feedback', icon: MessageSquareText },
  { to: '/identity', label: '权限与身份', en: 'Identity', icon: KeyRound },
] as const

function KbSwitcher() {
  const { kbId, setKb, kbStats, availableKbs } = useSession()
  return (
    <div className="shell-kb px-4">
      <div className="shell-expanded font-mono2 text-[9px] font-medium uppercase tracking-[0.28em] text-[#6e6656]">
        Knowledge Base
      </div>
      <div className="shell-kb-options mt-2 space-y-1">
        {(Object.keys(KNOWLEDGE_BASES) as KbId[]).filter(id=>availableKbs.includes(id)).map((id) => {
          const kb = KNOWLEDGE_BASES[id]
          const active = id === kbId
          return (
            <button
              key={id}
              aria-label={kb.name}
              aria-pressed={active}
              title={kb.name}
              onClick={() => setKb(id)}
              className={`shell-kb-option ease-junyi w-full rounded-md border px-3 py-2.5 text-left transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_50%)] ${
                active
                  ? 'border-[hsl(12_74%_50%/0.6)] bg-[hsl(12_74%_50%/0.12)]'
                  : 'border-transparent hover:bg-[hsl(36_12%_15%)]'
              }`}
            >
              <Database className="shell-collapsed-only size-5" aria-hidden="true"/>
              <div className="shell-expanded flex items-center justify-between gap-2">
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
              <div className="shell-expanded mt-1 font-mono2 text-[9px] uppercase tracking-[0.14em] text-[#6e6656]">
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
  const qaMode=useLocation().pathname==='/qa'
  const [collapsed,setCollapsed]=useState(()=>{try{return localStorage.getItem('p18.navigation.collapsed')==='true'}catch{return false}})
  function toggleNavigation(){setCollapsed(value=>{const next=!value;try{localStorage.setItem('p18.navigation.collapsed',String(next))}catch{/* Keep working without storage. */}return next})}
  const business=kb.id==='business',guest=business&&user?.accessRole==='guest',boss=business&&user?.accessRole==='boss'
  const navigation=NAV.filter(item=>guest?['/documents','/qa'].includes(item.to):(item.to!=='/knowledge-gaps'||boss)).map(item=>({...item,label:item.to==='/documents'?(guest?'公开资料':boss?'全公司资料':item.label):item.to==='/identity'&&boss?'权限与人员管理':item.label,to:item.to==='/identity'&&boss?'/management':item.to}))
  const [menuOpen,setMenuOpen]=useState(false)
  useEffect(()=>setMenuOpen(false),[kb.id])

  return (
    <div className={`app-shell flex min-h-dvh ${collapsed?'shell-collapsed':''} ${qaMode?'shell-qa':''}`}>
      {/* 深色窄边栏 */}
      {menuOpen&&<button aria-label="关闭导航遮罩" className="fixed inset-0 z-20 bg-black/30 lg:hidden" onClick={()=>setMenuOpen(false)}/>}
      <aside id="app-navigation" aria-label="主导航栏" className={`shell-sidebar fixed inset-y-0 left-0 z-30 flex w-[236px] flex-col overflow-y-auto bg-[hsl(36_16%_9%)] text-[#a89f8c] transition-transform lg:translate-x-0 ${menuOpen?'translate-x-0':'-translate-x-full'}`}>
        <div className="shell-brand">
          <div className="shell-expanded"><LogoLockup dark /></div>
          <div className="shell-collapsed-only"><LogoMark size={30} ink="#EDE6D8"/></div>
          <button type="button" className="shell-collapse hidden lg:grid" onClick={toggleNavigation} aria-expanded={!collapsed} aria-controls="app-navigation" aria-label={collapsed?'展开导航':'收起导航'} title={collapsed?'展开导航':'收起导航'}>{collapsed?<PanelLeftOpen size={18}/>:<PanelLeftClose size={18}/>}</button>
        </div>

        <KbSwitcher />

        <nav aria-label="主导航" className="shell-nav mt-6 flex-1 space-y-0.5 px-3">
          <div className="shell-expanded px-2 pb-2 font-mono2 text-[9px] font-medium uppercase tracking-[0.28em] text-[#6e6656]">
            Workspace
          </div>
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              title={item.label}
              aria-label={item.label}
              to={item.to}
              onClick={()=>setMenuOpen(false)}
              end={'end' in item}
              className={({ isActive }) =>
                `shell-nav-link ease-junyi group flex items-center gap-3 rounded-md px-3 py-2.5 transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_50%)] ${
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
                  <span className="shell-expanded text-[13px] font-medium">{item.label}</span>
                  <span className="shell-expanded ml-auto font-mono2 text-[9px] uppercase tracking-[0.14em] text-[#5d5647]">
                    {item.en}
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* 用户区 */}
        <div className="shell-user border-t border-[hsl(36_10%_18%)] p-4">
          <div className="shell-user-inner flex items-center gap-3">
            <div title={name} aria-label={name} className="flex size-9 shrink-0 items-center justify-center rounded-full border border-[hsl(36_10%_24%)] font-display text-[13px] font-semibold text-[#EDE6D8]">
              {Array.from(name)[0]}
            </div>
            <div className="shell-expanded min-w-0 flex-1 leading-tight">
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
              aria-label="退出登录"
              className="ease-junyi rounded-md p-2 text-[#8f8674] transition-colors duration-200 hover:bg-[hsl(36_12%_15%)] hover:text-[#EDE6D8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_50%)]"
            >
              <LogOut className="size-4" strokeWidth={1.8} />
            </button>
          </div>
        </div>
      </aside>

      {/* 内容区 */}
      <div className="shell-content flex min-h-dvh min-w-0 flex-1 flex-col lg:ml-[236px]">
        {!qaMode&&<header className="sticky top-0 z-20 flex min-h-14 flex-wrap items-center justify-between gap-3 py-3 border-b border-border bg-[hsl(44_22%_94%/0.92)] px-4 sm:px-8 backdrop-blur-sm">
          <div className="flex items-center gap-3 text-[12px] text-muted-foreground">
            <button type="button" aria-label={menuOpen?"关闭导航":"打开导航"} onClick={()=>setMenuOpen(!menuOpen)} className="mr-1 rounded-md border border-border p-2 lg:hidden">{menuOpen?<X className="size-4"/>:<Menu className="size-4"/>}</button>
            <Database className="size-3.5" strokeWidth={1.8} />
            <span className="font-medium text-foreground">{kb.name}</span>
            <span className="text-border">/</span>
            <span className="font-mono2 text-[11px]">
              可见 {visibleDocs.length} · 可检索 {searchableDocs.length}
            </span>
            <span className="text-border">/</span>
            <span className="hidden xl:inline">{guest?'仅查阅获准对外公开的资料':kb.modeLabel}</span>
          </div>
          <div className="flex flex-wrap items-center gap-3"><span className="text-[11px] text-muted-foreground">{user?.username} · {user?.role.name} · {user?.role.dept}</span><DemoTag /></div>
        </header>}
        <main className={qaMode?"min-w-0 flex-1":"min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8"}>
          <Outlet />
          <InvitationOverlay />
        </main>
        {!qaMode&&<footer className="border-t border-border px-8 py-4">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>均易 · 企业研发智能工作台（P18）</span>
            <span className="font-mono2 tracking-wide">让每一份信息，都有迹可循。</span>
          </div>
        </footer>}
      </div>
    </div>
  )
}
