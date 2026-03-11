import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  searchResumes, autocomplete, getUploaders,
  listSavedSearches, createSavedSearch, deleteSavedSearch,
  downloadUrl, bulkDownload,
} from '../api'

// ── Constants ──────────────────────────────────────────────────────────────────

const EDUCATION_OPTIONS = [
  '', "High School", "Diploma", "Bachelor's", "Master's", "MBA", "PhD", "Other",
]
const NOTICE_OPTIONS = [
  '', 'Immediate', '15 days', '30 days', '60 days', '90 days', '>90 days', 'Not mentioned',
]
const SORT_OPTIONS = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'exp_desc',  label: 'Experience: High → Low' },
  { value: 'exp_asc',   label: 'Experience: Low → High' },
  { value: 'date_desc', label: 'Date Added' },
]
const LIMIT_OPTIONS = [25, 50, 100]

const EMPTY_FILTERS = {
  title: '', skills: [], exp_min: '', exp_max: '',
  location: '', education: '', notice_period: '',
  date_from: '', date_to: '', uploaded_by: '',
}

// ── Small shared components ────────────────────────────────────────────────────

function SkillPill({ skill, onRemove }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">
      {skill}
      {onRemove && (
        <button onClick={onRemove} className="text-blue-500 hover:text-blue-800 leading-none">×</button>
      )}
    </span>
  )
}

function FileIcon({ filename = '' }) {
  const ext = filename.split('.').pop().toLowerCase()
  if (ext === 'pdf')
    return <span className="text-xs font-bold text-red-500 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded">PDF</span>
  if (ext === 'docx' || ext === 'doc')
    return <span className="text-xs font-bold text-blue-500 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded">DOC</span>
  return null
}

