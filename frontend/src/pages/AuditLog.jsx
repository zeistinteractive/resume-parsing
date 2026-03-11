import { useState, useEffect, useCallback } from 'react'
import { listAuditLogs } from '../api'

const OUTCOME_BADGE = {
  success: 'bg-green-100 text-green-700',
  failure: 'bg-red-100 text-red-700',
}

const ACTION_LABELS = {
  USER_LOGIN:               '🔑 Login',
  USER_LOGIN_FAILED:        '❌ Login Failed',
  USER_LOGOUT:              '🚪 Logout',
  USER_LOCKED:              '🔒 Locked',
  PASSWORD_CHANGED:         '🔐 Password Changed',
  PASSWORD_RESET_REQUESTED: '📧 Reset Requested',
  PASSWORD_RESET_COMPLETED: '✅ Reset Completed',
  PASSWORD_RESET_BY_ADMIN:  '🛠 Admin Reset',
  USER_CREATED:             '➕ User Created',
  USER_UPDATED:             '✏️ User Updated',
  USER_ACTIVATED:           '✅ Activated',
  USER_DEACTIVATED:         '🚫 Deactivated',
}

function fmtTs(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

const ALL_ACTIONS = Object.keys(ACTION_LABELS)

export default function AuditLog() {
  const [data,    setData]    = useState({ total: 0, items: [] })
  const [filters, setFilters] = useState({ user_email: '', action: '', date_from: '', date_to: '' })
  const [page,    setPage]    = useState(0)
  const [loading, setLoading] = useState(false)

  const PAGE_SIZE = 50

  const load = useCallback(async (p = page, f = filters) => {
    setLoading(true)
    try {
      const d = await listAuditLogs({ limit: PAGE_SIZE, offset: p * PAGE_SIZE, ...f })
      setData(d)
    } catch {}
    finally { setLoading(false) }
  }, [page, filters])

  useEffect(() => { load() }, [load])

  function applyFilters(patch) {
    const next = { ...filters, ...patch }
    setFilters(next)
    setPage(0)
    load(0, next)
  }

  function exportCsv() {
    const headers = ['Timestamp', 'User', 'Action', 'Target', 'Outcome', 'IP']
    const rows = data.items.map(r => [
      fmtTs(r.created_at), r.user_email, r.action,
      r.target_user_id ?? '', r.outcome, r.ip_address,
    ])
    const csv = [headers, ...rows].map(r => r.map(v => `"${v}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const a    = document.createElement('a')
    a.href     = URL.createObjectURL(blob)
    a.download = `audit-log-${new Date().toISOString().slice(0,10)}.csv`
    a.click()
  }

  const totalPages = Math.ceil(data.total / PAGE_SIZE)

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Audit Log</h1>
          <p className="text-gray-500 text-sm mt-0.5">{data.total} events</p>
        </div>
        <button onClick={exportCsv}
          className="border border-gray-200 text-gray-600 text-sm px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors">
          ↓ Export CSV
        </button>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <input
          placeholder="Filter by email"
          value={filters.user_email}
          onChange={e => applyFilters({ user_email: e.target.value })}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
        />
        <select
          value={filters.action}
          onChange={e => applyFilters({ action: e.target.value })}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none">
          <option value="">All actions</option>
          {ALL_ACTIONS.map(a => (
            <option key={a} value={a}>{ACTION_LABELS[a] ?? a}</option>
          ))}
        </select>
        <input type="date" value={filters.date_from}
          onChange={e => applyFilters({ date_from: e.target.value })}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
        />
        <input type="date" value={filters.date_to}
          onChange={e => applyFilters({ date_to: e.target.value })}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
        />
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['Timestamp', 'User', 'Action', 'Details', 'Outcome', 'IP'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">Loading…</td></tr>
              ) : data.items.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">No events found.</td></tr>
              ) : data.items.map(r => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{fmtTs(r.created_at)}</td>
                  <td className="px-4 py-3 font-medium text-gray-800 max-w-[180px] truncate"
                      title={r.user_email}>{r.user_email}</td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {ACTION_LABELS[r.action] ?? r.action}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs max-w-[200px] truncate"
                      title={r.new_value ?? r.old_value ?? ''}>
                    {r.new_value || r.old_value || '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${OUTCOME_BADGE[r.outcome] ?? 'bg-gray-100 text-gray-600'}`}>
                      {r.outcome}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs font-mono">{r.ip_address || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
            className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg text-gray-600
                       hover:bg-gray-50 disabled:opacity-40">← Previous</button>
          <span className="text-sm text-gray-500">Page {page + 1} of {totalPages}</span>
          <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
            className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg text-gray-600
                       hover:bg-gray-50 disabled:opacity-40">Next →</button>
        </div>
      )}
    </div>
  )
}
