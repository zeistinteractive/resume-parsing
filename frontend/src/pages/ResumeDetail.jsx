import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getResume, deleteResume, downloadUrl } from '../api'

function Section({ title, children }) {
  return (
    <div className="mb-6">
      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3 border-b pb-1">{title}</h2>
      {children}
    </div>
  )
}

export default function ResumeDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [resume, setResume] = useState(null)
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  useEffect(() => {
    getResume(id)
      .then(setResume)
      .catch(() => navigate('/'))
      .finally(() => setLoading(false))
  }, [id, navigate])

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await deleteResume(id)
      navigate('/')
    } catch (e) {
      alert(e.message)
      setDeleting(false)
    }
  }

  if (loading) return (
    <div className="animate-pulse space-y-4 mt-4">
      <div className="h-8 bg-gray-200 rounded w-64" />
      <div className="h-4 bg-gray-100 rounded w-48" />
      <div className="h-24 bg-gray-100 rounded" />
    </div>
  )

  if (!resume) return null
  const p = resume.parsed_data || {}

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <button onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 mb-3 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors">
            ← Back to results
          </button>
          <h1 className="text-3xl font-bold text-gray-900">{p.name || resume.filename}</h1>
          {p.email && <p className="text-gray-500 mt-1">{p.email}{p.phone ? ` · ${p.phone}` : ''}</p>}
        </div>
        <div className="flex gap-2 shrink-0 mt-6">
          <a href={downloadUrl(id)} download
            className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-700 font-medium">
            ⬇ Download
          </a>
          <button onClick={() => setShowConfirm(true)}
            className="px-4 py-2 text-sm border border-red-200 rounded-lg hover:bg-red-50 text-red-600 font-medium">
            🗑 Delete
          </button>
        </div>
      </div>

      {/* Delete confirm modal */}
      {showConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 shadow-xl max-w-sm w-full mx-4">
            <h3 className="font-semibold text-lg mb-2">Delete resume?</h3>
            <p className="text-gray-500 text-sm mb-4">This will permanently delete "{resume.filename}". This cannot be undone.</p>
            <div className="flex gap-3">
              <button onClick={() => setShowConfirm(false)}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleting}
                className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-60">
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        {/* Summary */}
        {p.summary && (
          <Section title="Summary">
            <p className="text-gray-700 leading-relaxed">{p.summary}</p>
          </Section>
        )}

        {/* Skills */}
        {p.skills?.length > 0 && (
          <Section title="Skills">
            <div className="flex flex-wrap gap-2">
              {p.skills.map(s => (
                <span key={s} className="bg-blue-50 text-blue-700 text-sm px-3 py-1 rounded-full font-medium">{s}</span>
              ))}
            </div>
          </Section>
        )}

        {/* Experience */}
        {p.experience?.length > 0 && (
          <Section title="Experience">
            <div className="space-y-5">
              {p.experience.map((e, i) => (
                <div key={i} className="border-l-2 border-blue-200 pl-4">
                  <div className="flex items-start justify-between gap-2 flex-wrap">
                    <div>
                      <p className="font-semibold text-gray-900">{e.title}</p>
                      <p className="text-gray-600 text-sm">{e.company}</p>
                    </div>
                    <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">{e.dates}</span>
                  </div>
                  {e.description && (
                    <p className="text-gray-600 text-sm mt-2 leading-relaxed">{e.description}</p>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Education */}
        {p.education?.length > 0 && (
          <Section title="Education">
            <div className="space-y-3">
              {p.education.map((e, i) => (
                <div key={i} className="flex items-start justify-between gap-2 flex-wrap">
                  <div>
                    <p className="font-medium text-gray-900">{e.degree}</p>
                    <p className="text-gray-500 text-sm">{e.institution}</p>
                  </div>
                  <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">{e.dates}</span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Raw file info */}
        <div className="mt-4 pt-4 border-t border-gray-100 text-xs text-gray-400 flex gap-4">
          <span>📎 {resume.filename}</span>
          <span>🕐 {new Date(resume.uploaded_at).toLocaleDateString()}</span>
          <span>📊 Status: {resume.parse_status}</span>
        </div>
      </div>
    </div>
  )
}
