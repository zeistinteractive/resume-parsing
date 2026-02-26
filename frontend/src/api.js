const BASE = '/api'

export async function uploadResume(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Upload failed')
  }
  return res.json()
}

export async function listResumes(limit = 20, offset = 0) {
  const res = await fetch(`${BASE}/resumes?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error('Failed to fetch resumes')
  return res.json()
}

export async function getResume(id) {
  const res = await fetch(`${BASE}/resumes/${id}`)
  if (!res.ok) throw new Error('Resume not found')
  return res.json()
}

export async function deleteResume(id) {
  const res = await fetch(`${BASE}/resumes/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Delete failed')
  return res.json()
}

/**
 * Search resumes with optional keyword + structured filters.
 * @param {Object} params
 * @param {string}   params.q
 * @param {string}   params.mode          'or' | 'and'
 * @param {string}   params.title
 * @param {string[]} params.skills        array of skill strings
 * @param {number}   params.exp_min
 * @param {number}   params.exp_max
 * @param {string}   params.location
 * @param {string}   params.education
 * @param {string}   params.notice_period
 * @param {string}   params.date_from     YYYY-MM-DD
 * @param {string}   params.date_to       YYYY-MM-DD
 * @param {string}   params.sort          'relevance'|'exp_desc'|'exp_asc'|'date_desc'
 * @param {number}   params.limit         25 | 50 | 100
 * @param {number}   params.offset
 */
export async function searchResumes(params = {}) {
  const p = new URLSearchParams()

  if (params.q)             p.set('q',             params.q)
  if (params.mode)          p.set('mode',           params.mode)
  if (params.title)         p.set('title',          params.title)
  if (params.skills?.length) p.set('skills',        params.skills.join(','))
  if (params.exp_min != null) p.set('exp_min',      params.exp_min)
  if (params.exp_max != null) p.set('exp_max',      params.exp_max)
  if (params.location)      p.set('location',       params.location)
  if (params.education)     p.set('education',      params.education)
  if (params.notice_period) p.set('notice_period',  params.notice_period)
  if (params.date_from)     p.set('date_from',      params.date_from)
  if (params.date_to)       p.set('date_to',        params.date_to)
  if (params.sort)          p.set('sort',           params.sort)
  if (params.limit)         p.set('limit',          params.limit)
  if (params.offset)        p.set('offset',         params.offset)

  const res = await fetch(`${BASE}/search?${p}`)
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Search failed')
  }
  return res.json()
}

export async function autocomplete(type, q) {
  if (!q) return []
  const res = await fetch(`${BASE}/autocomplete/${type}?q=${encodeURIComponent(q)}`)
  if (!res.ok) return []
  return res.json()
}

export async function listSavedSearches() {
  const res = await fetch(`${BASE}/saved-searches`)
  if (!res.ok) throw new Error('Failed to load saved searches')
  return res.json()
}

export async function createSavedSearch(name, query, filters) {
  const res = await fetch(`${BASE}/saved-searches`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ name, query, filters }),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Save failed')
  }
  return res.json()
}

export async function deleteSavedSearch(id) {
  const res = await fetch(`${BASE}/saved-searches/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Delete failed')
  return res.json()
}

export function downloadUrl(id) {
  return `${BASE}/resumes/${id}/download`
}

export async function bulkDownload(ids) {
  const res = await fetch(`${BASE}/download/bulk`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ ids }),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Bulk download failed')
  }
  return res.blob()
}