function AutocompleteInput({ value, onChange, onSelect, placeholder, type, className = '' }) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const debounce = useRef()

  useEffect(() => {
    clearTimeout(debounce.current)
    if (!value) { setSuggestions([]); setOpen(false); return }
    debounce.current = setTimeout(async () => {
      const results = await autocomplete(type, value)
      setSuggestions(results)
      setOpen(results.length > 0)
    }, 220)
    return () => clearTimeout(debounce.current)
  }, [value, type])

  const pick = (s) => { onSelect(s); setSuggestions([]); setOpen(false) }

  return (
    <div className="relative">
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        className={`w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 ${className}`}
      />
      {open && (
        <ul className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-52 overflow-y-auto">
          {suggestions.map(s => (
            <li key={s}
              onMouseDown={() => pick(s)}
              className="px-3 py-2 text-sm hover:bg-blue-50 cursor-pointer">
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Filter Panel ───────────────────────────────────────────────────────────────

function FilterPanel({ filters, onChange, onClear, activeCount, uploaders = [] }) {
  const [skillInput, setSkillInput] = useState('')

  const set = (key, val) => onChange({ ...filters, [key]: val })

  const addSkill = (s) => {
    const skill = s.trim()
    if (!skill || filters.skills.includes(skill)) { setSkillInput(''); return }
    set('skills', [...filters.skills, skill])
    setSkillInput('')
  }

  const removeSkill = (s) => set('skills', filters.skills.filter(x => x !== s))

  return (
    <aside className="w-64 shrink-0 space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">Filters</h2>
        {activeCount > 0 && (
          <button onClick={onClear}
            className="text-xs text-blue-600 hover:underline">
            Clear all ({activeCount})
          </button>
        )}
      </div>

      {/* Job Title */}
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1.5">Job Title</label>
        <AutocompleteInput
          type="titles"
          value={filters.title}
          onChange={v => set('title', v)}
          onSelect={v => set('title', v)}
          placeholder="e.g. Senior Engineer"
        />
      </div>

      {/* Skills */}
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1.5">Skills</label>
        <AutocompleteInput
          type="skills"
          value={skillInput}
          onChange={setSkillInput}
          onSelect={addSkill}
          placeholder="Add a skill…"
        />
        {/* Also add on Enter */}
        <input type="text" className="hidden"
          onKeyDown={e => e.key === 'Enter' && addSkill(skillInput)} />
        {filters.skills.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {filters.skills.map(s => (
              <SkillPill key={s} skill={s} onRemove={() => removeSkill(s)} />
            ))}
          </div>
        )}
      </div>

      {/* Experience range */}
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1.5">Experience (years)</label>
        <div className="flex items-center gap-2">
          <input
            type="number" min="0" max="50"
            value={filters.exp_min}
            onChange={e => set('exp_min', e.target.value)}
            placeholder="Min"
            className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm text-center focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <span className="text-gray-400 text-sm shrink-0">–</span>
          <input
            type="number" min="0" max="50"
            value={filters.exp_max}
            onChange={e => set('exp_max', e.target.value)}
            placeholder="Max"
            className="w-full border border-gray-300 rounded-lg px-2 py-2 text-sm text-center focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>
      </div>

      {/* Location */}
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1.5">Location</label>
        <AutocompleteInput
          type="locations"
          value={filters.location}
          onChange={v => set('location', v)}
          onSelect={v => set('location', v)}
          placeholder="e.g. San Francisco"
        />
      </div>

      {/* Education */}
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1.5">Education</label>
        <select
          value={filters.education}
          onChange={e => set('education', e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white">
          {EDUCATION_OPTIONS.map(o => (
            <option key={o} value={o}>{o || 'Any'}</option>
          ))}
        </select>
      </div>

      {/* Notice Period */}
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1.5">Notice Period</label>
        <select
          value={filters.notice_period}
          onChange={e => set('notice_period', e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white">
          {NOTICE_OPTIONS.map(o => (
            <option key={o} value={o}>{o || 'Any'}</option>
          ))}
        </select>
      </div>

      {/* Date range */}
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1.5">Date Uploaded</label>
        <div className="space-y-1.5">
          <input type="date" value={filters.date_from}
            onChange={e => set('date_from', e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          <input type="date" value={filters.date_to}
            onChange={e => set('date_to', e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
      </div>

      {/* Uploaded By */}
      {uploaders.length > 0 && (
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1.5">Uploaded By</label>
          <select
            value={filters.uploaded_by}
            onChange={e => set('uploaded_by', e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white">
            <option value="">Anyone</option>
            {uploaders.map(u => (
              <option key={u.id} value={u.id}>{u.full_name}</option>
            ))}
          </select>
        </div>
      )}
    </aside>
  )
}

// ── Result Card ────────────────────────────────────────────────────────────────

function ResultCard({ result, onClick, selected, onToggle }) {
  return (
    <div
      onClick={onClick}
      className={`bg-white border rounded-xl p-5 hover:shadow-md cursor-pointer transition-all ${
        selected ? 'border-blue-400 bg-blue-50/30' : 'border-gray-200 hover:border-blue-300'
      }`}>
      <div className="flex items-start gap-3">

        {/* Checkbox */}
        <div className="shrink-0 mt-1" onClick={e => { e.stopPropagation(); onToggle(result.id) }}>
          <input
            type="checkbox"
            checked={selected}
            onChange={() => {}}
            className="w-4 h-4 accent-blue-600 cursor-pointer rounded"
          />
        </div>

        {/* Main content */}
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2 mb-1">
            <span className="text-xl mt-0.5 shrink-0">👤</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-semibold text-gray-900 text-base leading-snug">
                  {result.candidate_name || result.filename}
                </h3>
                <FileIcon filename={result.filename} />
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm text-gray-500 mt-0.5">
                {result.current_title && (
                  <span className="font-medium text-gray-700">{result.current_title}</span>
                )}
                {result.experience_years > 0 && (
                  <span>·&nbsp;{result.experience_years} yr{result.experience_years !== 1 ? 's' : ''}</span>
                )}
                {result.location && (
                  <span>·&nbsp;📍 {result.location}</span>
                )}
              </div>
            </div>
          </div>

          {/* FTS snippet */}
          {result.snippet && (
            <p className="text-sm text-gray-600 leading-relaxed mb-2 pl-7 line-clamp-2"
              dangerouslySetInnerHTML={{ __html: result.snippet }} />
          )}

          {/* Skills */}
          {result.skills?.length > 0 && (
            <div className="flex flex-wrap gap-1 pl-7">
              {result.skills.map(s => <SkillPill key={s} skill={s} />)}
            </div>
          )}
        </div>

        {/* Right column: date + download + arrow */}
        <div className="shrink-0 flex flex-col items-end gap-2">
          {result.uploaded_at && (
            <span className="text-xs text-gray-400">
              {new Date(result.uploaded_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
            </span>
          )}
          <div className="flex items-center gap-2">
            <a
              href={downloadUrl(result.id)}
              download
              onClick={e => e.stopPropagation()}
              title="Download resume"
              className="text-gray-400 hover:text-blue-600 transition-colors text-base leading-none"
            >
              ⬇
            </a>
            <span className="text-blue-400 text-lg">→</span>
          </div>
        </div>
      </div>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 animate-pulse">
      <div className="flex gap-3 mb-3">
        <div className="w-8 h-8 bg-gray-200 rounded-full shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-gray-200 rounded w-48" />
          <div className="h-3 bg-gray-100 rounded w-64" />
        </div>
      </div>
      <div className="h-3 bg-gray-100 rounded w-full mb-1.5 ml-11" />
      <div className="h-3 bg-gray-100 rounded w-3/4 ml-11" />
    </div>
  )
}

// ── Pagination Bar ─────────────────────────────────────────────────────────────

function PaginationBar({ total, limit, offset, onPage, onLimit }) {
  const totalPages = Math.ceil(total / limit)
  const page       = Math.floor(offset / limit)
  const from       = total === 0 ? 0 : offset + 1
  const to         = Math.min(offset + limit, total)

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 mt-6 pt-4 border-t border-gray-100">
      <span className="text-sm text-gray-500">
        {from}–{to} of {total} result{total !== 1 ? 's' : ''}
      </span>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-sm text-gray-500">
          <span>Per page:</span>
          {LIMIT_OPTIONS.map(n => (
            <button key={n} onClick={() => onLimit(n)}
              className={`px-2.5 py-1 rounded-lg border text-sm transition-colors ${
                limit === n
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}>
              {n}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onPage(page - 1)}
            disabled={page === 0}
            className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-600
              hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
            ← Prev
          </button>
          <span className="px-3 text-sm text-gray-500">
            {page + 1} / {totalPages || 1}
          </span>
          <button
            onClick={() => onPage(page + 1)}
            disabled={page >= totalPages - 1}
            className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-600
              hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
            Next →
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Saved Searches Bar ─────────────────────────────────────────────────────────

function SavedSearchesBar({ saved, onLoad, onDelete, onSave, canSave }) {
  const [saving, setSaving] = useState(false)
  const [name, setName]     = useState('')

  const submit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    await onSave(name.trim())
    setName('')
    setSaving(false)
  }

  return (
    <div className="flex flex-wrap items-center gap-2 mt-3 min-h-[28px]">
      <span className="text-xs text-gray-400 font-medium shrink-0">Saved:</span>
      {saved.length === 0 && !saving && (
        <span className="text-xs text-gray-300">none yet</span>
      )}
      {saved.map(s => (
        <span key={s.id}
          className="inline-flex items-center gap-1 text-xs bg-gray-100 hover:bg-blue-50 border border-gray-200
            rounded-full px-2.5 py-0.5 cursor-pointer transition-colors group">
          <span onClick={() => onLoad(s)} className="text-gray-700 group-hover:text-blue-700">{s.name}</span>
          <button
            onClick={() => onDelete(s.id)}
            className="text-gray-300 hover:text-red-500 transition-colors ml-0.5">×</button>
        </span>
      ))}
      {canSave && !saving && (
        <button onClick={() => setSaving(true)}
          className="text-xs text-blue-600 hover:underline shrink-0">
          + Save current
        </button>
      )}
      {saving && (
        <form onSubmit={submit} className="flex items-center gap-1">
          <input autoFocus value={name} onChange={e => setName(e.target.value)}
            placeholder="Search name…"
            className="text-xs border border-gray-300 rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400 w-36" />
          <button type="submit"
            className="text-xs bg-blue-600 text-white px-2.5 py-1 rounded-lg hover:bg-blue-700">
            Save
          </button>
          <button type="button" onClick={() => setSaving(false)}
            className="text-xs text-gray-400 hover:text-gray-600">
            Cancel
          </button>
        </form>
      )}
    </div>
  )
}

// ── Bulk Action Bar ────────────────────────────────────────────────────────────

function BulkBar({ count, onSelectAll, onClear, onDownload, downloading }) {
  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 flex justify-center pointer-events-none">
      <div className="mb-6 pointer-events-auto bg-gray-900 text-white rounded-2xl shadow-2xl px-5 py-3 flex items-center gap-4 text-sm">
        <span className="font-semibold">{count} selected</span>
        <span className="text-gray-500">|</span>
        <button onClick={onSelectAll} className="text-gray-300 hover:text-white transition-colors">
          Select all on page
        </button>
        <button onClick={onClear} className="text-gray-300 hover:text-white transition-colors">
          Clear
        </button>
        <button
          onClick={onDownload}
          disabled={downloading}
          className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 px-4 py-1.5 rounded-lg font-medium transition-colors"
        >
          {downloading ? 'Preparing…' : '⬇ Download ZIP'}
        </button>
      </div>
    </div>
  )
}

// ── Session persistence ────────────────────────────────────────────────────────
// Called as a lazy useState initializer — runs fresh on every component mount,
// so navigating back from a detail page always restores the previous search.
function _readSession() {
  try { const s = sessionStorage.getItem('resumeSearch'); return s ? JSON.parse(s) : null }
  catch { return null }
}

// ── Main Search Page ───────────────────────────────────────────────────────────

function countActiveFilters(filters) {
  return [
    filters.title,
    filters.skills.length > 0,
    filters.exp_min !== '',
    filters.exp_max !== '',
    filters.location,
    filters.uploaded_by,
    filters.education,
    filters.notice_period,
    filters.date_from,
    filters.date_to,
  ].filter(Boolean).length
}

export default function Search() {
  const navigate = useNavigate()

  // ── Search state ─────────────────────────────────────────────────────────────
  const [query,   setQuery]   = useState(() => _readSession()?.query   ?? '')
  const [mode,    setMode]    = useState(() => _readSession()?.mode    ?? 'or')
  const [filters, setFilters] = useState(() => { const s = _readSession(); return s?.filters ? { ...EMPTY_FILTERS, ...s.filters } : EMPTY_FILTERS })
  const [sort,    setSort]    = useState(() => _readSession()?.sort    ?? 'relevance')
  const [limit,   setLimit]   = useState(() => _readSession()?.limit   ?? 25)
  const [offset,  setOffset]  = useState(() => _readSession()?.offset  ?? 0)

  // ── Results state ─────────────────────────────────────────────────────────────
  const [results,     setResults]     = useState(null)   // null = not searched yet
  const [total,       setTotal]       = useState(0)
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState(null)
  const [filtersOpen, setFiltersOpen] = useState(true)
  const [uploaders,   setUploaders]   = useState([])

  // ── Selection state ───────────────────────────────────────────────────────────
  const [selected,    setSelected]    = useState(new Set())
  const [downloading, setDownloading] = useState(false)

  // ── Saved searches ────────────────────────────────────────────────────────────
  const [saved, setSaved] = useState([])

  useEffect(() => {
    listSavedSearches().then(setSaved).catch(() => {})
    getUploaders().then(setUploaders).catch(() => {})
  }, [])

  // Persist state so back-navigation restores the search
  useEffect(() => {
    sessionStorage.setItem('resumeSearch', JSON.stringify({ query, mode, filters, sort, limit, offset }))
  }, [query, mode, filters, sort, limit, offset])

  // ── Core search function ──────────────────────────────────────────────────────
  const doSearch = useCallback(async (q, m, f, s, lim, off) => {
    const hasQuery   = q && q.trim().length >= 2
    const hasFilters = countActiveFilters(f) > 0
    if (!hasQuery && !hasFilters) { setResults([]); setTotal(0); return }

    setLoading(true); setError(null)
    try {
      const data = await searchResumes({
        q:             hasQuery ? q.trim() : '',
        mode:          m,
        title:         f.title,
        skills:        f.skills,
        exp_min:       f.exp_min !== '' ? Number(f.exp_min) : undefined,
        exp_max:       f.exp_max !== '' ? Number(f.exp_max) : undefined,
        location:      f.location,
        education:     f.education,
        notice_period: f.notice_period,
        date_from:     f.date_from   || undefined,
        date_to:       f.date_to     || undefined,
        uploaded_by:   f.uploaded_by || undefined,
        sort:          s,
        limit:         lim,
        offset:        off,
      })
      setResults(data.results)
      setTotal(data.total)
    } catch (e) {
      setError(e.message)
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [])

  // Debounce query changes; fire immediately on filter/sort/limit/offset changes
  const queryDebounce = useRef()
  const prevQuery     = useRef(query)

  useEffect(() => {
    clearTimeout(queryDebounce.current)
    const queryChanged = query !== prevQuery.current
    prevQuery.current  = query

    if (queryChanged) {
      queryDebounce.current = setTimeout(() => doSearch(query, mode, filters, sort, limit, offset), 350)
    } else {
      doSearch(query, mode, filters, sort, limit, offset)
    }
    return () => clearTimeout(queryDebounce.current)
  }, [query, mode, filters, sort, limit, offset, doSearch])

  // Reset to page 0 whenever anything except offset changes
  const resetAndSearch = (updates) => {
    setOffset(0)
    if ('query'   in updates) setQuery(updates.query)
    if ('mode'    in updates) setMode(updates.mode)
    if ('filters' in updates) setFilters(updates.filters)
    if ('sort'    in updates) setSort(updates.sort)
    if ('limit'   in updates) setLimit(updates.limit)
  }

  // ── Saved search handlers ─────────────────────────────────────────────────────
  const handleSave = async (name) => {
    const filtersToSave = {
      ...filters,
      exp_min: filters.exp_min !== '' ? Number(filters.exp_min) : null,
      exp_max: filters.exp_max !== '' ? Number(filters.exp_max) : null,
    }
    const ss = await createSavedSearch(name, query, filtersToSave)
    setSaved(prev => [ss, ...prev])
  }

  const handleLoadSaved = (ss) => {
    const f = {
      ...EMPTY_FILTERS,
      ...ss.filters,
      skills:  ss.filters.skills  || [],
      exp_min: ss.filters.exp_min != null ? String(ss.filters.exp_min) : '',
      exp_max: ss.filters.exp_max != null ? String(ss.filters.exp_max) : '',
    }
    setQuery(ss.query || '')
    setFilters(f)
    setOffset(0)
  }

  const handleDeleteSaved = async (id) => {
    await deleteSavedSearch(id)
    setSaved(prev => prev.filter(s => s.id !== id))
  }

  // ── Selection handlers ────────────────────────────────────────────────────────
  const toggleSelect = (id) =>
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const selectAllOnPage = () =>
    setSelected(prev => {
      const next = new Set(prev)
      results?.forEach(r => next.add(r.id))
      return next
    })

  const clearSelection = () => setSelected(new Set())

  const handleBulkDownload = async () => {
    if (selected.size === 0) return
    setDownloading(true)
    try {
      const blob = await bulkDownload([...selected])
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = 'resumes.zip'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      alert(e.message)
    } finally {
      setDownloading(false)
    }
  }

  const activeFilterCount = countActiveFilters(filters)
  const hasAnything       = (query && query.trim().length >= 2) || activeFilterCount > 0
  const canSave           = hasAnything

  return (
    <div>
      {/* Page header */}
      <h1 className="text-2xl font-bold text-gray-800 mb-1">Search Resumes</h1>
      <p className="text-gray-500 mb-5">Search by keyword, or use filters to find the right candidates.</p>

      {/* Search bar */}
      <div className="relative mb-2">
        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-xl pointer-events-none">🔍</span>
        <input
          autoFocus
          type="text"
          value={query}
          onChange={e => { setQuery(e.target.value); setOffset(0) }}
          placeholder="e.g. Python React Docker, Senior Engineer, Pune…"
          className="w-full pl-11 pr-10 py-3.5 text-lg border border-gray-300 rounded-xl shadow-sm
            focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {query && (
          <button onClick={() => resetAndSearch({ query: '' })}
            className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xl">
            ×
          </button>
        )}
      </div>

      {/* Controls row: AND/OR toggle + filter toggle */}
      <div className="flex items-center gap-3 mb-2">
        <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium">
          {['or', 'and'].map(m => (
            <button key={m} onClick={() => resetAndSearch({ mode: m })}
              className={`px-3 py-1.5 transition-colors ${
                mode === m ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}>
              {m === 'or' ? 'ANY keyword' : 'ALL keywords'}
            </button>
          ))}
        </div>

        <button
          onClick={() => setFiltersOpen(o => !o)}
          className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
            filtersOpen
              ? 'bg-gray-100 border-gray-300 text-gray-700'
              : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
          }`}>
          <span>⚙</span>
          <span>Filters{activeFilterCount > 0 ? ` (${activeFilterCount})` : ''}</span>
          <span className="text-gray-400">{filtersOpen ? '▲' : '▼'}</span>
        </button>
      </div>

      {/* Saved searches bar */}
      <SavedSearchesBar
        saved={saved}
        onLoad={handleLoadSaved}
        onDelete={handleDeleteSaved}
        onSave={handleSave}
        canSave={canSave}
      />

      {/* Body: filter panel + results */}
      <div className="flex gap-8 mt-6">

        {/* ── Filter Panel ── */}
        {filtersOpen && (
          <FilterPanel
            filters={filters}
            onChange={(f) => resetAndSearch({ filters: f })}
            onClear={() => resetAndSearch({ filters: EMPTY_FILTERS })}
            activeCount={activeFilterCount}
            uploaders={uploaders}
          />
        )}

        {/* ── Results area ── */}
        <div className="flex-1 min-w-0">

          {/* Sort + result count header */}
          {(results !== null || loading) && (
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm text-gray-500">
                {loading ? 'Searching…' : (
                  total === 0
                    ? 'No matches found'
                    : <><span className="font-semibold text-gray-800">{total}</span> candidate{total !== 1 ? 's' : ''} found</>
                )}
              </p>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">Sort:</span>
                <select
                  value={sort}
                  onChange={e => resetAndSearch({ sort: e.target.value })}
                  className="text-sm border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white">
                  {SORT_OPTIONS.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* Loading skeletons */}
          {loading && (
            <div className="space-y-3">
              {[1, 2, 3].map(i => <SkeletonCard key={i} />)}
            </div>
          )}

          {/* Error */}
          {error && !loading && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* Empty state — no search yet */}
          {!hasAnything && !loading && (
            <div className="text-center py-20 text-gray-400">
              <div className="text-6xl mb-4">🗂️</div>
              <p className="text-lg font-medium text-gray-500">Start typing or apply a filter</p>
              <p className="text-sm mt-2">Searches across all resume content in real-time</p>
            </div>
          )}

          {/* No results */}
          {hasAnything && !loading && results?.length === 0 && (
            <div className="text-center py-16 text-gray-400">
              <div className="text-5xl mb-3">🔎</div>
              <p className="font-medium text-gray-500">No candidates match your criteria</p>
              <p className="text-sm mt-1">Try a broader keyword or adjust your filters</p>
            </div>
          )}

          {/* Result cards */}
          {!loading && results?.length > 0 && (
            <>
              <div className="space-y-3">
                {results.map(r => (
                  <ResultCard key={r.id} result={r}
                    selected={selected.has(r.id)}
                    onToggle={toggleSelect}
                    onClick={() => navigate(`/resume/${r.id}`)} />
                ))}
              </div>

              <PaginationBar
                total={total}
                limit={limit}
                offset={offset}
                onPage={(p) => setOffset(p * limit)}
                onLimit={(n) => { setLimit(n); setOffset(0) }}
              />
            </>
          )}
        </div>
      </div>

      {/* Bulk action bar — floats above footer when ≥1 card selected */}
      {selected.size > 0 && (
        <BulkBar
          count={selected.size}
          onSelectAll={selectAllOnPage}
          onClear={clearSelection}
          onDownload={handleBulkDownload}
          downloading={downloading}
        />
      )}
    </div>
  )
}
