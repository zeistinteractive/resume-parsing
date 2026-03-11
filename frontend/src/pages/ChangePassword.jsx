import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { changePasswordApi } from '../api'

export default function ChangePassword() {
  const { logout } = useAuth()
  const navigate   = useNavigate()

  const [form,    setForm]    = useState({ current: '', next: '', confirm: '' })
  const [error,   setError]   = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    if (form.next !== form.confirm) { setError('New passwords do not match'); return }
    if (form.next.length < 8)       { setError('New password must be at least 8 characters'); return }
    setLoading(true)
    try {
      await changePasswordApi(form.current, form.next)
      setSuccess(true)
      setTimeout(() => { logout(); navigate('/login') }, 2000)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto">
      <h1 className="text-2xl font-bold text-gray-800 mb-1">Change Password</h1>
      <p className="text-gray-500 mb-6 text-sm">You will be logged out after changing your password.</p>

      <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>
        )}
        {success && (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm">
            Password changed! Redirecting to login…
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {[
            { label: 'Current password', key: 'current' },
            { label: 'New password',     key: 'next'    },
            { label: 'Confirm new',      key: 'confirm' },
          ].map(({ label, key }) => (
            <div key={key}>
              <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
              <input
                type="password"
                required
                value={form[key]}
                onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm
                           focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          ))}

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={() => navigate(-1)}
              className="px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50">
              Cancel
            </button>
            <button type="submit" disabled={loading || success}
              className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-60
                         text-white font-semibold py-2 rounded-lg text-sm transition-colors">
              {loading ? 'Saving…' : 'Change Password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
