import { useState, useEffect, useCallback } from 'react'
import { listUsers, createUser, updateUser, setUserStatus, adminResetPassword, adminSetPassword } from '../api'

const ROLE_BADGE = {
  admin:     'bg-purple-100 text-purple-700',
  recruiter: 'bg-blue-100 text-blue-700',
}
const STATUS_BADGE = {
  active:   'bg-green-100 text-green-700',
  inactive: 'bg-gray-100 text-gray-500',
}

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

// ── Create / Edit modal ───────────────────────────────────────────────────────
function UserModal({ user, onSave, onClose }) {
  const isEdit = !!user
  const [form,   setForm]   = useState(
    isEdit ? { full_name: user.full_name, email: user.email, role: user.role }
           : { full_name: '', email: '', role: 'recruiter' }
  )
  const [error,  setError]  = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      if (isEdit) await updateUser(user.id, form.full_name, form.email, form.role)
      else        await createUser(form.full_name, form.email, form.role)
      onSave()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-5">
          {isEdit ? 'Edit User' : 'Create New User'}
        </h2>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded-lg text-sm mb-4">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
            <input required value={form.full_name}
              onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input required type="email" value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
            <select value={form.role}
              onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white">
              <option value="recruiter">Recruiter</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          {!isEdit && (
            <p className="text-xs text-gray-400">
              A temporary password will be emailed to the user.
            </p>
          )}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 border border-gray-200 rounded-lg py-2 text-sm text-gray-600 hover:bg-gray-50">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-semibold py-2 rounded-lg text-sm">
              {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create User'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Set Password modal ────────────────────────────────────────────────────────
function SetPasswordModal({ user, onDone, onClose }) {
  const [form,   setForm]   = useState({ password: '', confirm: '' })
  const [error,  setError]  = useState('')
  const [saving, setSaving] = useState(false)
  const [done,   setDone]   = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    if (form.password.length < 8) { setError('Password must be at least 8 characters'); return }
    if (form.password !== form.confirm) { setError('Passwords do not match'); return }
    setSaving(true)
    try {
      await adminSetPassword(user.id, form.password)
      setDone(true)
      setTimeout(onDone, 1500)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
        <div className="mb-5">
          <h2 className="text-lg font-semibold text-gray-800">Set Password</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Setting password for <strong>{user.full_name}</strong> ({user.email})
          </p>
        </div>

        {done ? (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm text-center">
            ✅ Password updated successfully
          </div>
        ) : (
          <>
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded-lg text-sm mb-4">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">New Password</label>
                <input
                  type="password"
                  required
                  autoFocus
                  placeholder="Min. 8 characters"
                  value={form.password}
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Confirm Password</label>
                <input
                  type="password"
                  required
                  placeholder="Re-enter password"
                  value={form.confirm}
                  onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <p className="text-xs text-gray-400">
                The user will be required to change this password on next login.
              </p>

              <div className="flex gap-3 pt-1">
                <button type="button" onClick={onClose}
                  className="flex-1 border border-gray-200 rounded-lg py-2 text-sm text-gray-600 hover:bg-gray-50">
                  Cancel
                </button>
                <button type="submit" disabled={saving}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-semibold py-2 rounded-lg text-sm">
                  {saving ? 'Setting…' : 'Set Password'}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Users() {
  const [data,        setData]        = useState({ total: 0, items: [] })
  const [search,      setSearch]      = useState('')
  const [page,        setPage]        = useState(0)
  const [modal,       setModal]       = useState(null)   // null | 'create' | user-object (edit)
  const [setPwTarget, setSetPwTarget] = useState(null)   // user-object for set-password modal
  const [toast,       setToast]       = useState('')
  const [loading,     setLoading]     = useState(false)

  const PAGE_SIZE = 20

  const load = useCallback(async (p = page, s = search) => {
    setLoading(true)
    try {
      const d = await listUsers({ limit: PAGE_SIZE, offset: p * PAGE_SIZE, search: s })
      setData(d)
    } catch {}
    finally { setLoading(false) }
  }, [page, search])

  useEffect(() => { load() }, [load])

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  async function handleToggleStatus(user) {
    const next = user.status === 'active' ? 'inactive' : 'active'
    try {
      await setUserStatus(user.id, next)
      showToast(`${user.full_name} ${next === 'active' ? 'reactivated' : 'deactivated'}`)
      load()
    } catch (err) { showToast(err.message) }
  }

  async function handleResetPw(user) {
    if (!confirm(`Reset password for ${user.full_name}? A new temporary password will be emailed.`)) return
    try {
      await adminResetPassword(user.id)
      showToast(`Password reset email sent to ${user.email}`)
    } catch (err) { showToast(err.message) }
  }

  const totalPages = Math.ceil(data.total / PAGE_SIZE)

  return (
    <div>
      {/* Create / Edit modal */}
      {modal && (
        <UserModal
          user={modal === 'create' ? null : modal}
          onSave={() => { setModal(null); load(); showToast('Saved successfully') }}
          onClose={() => setModal(null)}
        />
      )}

      {/* Set Password modal */}
      {setPwTarget && (
        <SetPasswordModal
          user={setPwTarget}
          onDone={() => { setSetPwTarget(null); showToast(`Password updated for ${setPwTarget.email}`) }}
          onClose={() => setSetPwTarget(null)}
        />
      )}

      {toast && (
        <div className="fixed top-4 right-4 z-40 bg-gray-800 text-white text-sm px-4 py-2.5 rounded-lg shadow-lg">
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Users</h1>
          <p className="text-gray-500 text-sm mt-0.5">{data.total} total</p>
        </div>
        <button onClick={() => setModal('create')}
          className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors">
          + New User
        </button>
      </div>

      {/* Search */}
      <div className="mb-4">
        <input
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(0); load(0, e.target.value) }}
          placeholder="Search by name or email…"
          className="w-full max-w-sm border border-gray-300 rounded-lg px-3 py-2 text-sm
                     focus:ring-2 focus:ring-blue-500 focus:outline-none"
        />
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {['Name', 'Email', 'Role', 'Status', 'Last Login', 'Created', 'Actions'].map(h => (
                <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">Loading…</td></tr>
            ) : data.items.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">No users found.</td></tr>
            ) : data.items.map(u => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-800">{u.full_name}</td>
                <td className="px-4 py-3 text-gray-600">{u.email}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${ROLE_BADGE[u.role]}`}>
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_BADGE[u.status]}`}>
                    {u.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500">{fmtDate(u.last_login_at)}</td>
                <td className="px-4 py-3 text-gray-500">{fmtDate(u.created_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <button onClick={() => setModal(u)}
                      className="text-xs text-blue-600 hover:underline">Edit</button>
                    <button onClick={() => setSetPwTarget(u)}
                      className="text-xs text-indigo-600 hover:underline font-medium">Set pw</button>
                    <button onClick={() => handleToggleStatus(u)}
                      className={`text-xs hover:underline ${u.status === 'active' ? 'text-orange-500' : 'text-green-600'}`}>
                      {u.status === 'active' ? 'Deactivate' : 'Activate'}
                    </button>
                    <button onClick={() => handleResetPw(u)}
                      className="text-xs text-gray-400 hover:underline">Email reset</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
