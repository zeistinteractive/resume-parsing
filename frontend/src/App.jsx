import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { PrivateRoute, AdminRoute } from './components/PrivateRoute'
import Sidebar from './components/Sidebar'

import Upload         from './pages/Upload'
import Search         from './pages/Search'
import ResumeDetail   from './pages/ResumeDetail'
import Login          from './pages/Login'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword  from './pages/ResetPassword'
import ChangePassword from './pages/ChangePassword'
import Users           from './pages/Users'
import AuditLog        from './pages/AuditLog'
import DownloadHistory from './pages/DownloadHistory'

// ── Authenticated shell ────────────────────────────────────────────────────────

function AppShell() {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar />
      <main className="flex-1 ml-60 min-h-screen">
        <div className="px-8 py-7 max-w-6xl">
          <Routes>
            <Route path="/"                element={<PrivateRoute><Upload /></PrivateRoute>} />
            <Route path="/search"          element={<PrivateRoute><Search /></PrivateRoute>} />
            <Route path="/resume/:id"      element={<PrivateRoute><ResumeDetail /></PrivateRoute>} />
            <Route path="/change-password" element={<PrivateRoute><ChangePassword /></PrivateRoute>} />
            <Route path="/history"         element={<PrivateRoute><DownloadHistory /></PrivateRoute>} />
            <Route path="/users"           element={<AdminRoute><Users /></AdminRoute>} />
            <Route path="/audit-log"       element={<AdminRoute><AuditLog /></AdminRoute>} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

// ── Router ────────────────────────────────────────────────────────────────────

function AppInner() {
  const { user } = useAuth()

  return (
    <Routes>
      {/* Public auth routes — no sidebar */}
      <Route path="/login"           element={!user ? <Login />          : <Navigate to="/" replace />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password"  element={<ResetPassword />} />

      {/* Everything else — sidebar shell */}
      <Route path="/*" element={<PrivateRoute><AppShell /></PrivateRoute>} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  )
}
