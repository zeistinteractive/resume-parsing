import { useState } from 'react'
import { Link } from 'react-router-dom'
import { forgotPasswordApi } from '../api'

export default function ForgotPassword() {
  const [email,   setEmail]   = useState('')
  const [sent,    setSent]    = useState(false)
  const [error,   setError]   = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await forgotPasswordApi(email)
      setSent(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🔑</div>
          <h1 className="text-2xl font-bold text-gray-900">Forgot Password</h1>
          <p className="text-gray-500 mt-1 text-sm">
            Enter your email and we'll send a reset link.
          </p>
        </div>

        <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-8">
          {sent ? (
            <div className="text-center space-y-4">
              <div className="text-4xl">📧</div>
              <p className="text-gray-700 font-medium">Check your inbox</p>
              <p className="text-gray-500 text-sm">
                If an account with <strong>{email}</strong> exists, a reset link has been sent.
                The link expires in 1 hour.
              </p>
              <Link to="/login" className="block text-blue-600 hover:underline text-sm mt-4">
                ← Back to login
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email address</label>
                <input
                  type="email"
                  required
                  autoFocus
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm
                             focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <button type="submit" disabled={loading}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-60
                           text-white font-semibold py-2.5 rounded-lg text-sm transition-colors">
                {loading ? 'Sending…' : 'Send Reset Link'}
              </button>
              <Link to="/login" className="block text-center text-sm text-gray-500 hover:text-gray-700 mt-2">
                ← Back to login
              </Link>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
