import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { resetPasswordApi } from '../api'

export default function ResetPassword() {
  const [searchParams]                  = useSearchParams()
  const token                           = searchParams.get('token') ?? ''
  const [form,    setForm]              = useState({ next: '', confirm: '' })
  const [done,    setDone]              = useState(false)
  const [error,   setError]             = useState('')
  const [loading, setLoading]           = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    if (form.next !== form.confirm) { setError('Passwords do not match'); return }
    if (form.next.length < 8)       { setError('Password must be at least 8 characters'); return }
    setLoading(true)
    try {
      await resetPasswordApi(token, form.next)
      setDone(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!token) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-center">
        <p className="text-red-600 font-medium">Invalid reset link.</p>
        <Link to="/forgot-password" className="text-blue-600 hover:underline text-sm mt-2 block">
          Request a new one →
        </Link>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🔒</div>
          <h1 className="text-2xl font-bold text-gray-900">Reset Password</h1>
        </div>

        <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-8">
          {done ? (
            <div className="text-center space-y-4">
              <div className="text-4xl">✅</div>
              <p className="text-gray-700 font-medium">Password reset successfully!</p>
              <Link to="/login"
                className="inline-block bg-blue-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-blue-700">
                Sign in →
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}
              {[
                { label: 'New password',     key: 'next'    },
                { label: 'Confirm password', key: 'confirm' },
              ].map(({ label, key }) => (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                  <input
                    type="password"
                    required
                    value={form[key]}
                    onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm
                               focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
              ))}
              <button type="submit" disabled={loading}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-60
                           text-white font-semibold py-2.5 rounded-lg text-sm transition-colors">
                {loading ? 'Resetting…' : 'Reset Password'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
