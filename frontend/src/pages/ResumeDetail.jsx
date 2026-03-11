import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getResume, deleteResume, getDownloadUrl } from '../api'

// ── Helpers ───────────────────────────────────────────────────────────────────

function Badge({ children, color = 'slate' }) {
  const colors = {
    indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-100',
    emerald:'bg-emerald-50 text-emerald-700 ring-emerald-100',
    amber:  'bg-amber-50 text-amber-700 ring-amber-100',
    slate:  'bg-slate-100 text-slate-600 ring-slate-200',
  }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ring-1 ring-inset ${colors[color]}`}>
      {children}
    </span>
  )
}

function MetaItem({ icon, label, value }) {
  if (!value) return null
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-slate-400 shrink-0">{icon}</span>
      <span className="text-slate-500 shrink-0">{label}</span>
      <span className="font-medium text-slate-800">{value}</span>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div>
      <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">{title}</h2>
      {children}
    </div>
  )
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-32 bg-white rounded-2xl border border-slate-200" />
      <div className="grid grid-cols-3 gap-4">
        <div className="h-24 bg-white rounded-2xl border border-slate-200 col-span-1" />
        <div className="h-24 bg-white rounded-2xl border border-slate-200 col-span-2" />
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function ResumeDetail() {
  const { id }     = useParams()
  const navigate   = useNavigate()
  const [resume,     setResume]    = useState(null)
  const [loading,    setLoading]   = useState(true)
  const [deleting,   setDeleting]  = useState(false)
  const [confirm,    setConfirm]   = useState(false)
  const [downloading,setDownloading] = useState(false)

  async function handleDownload() {
    setDownloading(true)
    try {
      const url = await getDownloadUrl(id)
      window.location.href = url
    } catch (e) {
      alert('Download failed: ' + e.message)
    } finally {
      setDownloading(false)
    }
  }

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

  if (loading) return <Skeleton />
  if (!resume) return null

  const p = resume.parsed_data || {}

  return (
    <div className="space-y-5">

      {/* ── Back ── */}
      <button
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors group">
        <svg className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
        </svg>
        Back to results
      </button>

      {/* ── Hero card ── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {/* Top stripe */}
        <div className="h-2 bg-gradient-to-r from-indigo-500 via-indigo-400 to-violet-400" />

        <div className="px-7 py-6">
          <div className="flex items-start justify-between gap-4">
            {/* Left: identity */}
            <div className="flex items-start gap-5">
              {/* Avatar */}
              <div className="w-16 h-16 rounded-2xl bg-indigo-100 flex items-center justify-center shrink-0">
                <span className="text-2xl font-bold text-indigo-600">
                  {(p.name || resume.filename)[0].toUpperCase()}
                </span>
              </div>

              {/* Name + title */}
              <div>
                <h1 className="text-2xl font-bold text-slate-900 leading-tight">
                  {p.name || resume.filename}
                </h1>
                {p.current_title && (
                  <p className="text-indigo-600 font-medium mt-0.5">{p.current_title}</p>
                )}
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-sm text-slate-500">
                  {p.email && (
                    <a href={`mailto:${p.email}`} className="hover:text-indigo-600 transition-colors">
                      ✉ {p.email}
                    </a>
                  )}
                  {p.phone && <span>📞 {p.phone}</span>}
                  {p.location && <span>📍 {p.location}</span>}
                </div>
              </div>
            </div>

            {/* Right: actions */}
            <div className="flex gap-2 shrink-0">
              <button
                onClick={handleDownload}
                disabled={downloading}
                className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-medium rounded-xl transition-colors shadow-sm">
                {downloading ? (
                  <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
                  </svg>
                )}
                {downloading ? 'Preparing…' : 'Download'}
              </button>
              <button
                onClick={() => setConfirm(true)}
                className="inline-flex items-center gap-2 px-4 py-2 border border-red-200 text-red-600 hover:bg-red-50 text-sm font-medium rounded-xl transition-colors">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                </svg>
                Delete
              </button>
            </div>
          </div>

          {/* Meta badges */}
          <div className="flex flex-wrap gap-2 mt-5 pt-5 border-t border-slate-100">
            {p.experience_years > 0 && (
              <Badge color="indigo">{p.experience_years} yrs experience</Badge>
            )}
            {p.education_level && <Badge color="slate">{p.education_level}</Badge>}
            {p.notice_period && (
              <Badge color="amber">Notice: {p.notice_period}</Badge>
            )}
            <Badge color="slate">
              Uploaded {new Date(resume.uploaded_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
            </Badge>
          </div>
        </div>
      </div>

      {/* ── Two-column body ── */}
      <div className="grid grid-cols-3 gap-5">

        {/* Left column */}
        <div className="space-y-5">
          {/* Skills */}
          {p.skills?.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <Section title="Skills">
                <div className="flex flex-wrap gap-1.5">
                  {p.skills.map(s => (
                    <span key={s}
                      className="bg-indigo-50 text-indigo-700 text-xs font-medium px-2.5 py-1 rounded-lg ring-1 ring-inset ring-indigo-100">
                      {s}
                    </span>
                  ))}
                </div>
              </Section>
            </div>
          )}

          {/* Quick info */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 space-y-3">
            <Section title="Details">
              <div className="space-y-2.5">
                <MetaItem icon="🎓" label="Education"  value={p.education_level} />
                <MetaItem icon="⏱"  label="Notice"    value={p.notice_period} />
                <MetaItem icon="📁" label="File"       value={resume.filename} />
              </div>
            </Section>
          </div>
        </div>

        {/* Right column */}
        <div className="col-span-2 space-y-5">
          {/* Summary */}
          {p.summary && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <Section title="Summary">
                <p className="text-slate-700 leading-relaxed text-sm">{p.summary}</p>
              </Section>
            </div>
          )}

          {/* Experience timeline */}
          {p.experience?.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <Section title="Experience">
                <div className="relative space-y-5">
                  {/* Vertical line */}
                  <div className="absolute left-[7px] top-2 bottom-2 w-px bg-slate-200" />

                  {p.experience.map((e, i) => (
                    <div key={i} className="relative flex gap-4 pl-7">
                      {/* Dot */}
                      <div className="absolute left-0 top-1.5 w-3.5 h-3.5 rounded-full border-2 border-indigo-500 bg-white shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2 flex-wrap">
                          <div>
                            <p className="font-semibold text-slate-900 text-sm">{e.title}</p>
                            <p className="text-indigo-600 text-xs font-medium mt-0.5">{e.company}</p>
                          </div>
                          {e.dates && (
                            <span className="text-xs text-slate-400 bg-slate-50 border border-slate-200 px-2.5 py-0.5 rounded-full shrink-0">
                              {e.dates}
                            </span>
                          )}
                        </div>
                        {e.description && (
                          <p className="text-slate-600 text-xs mt-1.5 leading-relaxed">{e.description}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            </div>
          )}

          {/* Education */}
          {p.education?.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <Section title="Education">
                <div className="space-y-3">
                  {p.education.map((e, i) => (
                    <div key={i} className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-3">
                        <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center shrink-0 mt-0.5">
                          <span className="text-base">🎓</span>
                        </div>
                        <div>
                          <p className="font-medium text-slate-900 text-sm">{e.degree}</p>
                          <p className="text-slate-500 text-xs mt-0.5">{e.institution}</p>
                        </div>
                      </div>
                      {e.dates && (
                        <span className="text-xs text-slate-400 bg-slate-50 border border-slate-200 px-2.5 py-0.5 rounded-full shrink-0">
                          {e.dates}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            </div>
          )}
        </div>
      </div>

      {/* ── Delete confirm modal ── */}
      {confirm && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 px-4">
          <div className="bg-white rounded-2xl p-6 shadow-2xl max-w-sm w-full">
            <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
              </svg>
            </div>
            <h3 className="font-bold text-lg text-slate-900 text-center mb-1">Delete resume?</h3>
            <p className="text-slate-500 text-sm text-center mb-5">
              "{resume.filename}" will be permanently deleted. This cannot be undone.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setConfirm(false)}
                className="flex-1 px-4 py-2.5 border border-slate-200 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleting}
                className="flex-1 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-medium disabled:opacity-60 transition-colors">
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
