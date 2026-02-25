import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { searchResumes } from '../api'

function SkillTag({ skill }) {
  return <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">{skill}</span>
}

function ResultCard({ result, onClick }) {
  return (
    <div onClick={onClick}
      className="bg-white border border-gray-200 rounded-xl p-5 hover:border-blue-300 hover:shadow-md cursor-pointer transition-all">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xl">👤</span>
            <h3 className="font-semibold text-gray-900 text-lg">
              {result.candidate_name || result.filename}
            </h3>
          </div>
          {result.email && (
            <p className="text-sm text-gray-500 mb-2">{result.email}</p>
          )}
          {result.snippet && (
            <p className="text-sm text-gray-600 leading-relaxed mb-3"
              dangerouslySetInnerHTML={{ __html: result.snippet }} />
          )}
          {result.skills?.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {result.skills.map(s => <SkillTag key={s} skill={s} />)}
            </div>
          )}
        </div>
        <span className="text-blue-400 text-xl shrink-0">→</span>
      </div>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 animate-pulse">
      <div className="flex gap-3 mb-3">
        <div className="w-8 h-8 bg-gray-200 rounded-full" />
        <div className="h-5 bg-gray-200 rounded w-48" />
      </div>
      <div className="h-3 bg-gray-100 rounded w-full mb-2" />
      <div className="h-3 bg-gray-100 rounded w-3/4" />
    </div>
  )
}

export default function Search() {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('or')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const debounce = useRef()
  const navigate = useNavigate()

  const doSearch = useCallback(async (q, m) => {
    if (!q || q.trim().length < 2) { setResults(null); return }
    setLoading(true); setError(null)
    try {
      const data = await searchResumes(q.trim(), m)
      setResults(data)
    } catch (e) {
      setError(e.message)
      setResults(null)
    } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    clearTimeout(debounce.current)
    debounce.current = setTimeout(() => doSearch(query, mode), 300)
    return () => clearTimeout(debounce.current)
  }, [query, mode, doSearch])

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-1">Search Resumes</h1>
      <p className="text-gray-500 mb-6">Search by skill, job title, company, or any keyword.</p>

      {/* Search bar */}
      <div className="relative mb-3">
        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-xl">🔍</span>
        <input
          autoFocus
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="e.g. Python React Docker, Senior Engineer, Pune…"
          className="w-full pl-11 pr-4 py-3.5 text-lg border border-gray-300 rounded-xl shadow-sm
            focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {query && (
          <button onClick={() => setQuery('')}
            className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xl">
            ×
          </button>
        )}
      </div>

      {/* AND / OR toggle */}
      <div className="flex items-center gap-2 mb-6">
        <span className="text-sm text-gray-500">Match:</span>
        <div className="flex rounded-lg border border-gray-200 overflow-hidden text-sm font-medium">
          <button
            onClick={() => setMode('or')}
            className={`px-4 py-1.5 transition-colors ${
              mode === 'or'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            ANY keyword
          </button>
          <button
            onClick={() => setMode('and')}
            className={`px-4 py-1.5 border-l border-gray-200 transition-colors ${
              mode === 'and'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-600 hover:bg-gray-50'
            }`}
          >
            ALL keywords
          </button>
        </div>
        <span className="text-xs text-gray-400">
          {mode === 'or'
            ? 'Returns resumes matching any keyword'
            : 'Returns resumes matching every keyword'}
        </span>
      </div>

      {/* Results */}
      {loading && (
        <div className="space-y-3">
          {[1,2,3].map(i => <SkeletonCard key={i} />)}
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
          {error}
        </div>
      )}

      {results && !loading && (
        <div>
          <p className="text-sm text-gray-500 mb-3">
            {results.count === 0
              ? `No resumes found for "${results.query}"`
              : `Found ${results.count} resume${results.count !== 1 ? 's' : ''} matching "${results.query}"`}
          </p>
          {results.count === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <div className="text-5xl mb-3">🔎</div>
              <p className="font-medium">No matches found</p>
              <p className="text-sm mt-1">Try a different keyword or skill</p>
            </div>
          ) : (
            <div className="space-y-3">
              {results.results.map(r => (
                <ResultCard key={r.id} result={r} onClick={() => navigate(`/resume/${r.id}`)} />
              ))}
            </div>
          )}
        </div>
      )}

      {!query && !loading && !results && (
        <div className="text-center py-16 text-gray-400">
          <div className="text-6xl mb-4">🗂️</div>
          <p className="text-lg font-medium text-gray-500">Start typing to search</p>
          <p className="text-sm mt-2">Searches across skills, experience, and all resume text</p>
        </div>
      )}
    </div>
  )
}
