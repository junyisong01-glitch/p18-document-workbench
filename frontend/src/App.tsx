import { Navigate, Route, Routes, useLocation } from 'react-router'
import { SessionProvider, useSession } from './lib/session'
import AppShell from './components/AppShell'
import LoginPage from './pages/Login'
import DashboardPage from './pages/Dashboard'
import DocumentsPage from './pages/Documents'
import SearchPage from './pages/SearchPage'
import QaPage from './pages/QaPage'
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

function AppRoutes() {
  const { user, ready } = useSession()
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
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/qa" element={<QaPage />} />
        <Route path="/identity" element={<IdentityPage />} />
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
