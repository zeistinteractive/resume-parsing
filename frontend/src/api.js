const BASE = '/api'

// ── Auth helpers ──────────────────────────────────────────────────────────────

function _token() {
  return localStorage.getItem('re_token')
}

function _authHeaders(extra = {}) {
  const t = _token()
  return t ? { Authorization: `Bearer ${t}`, ...extra } : { ...extra }
}

async function _fetch(url, opts = {}) {
  const res = await fetch(url, opts)
  if (res.status === 401) {
    window.dispatchEvent(new Event('auth:unauthorized'))
  }
  return res
}

// ── Auth API ──────────────────────────────────────────────────────────────────

export async function loginApi(email, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ email, password }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Login failed')
  return data   // { access_token, token_type, user }
}

export async function changePasswordApi(currentPassword, newPassword) {
  const res = await _fetch(`${BASE}/auth/change-password`, {
    method:  'POST',
    headers: { ..._authHeaders(), 'Content-Type': 'application/json' },
    body:    JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Failed to change password')
  return data
}

export async function forgotPasswordApi(email) {
  const res = await fetch(`${BASE}/auth/forgot-password`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ email }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Request failed')
  return data
}

export async function resetPasswordApi(token, newPassword) {
  const res = await fetch(`${BASE}/auth/reset-password`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ token, new_password: newPassword }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Reset failed')
  return data
}

// ── Resume API ────────────────────────────────────────────────────────────────

export async function uploadResume(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await _fetch(`${BASE}/upload`, {
    method:  'POST',
    headers: _authHeaders(),
    body:    form,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Upload failed')
  return data
}

export async function listResumes(limit = 20, offset = 0) {
  const res = await _fetch(`${BASE}/resumes?limit=${limit}&offset=${offset}`, {
    headers: _authHeaders(),
  })
  if (!res.ok) throw new Error('Failed to fetch resumes')
  return res.json()
}

export async function getResume(id) {
  const res = await _fetch(`${BASE}/resumes/${id}`, { headers: _authHeaders() })
  if (!res.ok) throw new Error('Resume not found')
  return res.json()
}

export async function deleteResume(id) {
  const res = await _fetch(`${BASE}/resumes/${id}`, {
    method:  'DELETE',
    headers: _authHeaders(),
  })
  if (!res.ok) throw new Error('Delete failed')
  return res.json()
}

export async function searchResumes(params = {}) {
  const p = new URLSearchParams()
  if (params.q)              p.set('q',             params.q)
  if (params.mode)           p.set('mode',           params.mode)
  if (params.title)          p.set('title',          params.title)
  if (params.skills?.length) p.set('skills',         params.skills.join(','))
  if (params.exp_min != null) p.set('exp_min',       params.exp_min)
  if (params.exp_max != null) p.set('exp_max',       params.exp_max)
  if (params.location)       p.set('location',       params.location)
  if (params.education)      p.set('education',      params.education)
  if (params.notice_period)  p.set('notice_period',  params.notice_period)
  if (params.date_from)      p.set('date_from',      params.date_from)
  if (params.date_to)        p.set('date_to',        params.date_to)
  if (params.uploaded_by)    p.set('uploaded_by',    params.uploaded_by)
  if (params.sort)           p.set('sort',           params.sort)
  if (params.limit)          p.set('limit',          params.limit)
  if (params.offset)         p.set('offset',         params.offset)

  const res = await _fetch(`${BASE}/search?${p}`, { headers: _authHeaders() })
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || 'Search failed') }
  return res.json()
}

export async function getUploaders() {
  const res = await _fetch(`${BASE}/uploaders`, { headers: _authHeaders() })
  if (!res.ok) return []
  return res.json()
}

export async function autocomplete(type, q) {
  if (!q) return []
  const res = await _fetch(
    `${BASE}/autocomplete/${type}?q=${encodeURIComponent(q)}`,
    { headers: _authHeaders() },
  )
  if (!res.ok) return []
  return res.json()
}

export async function listSavedSearches() {
  const res = await _fetch(`${BASE}/saved-searches`, { headers: _authHeaders() })
  if (!res.ok) throw new Error('Failed to load saved searches')
  return res.json()
}

export async function createSavedSearch(name, query, filters) {
  const res = await _fetch(`${BASE}/saved-searches`, {
    method:  'POST',
    headers: { ..._authHeaders(), 'Content-Type': 'application/json' },
    body:    JSON.stringify({ name, query, filters }),
  })
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || 'Save failed') }
  return res.json()
}

