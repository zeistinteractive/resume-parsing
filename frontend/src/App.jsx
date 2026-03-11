import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { PrivateRoute, AdminRoute } from './components/PrivateRoute'

import Upload         from './pages/Upload'
import Search         from './pages/Search'
import ResumeDetail   from './pages/ResumeDetail'
import Login          from './pages/Login'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword  from './pages/ResetPassword'
import ChangePassword from './pages/ChangePassword'
import Users          from './pages/Users'
import AuditLog       from './pages/AuditLog'

// ── Nav link helper ───────────────────────────────────────────────────────────
function NL({ to, children, end = false }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) =>
      `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
        isActive ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
      }`}>
      {children}
    </NavLink>
  )
}

// ── Navbar ────────────────────────────────────────────────────────────────────
function Navbar() {
  const { user, logout } = useAuth()
  const navigate         = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  if (!user) return null   // hide navbar on login / forgot / reset pages

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-30 shadow-sm">
      <div className="max-w-6xl mx-auto px-6 flex items-center gap-2 h-14">
        {/* Brand */}
        <div className="flex items-center gap-2 mr-6">
          <span className="text-xl">📄</span>
          <span className="font-bold text-gray-900 text-base tracking-tight">Resume Engine</span>
        </div>

        {/* Links — both roles */}
        <NL to="/" end>Upload</NL>
        <NL to="/search">Search</NL>

        {/* Admin-only links */}
        {user.role === 'admin' && (
          <>
            <NL to="/users">Users</NL>
            <NL to="/audit-log">Audit Log</NL>
          </>
        )}

        {/* Right side */}
        <div className="ml-auto flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2">
            <span className="text-xs text-gray-400">{user.email}</span>
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              user.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'
            }`}>{user.role}</span>
          </div>
          <NL to="/change-password">Change pw</NL>
          <button
            onClick={handleLogout}
            className="px-3 py-1.5 rounded-lg text-sm font-medium text-red-600 hover:bg-red-50 transition-colors">
            Logout
          </button>
        </div>
      </div>
    </nav>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────
function AppInner() {
  const { user } = useAuth()

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className={user ? 'max-w-6xl mx-auto px-6 py-8' : ''}>
        <Routes>
          {/* Public auth routes */}
          <Route path="/login"           element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password"  element={<ResetPassword />} />

          {/* Protected — any authenticated user */}
          <Route path="/"                element={<PrivateRoute><Upload /></PrivateRoute>} />
          <Route path="/search"          element={<PrivateRoute><Search /></PrivateRoute>} />
          <Route path="/resume/:id"      element={<PrivateRoute><ResumeDetail /></PrivateRoute>} />
          <Route path="/change-password" element={<PrivateRoute><ChangePassword /></PrivateRoute>} />

          {/* Admin-only */}
          <Route path="/users"     element={<AdminRoute><Users /></AdminRoute>} />
          <Route path="/audit-log" element={<AdminRoute><AuditLog /></AdminRoute>} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  )
}
