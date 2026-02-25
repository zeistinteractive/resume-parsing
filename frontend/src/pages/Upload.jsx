import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadResume, listResumes, deleteResume } from '../api'

const PAGE_SIZE = 20

const STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800',
  success: 'bg-green-100 text-green-800',
  failed:  'bg-red-100 text-red-800',
}
const STATUS_LABELS = { pending: '⏳ Parsing…', success: '✅ Parsed', failed: '❌ Failed' }

export default function Upload() {
  const [dragging, setDragging]   = useState(false)
  const [uploading, setUploading] = useState(false)
  const [toast, setToast]         = useState(null)
  const [items, setItems]         = useState([])
  const [total, setTotal]         = useState(0)
  const [page, setPage]           = useState(0)
  const inputRef = useRef()
  const navigate = useNavigate()

  const fetchPage = useCallback(async (p) => {
    try {
      const data = await listResumes(PAGE_SIZE, p * PAGE_SIZE)
      setItems(data.items)
      setTotal(data.total)
    } catch {}
  }, [])

  // Re-fetch whenever the user navigates to a different page
  useEffect(() => {
    fetchPage(page)
  }, [page, fetchPage])

  // SSE: one persistent connection for the lifetime of this component.
  // Receives a push the instant a resume finishes parsing — no polling needed.
  useEffect(() => {
    const es = new EventSource('/api/events')

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        setItems(prev => prev.map(r =>
          r.id === event.resume_id
            ? {
                ...r,
                parse_status:   event.status,
                // Show parsed name as soon as it arrives
                candidate_name: event.candidate_name ?? r.candidate_name,
              }
            : r
        ))
      } catch {}
    }

    // EventSource reconnects automatically on error — no manual retry needed
    return () => es.close()
  }, []) // Open once on mount, close on unmount

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const handleFiles = async (files) => {
    const file = files[0]
    if (!file) return
    setUploading(true)
    try {
      await uploadResume(file)
      showToast(`"${file.name}" uploaded! Parsing in background…`)
      // Navigate to page 1 to see the new upload; SSE will update its status
      if (page !== 0) setPage(0)
      else fetchPage(0)
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const handleDelete = async (e, id, filename) => {
    e.stopPropagation()
    if (!confirm(`Delete "${filename}"?`)) return
    try {
      await deleteResume(id)
      showToast('Deleted.', 'info')
      if (items.length === 1 && page > 0) setPage(p => p - 1)
      else fetchPage(page)
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1
  const to   = Math.min((page + 1) * PAGE_SIZE, total)

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-1">Upload Resumes</h1>
      <p className="text-gray-500 mb-6">Drop a PDF or DOCX file. AI will parse it automatically.</p>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all
          ${dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'}
          ${uploading ? 'opacity-60 pointer-events-none' : ''}`}
      >
        <div className="text-5xl mb-3">{uploading ? '⏳' : '📂'}</div>
        <p className="text-lg font-medium text-gray-700">
          {uploading ? 'Uploading…' : 'Drag & drop a resume here'}
        </p>
        <p className="text-sm text-gray-400 mt-1">or click to browse · PDF, DOCX · max 5MB</p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.doc"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {/* Toast */}
      {toast && (
        <div className={`mt-4 px-4 py-3 rounded-lg text-sm font-medium
          ${toast.type === 'error' ? 'bg-red-50 text-red-700 border border-red-200' :
            toast.type === 'info'  ? 'bg-gray-100 text-gray-700' :
            'bg-green-50 text-green-700 border border-green-200'}`}>
          {toast.msg}
        </div>
      )}

      {/* Resume list */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-gray-700">
            All Resumes
            {total > 0 && (
              <span className="font-normal text-gray-400 ml-2 text-sm">
                {from}–{to} of {total}
              </span>
            )}
          </h2>
          {items.some(r => r.parse_status === 'success') && (
            <button onClick={() => navigate('/search')}
              className="text-sm text-blue-600 hover:underline">
              Search resumes →
            </button>
          )}
        </div>

        {total === 0 ? (
          <p className="text-gray-400 text-sm py-8 text-center">No resumes yet. Upload one above!</p>
        ) : (
          <>
            <div className="space-y-2">
              {items.map(r => (
                <div key={r.id}
                  onClick={() => r.parse_status === 'success' && navigate(`/resume/${r.id}`)}
                  className={`flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-3
                    ${r.parse_status === 'success' ? 'hover:border-blue-300 hover:shadow-sm cursor-pointer' : ''} transition-all`}>
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-xl">
                      {r.parse_status === 'success' ? '👤' : r.parse_status === 'failed' ? '⚠️' : '⏳'}
                    </span>
                    <div className="min-w-0">
                      <p className="font-medium text-gray-800 truncate">
                        {r.candidate_name || r.filename}
                      </p>
                      {r.candidate_name && (
                        <p className="text-xs text-gray-400 truncate">{r.filename}</p>
                      )}
                      {r.skills?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {r.skills.slice(0, 5).map(s => (
                            <span key={s} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">{s}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 ml-4 shrink-0">
                    <span className={`text-xs font-medium px-2 py-1 rounded-full ${STATUS_COLORS[r.parse_status]}`}>
                      {STATUS_LABELS[r.parse_status]}
                    </span>
                    <button
                      onClick={(e) => handleDelete(e, r.id, r.filename)}
                      className="text-gray-300 hover:text-red-500 transition-colors text-lg leading-none"
                      title="Delete">×</button>
                  </div>
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100">
                <button
                  onClick={() => setPage(p => p - 1)}
                  disabled={page === 0}
                  className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-600
                    hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                  ← Previous
                </button>
                <span className="text-sm text-gray-500">
                  Page {page + 1} of {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => p + 1)}
                  disabled={page >= totalPages - 1}
                  className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-600
                    hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
