import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadResume, listResumes, deleteResume } from '../api'

const STATUS_COLORS = {
  pending:  'bg-yellow-100 text-yellow-800',
  success:  'bg-green-100 text-green-800',
  failed:   'bg-red-100 text-red-800',
}
const STATUS_LABELS = { pending: '⏳ Parsing…', success: '✅ Parsed', failed: '❌ Failed' }

export default function Upload() {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [toast, setToast] = useState(null)
  const [resumes, setResumes] = useState([])
  const inputRef = useRef()
  const navigate = useNavigate()
  const pollRef = useRef()

  const fetchResumes = useCallback(async () => {
    try { setResumes(await listResumes()) } catch {}
  }, [])

  useEffect(() => {
    fetchResumes()
    pollRef.current = setInterval(fetchResumes, 2500)
    return () => clearInterval(pollRef.current)
  }, [fetchResumes])

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
      fetchResumes()
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault(); setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const handleDelete = async (e, id, filename) => {
    e.stopPropagation()
    if (!confirm(`Delete "${filename}"?`)) return
    try {
      await deleteResume(id)
      showToast('Deleted.', 'info')
      fetchResumes()
    } catch (e) { showToast(e.message, 'error') }
  }

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
            toast.type === 'info' ? 'bg-gray-100 text-gray-700' :
            'bg-green-50 text-green-700 border border-green-200'}`}>
          {toast.msg}
        </div>
      )}

      {/* Resume list */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-gray-700">All Resumes ({resumes.length})</h2>
          {resumes.some(r => r.parse_status === 'success') && (
            <button onClick={() => navigate('/search')}
              className="text-sm text-blue-600 hover:underline">
              Search resumes →
            </button>
          )}
        </div>

        {resumes.length === 0 ? (
          <p className="text-gray-400 text-sm py-8 text-center">No resumes yet. Upload one above!</p>
        ) : (
          <div className="space-y-2">
            {resumes.map(r => (
              <div key={r.id}
                onClick={() => r.parse_status === 'success' && navigate(`/resume/${r.id}`)}
                className={`flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-3 
                  ${r.parse_status === 'success' ? 'hover:border-blue-300 hover:shadow-sm cursor-pointer' : ''} transition-all`}>
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-xl">{r.parse_status === 'success' ? '👤' : r.parse_status === 'failed' ? '⚠️' : '⏳'}</span>
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
        )}
      </div>
    </div>
  )
}