export async function deleteSavedSearch(id) {
  const res = await _fetch(`${BASE}/saved-searches/${id}`, {
    method:  'DELETE',
    headers: _authHeaders(),
  })
  if (!res.ok) throw new Error('Delete failed')
  return res.json()
}

export async function getDownloadUrl(id) {
  // Get a one-time token and return the public token URL (no auth needed to redeem)
  const res = await _fetch(`${BASE}/download/token/${id}`, { headers: _authHeaders() })
  if (!res.ok) throw new Error('Failed to get download token')
  const { url } = await res.json()
  return url
}

export async function getDownloadHistory(limit = 25, offset = 0) {
  const res = await _fetch(`${BASE}/download/history?limit=${limit}&offset=${offset}`, {
    headers: _authHeaders(),
  })
  if (!res.ok) throw new Error('Failed to fetch download history')
  return res.json()
}

export function downloadUrl(id) {
  return `${BASE}/resumes/${id}/download`
}

export async function bulkDownload(ids) {
  const res = await _fetch(`${BASE}/download/bulk`, {
    method:  'POST',
    headers: { ..._authHeaders(), 'Content-Type': 'application/json' },
    body:    JSON.stringify({ ids }),
  })
  if (!res.ok) { const e = await res.json(); throw new Error(e.detail || 'Bulk download failed') }
  return res.blob()
}

// ── User Management API (Admin) ───────────────────────────────────────────────

export async function listUsers(params = {}) {
  const p = new URLSearchParams()
  if (params.limit)  p.set('limit',  params.limit)
  if (params.offset) p.set('offset', params.offset)
  if (params.search) p.set('search', params.search)
  const res = await _fetch(`${BASE}/users?${p}`, { headers: _authHeaders() })
  if (!res.ok) throw new Error('Failed to list users')
  return res.json()
}

export async function createUser(full_name, email, role) {
  const res = await _fetch(`${BASE}/users`, {
    method:  'POST',
    headers: { ..._authHeaders(), 'Content-Type': 'application/json' },
    body:    JSON.stringify({ full_name, email, role }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Failed to create user')
  return data
}

export async function updateUser(id, full_name, email, role) {
  const res = await _fetch(`${BASE}/users/${id}`, {
    method:  'PATCH',
    headers: { ..._authHeaders(), 'Content-Type': 'application/json' },
    body:    JSON.stringify({ full_name, email, role }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Failed to update user')
  return data
}

export async function setUserStatus(id, status) {
  const res = await _fetch(`${BASE}/users/${id}/status`, {
    method:  'PATCH',
    headers: { ..._authHeaders(), 'Content-Type': 'application/json' },
    body:    JSON.stringify({ status }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Failed to update status')
  return data
}

export async function adminResetPassword(id) {
  const res = await _fetch(`${BASE}/users/${id}/reset-password`, {
    method:  'POST',
    headers: _authHeaders(),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Failed to reset password')
  return data
}

export async function adminSetPassword(id, newPassword) {
  const res = await _fetch(`${BASE}/users/${id}/set-password`, {
    method:  'POST',
    headers: { ..._authHeaders(), 'Content-Type': 'application/json' },
    body:    JSON.stringify({ new_password: newPassword }),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Failed to set password')
  return data
}

export async function listAuditLogs(params = {}) {
  const p = new URLSearchParams()
  if (params.limit)      p.set('limit',      params.limit)
  if (params.offset)     p.set('offset',     params.offset)
  if (params.user_email) p.set('user_email', params.user_email)
  if (params.action)     p.set('action',     params.action)
  if (params.date_from)  p.set('date_from',  params.date_from)
  if (params.date_to)    p.set('date_to',    params.date_to)
  const res = await _fetch(`${BASE}/audit-logs?${p}`, { headers: _authHeaders() })
  if (!res.ok) throw new Error('Failed to fetch audit logs')
  return res.json()
}
