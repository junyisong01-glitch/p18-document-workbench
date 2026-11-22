import { Navigate, Route, Routes, useLocation } from 'react-router'
import { SessionProvider, useSession } from './lib/session'
import AppShell from './components/AppShell'
import LoginPage from './pages/Login'
import DashboardPage from './pages/Dashboard'
import DocumentsPage from './pages/Documents'
import QaPage from './pages/QaPage'
import KnowledgeGapsPage from './pages/KnowledgeGaps'
import Management from './pages/Management'
import IdentityPage from './pages/Identity'

/** 未登录访问受保护资源时拒绝访问，回到登录入口 */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user } = useSession()
  const location = useLocation()
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}

function RoleHome(){const {user,kbId}=useSession();return <Navigate to={kbId==='business'&&['employee','guest'].includes(user?.accessRole||'')?'/qa':'/workbench'} replace/>}

function InternalPage({children,bossOnly=false}:{children:React.ReactNode;bossOnly?:boolean}){
 const {user,kbId}=useSession()
 if(kbId==='business'&&(user?.accessRole==='guest'||bossOnly&&user?.accessRole!=='boss'))return <Navigate to="/qa" replace/>
 if(bossOnly&&kbId!=='business')return <Navigate to="/" replace/>
 return <>{children}</>
}

function AppRoutes() {
  const { user, ready } = useSession()
  const from = useLocation().state?.from
  const afterLogin = from === '/search' || from === '/qa' ? '/qa' : '/'
  // 深链接：会话恢复完成前不要渲染路由，否则会先跳登录再跳首页
  if (!ready) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background text-[13px] text-muted-foreground">
        正在恢复会话…
      </div>
    )
  }
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to={afterLogin} replace /> : <LoginPage />} />
      <Route path="/qa" element={<RequireAuth><QaPage key={user?.username} /></RequireAuth>} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<RoleHome />} />
        <Route path="/workbench" element={<InternalPage><DashboardPage /></InternalPage>} />
        <Route path="/knowledge-gaps" element={<InternalPage><KnowledgeGapsPage /></InternalPage>} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/search" element={<Navigate to="/qa" replace />} />
        <Route path="/management" element={<InternalPage bossOnly><Management/></InternalPage>} />
        <Route path="/identity" element={<InternalPage><IdentityPage /></InternalPage>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <SessionProvider>
      <AppRoutes />
    </SessionProvider>
  )
}
