import { Routes, Route, NavLink } from 'react-router-dom'
import Upload from './pages/Upload'
import Search from './pages/Search'
import ResumeDetail from './pages/ResumeDetail'

function Navbar() {
  const active = 'bg-blue-700 text-white'
  const inactive = 'text-blue-100 hover:bg-blue-600 hover:text-white'
  return (
    <nav className="bg-blue-800 shadow">
      <div className="max-w-5xl mx-auto px-4 flex items-center gap-1 h-14">
        <span className="text-white font-bold text-lg mr-6 flex items-center gap-2">
          <span className="text-2xl">📄</span> Resume Engine
        </span>
        <NavLink to="/" end className={({ isActive }) =>
          `px-4 py-2 rounded text-sm font-medium transition-colors ${isActive ? active : inactive}`}>
          Upload
        </NavLink>
        <NavLink to="/search" className={({ isActive }) =>
          `px-4 py-2 rounded text-sm font-medium transition-colors ${isActive ? active : inactive}`}>
          Search
        </NavLink>
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="max-w-5xl mx-auto px-4 py-8">
        <Routes>
          <Route path="/" element={<Upload />} />
          <Route path="/search" element={<Search />} />
          <Route path="/resume/:id" element={<ResumeDetail />} />
        </Routes>
      </main>
    </div>
  )
}
