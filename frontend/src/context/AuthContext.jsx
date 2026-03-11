import { createContext, useContext, useState, useEffect } from 'react'

const AuthContext = createContext(null)

const TOKEN_KEY = 're_token'

function parseToken(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    if (payload.exp < Date.now() / 1000) return null   // expired
    return { id: payload.sub, email: payload.email, role: payload.role }
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const t = localStorage.getItem(TOKEN_KEY)
    return t ? parseToken(t) : null
  })

  // Listen for 401 events dispatched by api.js
  useEffect(() => {
    const handle = () => {
      localStorage.removeItem(TOKEN_KEY)
      setUser(null)
    }
    window.addEventListener('auth:unauthorized', handle)
    return () => window.removeEventListener('auth:unauthorized', handle)
  }, [])

  function login(token) {
    localStorage.setItem(TOKEN_KEY, token)
    setUser(parseToken(token))
  }

  async function logout() {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      try {
        await fetch('/api/auth/logout', {
          method:  'POST',
          headers: { Authorization: `Bearer ${token}` },
        })
      } catch {}
    }
    localStorage.removeItem(TOKEN_KEY)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY)
}
