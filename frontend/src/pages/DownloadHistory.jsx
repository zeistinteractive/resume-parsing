import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDownloadHistory } from '../api'

const PAGE_SIZE = 25

const TYPE_CFG = {
  token:  { label: 'Single',   cls: 'bg-indigo-50 text-indigo-700 ring-indigo-100' },
  single: { label: 'Single',   cls: 'bg-indigo-50 text-indigo-700 ring-indigo-100' },
  bulk:   { label: 'Bulk ZIP', cls: 'bg-amber-50  text-amber-700  ring-amber-100'  },
}

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) +
    ' · ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

function SkeletonRow() {
  return (
    <tr className="animate-pulse">
      {[1,2,3,4,5].map(i => (
        <td key={i} className="px-5 py-3.5">
          <div className="h-3.5 bg-slate-100 rounded w-24" />
        </td>
      ))}
    </tr>
  )
}

export default function DownloadHistory() {
  const navigate            = useNavigate()
  const [data,    setData]  = useState({ total: 0, items: [] })
  const [page,    setPage]  = useState(0)
  const [loading, setLoading] = useState(true)
  const [error,   setError] = useState(null)

  const load = useCallback(async (p = 0) => {
    setLoading(true)
    setError(null)
    try {
      const d = await getDownloadHistory(PAGE_SIZE, p * PAGE_SIZE)
      setData(d)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(page) }, [page, load])

  const totalPages = Math.ceil(data.total / PAGE_SIZE)
  const from = data.total === 0 ? 0 : page * PAGE_SIZE + 1
  const to   = Math.min((page + 1) * PAGE_SIZE, data.total)

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Download History</h1>
          <p className="text-slate-500 text-sm mt-1">
            Every resume file served — single downloads and bulk ZIPs.
          </p>
        </div>
        {data.total > 0 && (
          <div className="text-sm text-slate-400 mt-1 shrink-0">
            {from}–{to} of <span className="font-medium text-slate-700">{data.total}</span> downloads
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm mb-5">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              {['Candidate', 'File', 'Type', 'IP Address', 'Downloaded At'].map(h => (
                <th key={h} className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-100">
            {loading ? (
              Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} />)
            ) : data.items.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-5 py-16 text-center">
                  <div className="flex flex-col items-center gap-3 text-slate-400">
                    <svg className="w-10 h-10" fill="none" stroke="currentColor" strokeWidth={1.25} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
                    </svg>
                    <p className="text-sm font-medium text-slate-500">No downloads yet</p>
                    <p className="text-xs">Downloads will appear here once resumes are downloaded.</p>
                  </div>
                </td>
              </tr>
            ) : (
              data.items.map(row => {
                const typeCfg = TYPE_CFG[row.download_type] ?? { label: row.download_type, cls: 'bg-slate-100 text-slate-600 ring-slate-200' }
                return (
                  <tr
                    key={row.id}
                    onClick={() => row.resume_id && navigate(`/resume/${row.resume_id}`)}
                    className={`transition-colors ${row.resume_id ? 'hover:bg-indigo-50/40 cursor-pointer' : ''}`}
                  >
                    {/* Candidate */}
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div className="w-7 h-7 rounded-lg bg-indigo-100 flex items-center justify-center shrink-0">
                          <span className="text-indigo-600 text-xs font-bold">
                            {(row.candidate_name || row.filename || '?')[0].toUpperCase()}
                          </span>
                        </div>
                        <span className={`font-medium ${row.resume_id ? 'text-slate-800 hover:text-indigo-700' : 'text-slate-500'}`}>
                          {row.candidate_name || '—'}
                        </span>
                      </div>
                    </td>

                    {/* File */}
                    <td className="px-5 py-3.5 text-slate-500 max-w-[200px]">
                      <span className="truncate block" title={row.filename}>{row.filename || '—'}</span>
                    </td>

                    {/* Type badge */}
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ring-1 ring-inset ${typeCfg.cls}`}>
                        {typeCfg.label}
                      </span>
                    </td>

                    {/* IP */}
                    <td className="px-5 py-3.5 text-slate-400 font-mono text-xs">
                      {row.ip_address || '—'}
                    </td>

                    {/* Date */}
                    <td className="px-5 py-3.5 text-slate-500 text-xs whitespace-nowrap">
                      {fmtDate(row.downloaded_at)}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <button
            onClick={() => setPage(p => p - 1)}
            disabled={page === 0}
            className="flex items-center gap-2 px-3.5 py-2 text-sm border border-slate-200 rounded-xl
                       text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
            </svg>
            Previous
          </button>
          <span className="text-sm text-slate-500">
            Page <span className="font-medium text-slate-700">{page + 1}</span> of {totalPages}
          </span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={page >= totalPages - 1}
            className="flex items-center gap-2 px-3.5 py-2 text-sm border border-slate-200 rounded-xl
                       text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
            Next
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
            </svg>
          </button>
        </div>
      )}
    </div>
  )
}
