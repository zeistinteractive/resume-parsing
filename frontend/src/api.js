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

export async function listResumes() {
  const res = await fetch(`${BASE}/resumes`)
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

export async function searchResumes(query, mode = 'or') {
  const res = await fetch(`${BASE}/search?q=${encodeURIComponent(query)}&mode=${mode}`)
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Search failed')
  }
  return res.json()
}

export function downloadUrl(id) {
  return `${BASE}/resumes/${id}/download`
}
