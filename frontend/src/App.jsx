import { Routes, Route, NavLink } from 'react-router-dom'
import Upload from './pages/Upload'
import Search from './pages/Search'
import ResumeDetail from './pages/ResumeDetail'

function Navbar() {
  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-30 shadow-sm">
      <div className="max-w-6xl mx-auto px-6 flex items-center gap-2 h-14">
        {/* Brand */}
        <div className="flex items-center gap-2 mr-8">
          <span className="text-xl">📄</span>
          <span className="font-bold text-gray-900 text-base tracking-tight">Resume Engine</span>
        </div>

        {/* Nav links */}
        <NavLink to="/" end className={({ isActive }) =>
          `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            isActive ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
          }`}>
          Upload
        </NavLink>
        <NavLink to="/search" className={({ isActive }) =>
          `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            isActive ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
          }`}>
          Search
        </NavLink>
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-6xl mx-auto px-6 py-8">
        <Routes>
          <Route path="/" element={<Upload />} />
          <Route path="/search" element={<Search />} />
          <Route path="/resume/:id" element={<ResumeDetail />} />
        </Routes>
      </main>
    </div>
  )
}
