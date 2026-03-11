import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadResume, listResumes, deleteResume } from '../api'

// ─── Constants ────────────────────────────────────────────────────────────────

const PAGE_SIZE   = 20
const MAX_FILES   = 100
const CONCURRENCY = 3

const STATUS_CFG = {
  queued:     { icon: '🕐', label: 'Queued',      cls: 'bg-gray-100 text-gray-600'     },
  uploading:  { icon: '⬆️', label: 'Uploading',   cls: 'bg-blue-100 text-blue-700'     },
  processing: { icon: '🤖', label: 'Processing',  cls: 'bg-yellow-100 text-yellow-700' },
  parsed:     { icon: '✅', label: 'Parsed',       cls: 'bg-green-100 text-green-700'   },
  failed:     { icon: '❌', label: 'Failed',       cls: 'bg-red-100 text-red-700'       },
  duplicate:  { icon: '🔁', label: 'Duplicate',   cls: 'bg-purple-100 text-purple-700' },
}

const RESUME_STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800',
  success: 'bg-green-100 text-green-800',
  failed:  'bg-red-100 text-red-800',
}
const RESUME_STATUS_LABELS = {
  pending: '⏳ Parsing…',
  success: '✅ Parsed',
  failed:  '❌ Failed',
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

let _lid = 0
const nextId = () => ++_lid

function fmtSize(bytes) {
  if (bytes < 1024)         return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function Upload() {
  // -- Queue state -------------------------------------------------------------
  const [queue, setQueue]     = useState([])   // [{localId, filename, size, status, resumeId, duplicateOf, dupCandidateOf, candidateName, error}]
  const queueRef              = useRef([])      // shadow ref for use in async callbacks
  const fileMapRef            = useRef({})      // localId → File object
  const activeRef             = useRef(0)       // count of in-flight uploads
  const uploadingIds          = useRef(new Set()) // Set of localIds currently uploading

  // -- Existing resume list ----------------------------------------------------
  const [items, setItems]     = useState([])
  const [total, setTotal]     = useState(0)
  const [page, setPage]       = useState(0)

  // -- UI state ----------------------------------------------------------------
  const [dragging, setDragging] = useState(false)
  const [toast, setToast]       = useState(null)
  const inputRef                = useRef()
  const navigate                = useNavigate()

  // Keep queueRef in sync with queue state
  useEffect(() => { queueRef.current = queue }, [queue])

  // ─── Existing resume list ──────────────────────────────────────────────────

  const fetchPage = useCallback(async (p) => {
    try {
      const data = await listResumes(PAGE_SIZE, p * PAGE_SIZE)
      setItems(data.items)
      setTotal(data.total)
    } catch {}
  }, [])

  useEffect(() => { fetchPage(page) }, [page, fetchPage])

  // ─── SSE ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    const es = new EventSource('/api/events')

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)

        // Update queue items that match this resume_id
        setQueue(prev => prev.map(item => {
          if (item.resumeId !== event.resume_id) return item
          if (event.status === 'processing') {
            return { ...item, status: 'processing' }
          }
          if (event.status === 'success') {
            return {
              ...item,
              status:          'parsed',
              candidateName:   event.candidate_name ?? item.candidateName,
              dupCandidateOf:  event.is_duplicate_candidate ? event.duplicate_of : null,
            }
          }
          if (event.status === 'failed') {
            return { ...item, status: 'failed', error: event.error ?? 'Parse error' }
          }
          return item
        }))

        // Also refresh the resume list when something finishes
        if (event.status === 'success' || event.status === 'failed') {
          fetchPage(page)
        }

        // Update existing resume list for processing events too
        setItems(prev => prev.map(r =>
          r.id === event.resume_id
            ? { ...r,
                parse_status:   event.status === 'success' ? 'success'
                              : event.status === 'failed'  ? 'failed'
                              : r.parse_status,
                candidate_name: event.candidate_name ?? r.candidate_name }
            : r
        ))
      } catch {}
    }

    return () => es.close()
  }, [fetchPage, page])

  // ─── Upload logic ──────────────────────────────────────────────────────────

  const updateItem = (localId, patch) => {
    setQueue(prev => prev.map(it => it.localId === localId ? { ...it, ...patch } : it))
  }

  const startUpload = useCallback(async (item) => {
    const { localId } = item
    activeRef.current++
    uploadingIds.current.add(localId)
    updateItem(localId, { status: 'uploading' })

    const file = fileMapRef.current[localId]
    try {
      const res = await uploadResume(file)

      if (res.duplicate) {
        updateItem(localId, {
          status:     'duplicate',
          resumeId:   res.id,
          duplicateOf: res.duplicate_of,
        })
      } else {
        // Queued for parsing — SSE will update to processing → parsed/failed
        updateItem(localId, {
          status:   'processing',
          resumeId: res.id,
        })
        // Refresh list to show the new entry
        fetchPage(0)
        if (page !== 0) setPage(0)
      }
    } catch (err) {
      updateItem(localId, { status: 'failed', error: err.message })
    } finally {
      activeRef.current--
      uploadingIds.current.delete(localId)

      // Pick next queued item
      const next = queueRef.current.find(
        it => it.status === 'queued' && !uploadingIds.current.has(it.localId)
      )
      if (next && activeRef.current < CONCURRENCY) {
        startUpload(next)
      }
    }
  }, [fetchPage, page])

  const addFiles = useCallback((fileList) => {
    const files = Array.from(fileList)
    if (files.length === 0) return

    const current = queueRef.current.length
    if (current + files.length > MAX_FILES) {
      setToast({ msg: `Maximum ${MAX_FILES} files per batch. Only first ${MAX_FILES - current} added.`, type: 'warn' })
    }

    const toAdd = files.slice(0, Math.max(0, MAX_FILES - current))
    if (toAdd.length === 0) return

    const newItems = toAdd.map(f => {
      const localId = nextId()
      fileMapRef.current[localId] = f
      return { localId, filename: f.name, size: f.size, status: 'queued', resumeId: null, duplicateOf: null, dupCandidateOf: null, candidateName: null, error: null }
    })

    setQueue(prev => {
      const updated = [...prev, ...newItems]
      queueRef.current = updated

      // Kick off uploads up to CONCURRENCY
      const slots = CONCURRENCY - activeRef.current
      const toStart = newItems.slice(0, slots)
      toStart.forEach(it => startUpload(it))

      return updated
    })
  }, [startUpload])

  // ─── Drop / file input handlers ───────────────────────────────────────────

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    addFiles(e.dataTransfer.files)
  }

  const handleFileInput = (e) => {
    addFiles(e.target.files)
    if (inputRef.current) inputRef.current.value = ''
  }

  // ─── Queue derived state ───────────────────────────────────────────────────

  const total_q   = queue.length
  const doneCount = queue.filter(it => ['parsed','failed','duplicate'].includes(it.status)).length
  const allDone   = total_q > 0 && doneCount === total_q
  const progress  = total_q > 0 ? Math.round((doneCount / total_q) * 100) : 0

  const clearDone = () => {
    setQueue(prev => {
      const remaining = prev.filter(it => !['parsed','failed','duplicate'].includes(it.status))
      queueRef.current = remaining
      return remaining
    })
  }

  // ─── Resume list handlers ──────────────────────────────────────────────────

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3500)
  }

  const handleDelete = async (e, id, filename) => {
    e.stopPropagation()
    if (!confirm(`Delete "${filename}"?`)) return
    try {
      await deleteResume(id)
      showToast('Deleted.', 'info')
      if (items.length === 1 && page > 0) setPage(p => p - 1)
      else fetchPage(page)
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1
  const to   = Math.min((page + 1) * PAGE_SIZE, total)

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-800 mb-1">Upload Resumes</h1>
      <p className="text-gray-500 mb-6">
        Drag &amp; drop up to {MAX_FILES} files at once. AI parses them in parallel.
      </p>

      {/* ── Drop zone ─────────────────────────────────────────────────────── */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all
          ${dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'}`}
      >
        <div className="text-5xl mb-3">📂</div>
        <p className="text-lg font-medium text-gray-700">Drag &amp; drop resumes here</p>
        <p className="text-sm text-gray-400 mt-1">
          or click to browse · PDF, DOCX, DOC · max 5 MB each · up to {MAX_FILES} files
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc"
          className="hidden"
          onChange={handleFileInput}
        />
      </div>

      {/* ── Toast ─────────────────────────────────────────────────────────── */}
      {toast && (
        <div className={`mt-4 px-4 py-3 rounded-lg text-sm font-medium
          ${toast.type === 'error' ? 'bg-red-50 text-red-700 border border-red-200' :
            toast.type === 'warn'  ? 'bg-yellow-50 text-yellow-700 border border-yellow-200' :
            toast.type === 'info'  ? 'bg-gray-100 text-gray-700' :
            'bg-green-50 text-green-700 border border-green-200'}`}>
          {toast.msg}
        </div>
      )}

      {/* ── Upload queue ──────────────────────────────────────────────────── */}
      {queue.length > 0 && (
        <div className="mt-6 bg-white border border-gray-200 rounded-xl overflow-hidden">
          {/* Queue header + progress */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <span className="text-sm font-semibold text-gray-700 shrink-0">
                {doneCount}/{total_q} files
              </span>
              <div className="flex-1 bg-gray-100 rounded-full h-2 min-w-0">
                <div
                  className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <span className="text-xs text-gray-400 shrink-0">{progress}%</span>
            </div>
            {allDone && (
              <button
                onClick={clearDone}
                className="ml-4 text-xs text-gray-500 hover:text-gray-800 underline shrink-0"
              >
                Clear all
              </button>
            )}
          </div>

          {/* Queue items */}
          <div className="max-h-80 overflow-y-auto divide-y divide-gray-50">
            {queue.map(item => {
              const cfg = STATUS_CFG[item.status] ?? STATUS_CFG.queued
              return (
                <div key={item.localId} className="flex items-start gap-3 px-4 py-2.5">
                  {/* Status icon */}
                  <span className="text-lg mt-0.5 shrink-0">{cfg.icon}</span>

                  {/* File info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">
                      {item.candidateName ?? item.filename}
                    </p>
                    {item.candidateName && (
                      <p className="text-xs text-gray-400 truncate">{item.filename}</p>
                    )}
                    <div className="flex flex-wrap items-center gap-2 mt-0.5">
                      <span className="text-xs text-gray-400">{fmtSize(item.size)}</span>
                      {/* Duplicate file */}
                      {item.status === 'duplicate' && item.duplicateOf && (
                        <span className="text-xs text-purple-600">
                          → same file as{' '}
                          <button
                            onClick={() => navigate(`/resume/${item.duplicateOf}`)}
                            className="underline hover:text-purple-800"
                          >
                            #{item.duplicateOf}
                          </button>
                        </span>
                      )}
                      {/* Duplicate candidate warning */}
                      {item.dupCandidateOf && (
                        <span className="text-xs text-amber-600">
                          ⚠️ possible duplicate of{' '}
                          <button
                            onClick={() => navigate(`/resume/${item.dupCandidateOf}`)}
                            className="underline hover:text-amber-800"
                          >
                            #{item.dupCandidateOf}
                          </button>
                        </span>
                      )}
                      {item.error && (
                        <span className="text-xs text-red-500">{item.error}</span>
                      )}
                    </div>
                  </div>

                  {/* Status badge */}
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${cfg.cls}`}>
                    {cfg.label}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Existing resume list ───────────────────────────────────────────── */}
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
            <button
              onClick={() => navigate('/search')}
              className="text-sm text-blue-600 hover:underline"
            >
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
                    <span className={`text-xs font-medium px-2 py-1 rounded-full ${RESUME_STATUS_COLORS[r.parse_status]}`}>
                      {RESUME_STATUS_LABELS[r.parse_status]}
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
                <span className="text-sm text-gray-500">Page {page + 1} of {totalPages}</span>
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
