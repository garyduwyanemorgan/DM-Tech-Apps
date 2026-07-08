import React, { useState, useRef, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { Save, Upload, Sparkles, FileText } from 'lucide-react'
import { PageHeader } from './PageHeader'

// ── Extraction progress ───────────────────────────────────────────────────────
// Stages: compress (client-side) → upload (real %) → ai (indeterminate + timer)
type ExtractStage = 'idle' | 'compress' | 'upload' | 'ai'

const MAX_UPLOAD_PX = 1600
const JPEG_QUALITY = 0.82

/** Downscale/re-encode a photo on-device before upload. A 10MB phone photo
 *  becomes ~300KB — the single biggest win for field connections. Falls back
 *  to the original file on any failure (and skips PDFs / small files). */
async function compressImage(file: File): Promise<File> {
  if (!file.type.startsWith('image/') || file.size < 400_000) return file
  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, MAX_UPLOAD_PX / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) return file
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()
    const blob = await new Promise<Blob | null>(resolve =>
      canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY)
    )
    if (!blob || blob.size >= file.size) return file
    return new File([blob], file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' })
  } catch {
    return file
  }
}

/** POST a file with real upload progress (fetch can't report upload %). */
function uploadWithProgress(
  url: string,
  form: FormData,
  headers: Record<string, string>,
  onProgress: (pct: number) => void,
): Promise<{ ok: boolean; status: number; json: any }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v))
    xhr.upload.onprogress = e => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      let json: any = null
      try { json = JSON.parse(xhr.responseText) } catch { /* non-JSON error body */ }
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, json })
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.send(form)
  })
}

const FIELDS = [
  { key: 'ph',              label: 'pH',               unit: '',          hint: '6.0–9.0',   default: 7.5  },
  { key: 'do',              label: 'Dissolved Oxygen',  unit: 'mg/L',      hint: '> 4.0',     default: 6.2  },
  { key: 'tss',             label: 'TSS',               unit: 'mg/L',      hint: '< 50',      default: 15.0 },
  { key: 'turbidity',       label: 'Turbidity',         unit: 'NTU',       hint: '< 75',      default: 10.0 },
  { key: 'cod',             label: 'COD',               unit: 'mg/L',      hint: '< 50',      default: 25.0 },
  { key: 'ammonia',         label: 'Ammonia',           unit: 'mg/L',      hint: '< 5.0',     default: 0.5  },
  { key: 'phosphate',       label: 'Phosphate',         unit: 'mg/L',      hint: '< 5.0',     default: 0.4  },
  { key: 'oil_grease',      label: 'Oil & Grease',      unit: 'mg/L',      hint: '< 10',      default: 1.0  },
  { key: 'ecoli',           label: 'E. coli',           unit: 'CFU/100mL', hint: '< 200',     default: 50   },
  { key: 'total_coliforms', label: 'Total Coliforms',   unit: 'CFU/100mL', hint: '< 1000',    default: 200  },
  { key: 'chla',            label: 'Chlorophyll-a',     unit: 'µg/L',      hint: 'bloom >10', default: 5.0  },
  { key: 'phycocyanin',     label: 'Phycocyanin',       unit: 'µg/L',      hint: 'cyano >50', default: 12.0 },
  { key: 'salinity',        label: 'Salinity',          unit: 'PSU',       hint: '40–60',     default: 45.0 },
  { key: 'water_temp',      label: 'Water Temp',        unit: '°C',        hint: '22–33',     default: 28.0 },
]

const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December']

type FieldValues = Record<string, number>

function defaultValues(): FieldValues {
  const today = new Date()
  const v: FieldValues = { year: today.getFullYear(), month: today.getMonth() + 1, day: today.getDate() }
  FIELDS.forEach(f => { v[f.key] = f.default })
  return v
}

export const UploadReport: React.FC<{ activeSite: string }> = ({ activeSite }) => {
  const { organizationId, getToken, email, role } = useAuth()
  const [fields, setFields] = useState<FieldValues>(defaultValues())
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [extracting, setExtracting] = useState(false)
  const [stage, setStage] = useState<ExtractStage>('idle')
  const [uploadPct, setUploadPct] = useState(0)
  const [aiSeconds, setAiSeconds] = useState(0)
  const [extractNotes, setExtractNotes] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    setFile(f)
    setExtractNotes(null)
    if (f.type.startsWith('image/')) {
      const url = URL.createObjectURL(f)
      setPreview(url)
    } else {
      setPreview(null)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  // Elapsed-seconds ticker for the AI stage.
  useEffect(() => {
    if (stage !== 'ai') return
    setAiSeconds(0)
    const t = setInterval(() => setAiSeconds(s => s + 1), 1000)
    return () => clearInterval(t)
  }, [stage])

  const handleExtract = async () => {
    if (!file) return
    setExtracting(true)
    setError(null)
    setExtractNotes(null)
    setUploadPct(0)
    try {
      setStage('compress')
      const compact = await compressImage(file)

      setStage('upload')
      const form = new FormData()
      form.append('file', compact)
      const headers: Record<string, string> = {}
      if (organizationId) headers['X-Organization-ID'] = organizationId
      const extractToken = await getToken()
      if (extractToken) headers['Authorization'] = `Bearer ${extractToken}`
      if (email) headers['X-User-Email'] = email
      const res = await uploadWithProgress('/api/extract', form, headers, pct => {
        setUploadPct(pct)
        if (pct >= 100) setStage('ai') // request sent — model is now reading
      })
      if (!res.ok) {
        throw new Error(res.json?.detail || 'Extraction failed')
      }
      const extracted = res.json
      const updated = { ...fields }
      FIELDS.forEach(f => {
        if (extracted[f.key] != null) updated[f.key] = extracted[f.key]
      })
      setFields(updated)
      if (extracted.notes) setExtractNotes(extracted.notes)
      setMessage('Values extracted — review and correct before saving.')
    } catch (e: any) {
      setError(e.message || 'AI extraction failed. Enter values manually.')
    } finally {
      setExtracting(false)
      setStage('idle')
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setFields(prev => ({ ...prev, [name]: parseFloat(value) || 0 }))
  }

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const [y, m, d] = e.target.value.split('-').map(Number)
    if (y && m && d) setFields(prev => ({ ...prev, year: y, month: m, day: d }))
  }

  const dateValue = `${fields.year}-${String(fields.month).padStart(2, '0')}-${String(fields.day ?? 1).padStart(2, '0')}`

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (role === 'auditor') { setError('Your Auditor account is read-only.'); return }
    setSaving(true); setMessage(null); setError(null)
    try {
      const headers: HeadersInit = { 'Content-Type': 'application/json' }
      if (organizationId) headers['X-Organization-ID'] = organizationId
      const logToken = await getToken()
      if (logToken) headers['Authorization'] = `Bearer ${logToken}`
      if (email) headers['X-User-Email'] = email
      const payload = { site: activeSite, year: Number(fields.year), month: Number(fields.month), day: Number(fields.day ?? 1), overwrite: true, ...Object.fromEntries(FIELDS.map(f => [f.key, fields[f.key]])) }
      const res = await fetch('/api/log', { method: 'POST', headers, body: JSON.stringify(payload) })
      const data = await res.json()
      if (data.saved) {
        setMessage(`Saved — ${activeSite}, ${MONTH_NAMES[Number(fields.month) - 1]} ${fields.day ?? 1}, ${fields.year}.`)
        setFile(null); setPreview(null)
      } else {
        setError(data.message || 'Failed to save reading.')
      }
    } catch {
      setError('Network error — please try again.')
    } finally {
      setSaving(false)
    }
  }

  const labelStyle: React.CSSProperties = { fontSize: '0.82rem', fontWeight: 600, color: '#1B3A5C', display: 'block', marginBottom: '4px' }
  const hintStyle: React.CSSProperties = { fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }

  return (
    <div style={{ maxWidth: 860 }}>
      <PageHeader title="Upload Lab Report" subtitle="Photo or PDF → AI auto-fill → review → save" icon="📷" />

      {/* ── Step 1: Upload ── */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <h3 className="section-heading" style={{ marginTop: 0 }}>Step 1 — Upload the lab report</h3>

        <div
          className={`upload-zone${dragOver ? ' drag-over' : ''}`}
          onClick={() => fileRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <input ref={fileRef} type="file" accept=".png,.jpg,.jpeg,.webp,.pdf" onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
          {file ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem' }}>
              {preview
                ? <img src={preview} alt="Lab report" style={{ maxHeight: 220, maxWidth: '100%', borderRadius: 8, border: '1px solid #e2e8f0' }} />
                : <FileText size={48} color="#1B3A5C" />
              }
              <span style={{ fontWeight: 600, color: '#1B3A5C' }}>{file.name}</span>
              <span style={{ fontSize: '0.82rem', color: '#64748b' }}>Click to change file</span>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem', color: '#64748b' }}>
              <Upload size={36} color="#2E5D8A" />
              <span style={{ fontWeight: 600, color: '#1B3A5C' }}>Drop a lab report here or click to browse</span>
              <span style={{ fontSize: '0.82rem' }}>PNG, JPG, WEBP, or PDF</span>
            </div>
          )}
        </div>

        {file && (
          <button onClick={handleExtract} disabled={extracting} style={{ marginTop: '1rem', gap: '0.5rem' }}>
            <Sparkles size={16} />
            {extracting ? 'Working…' : 'Extract Values with AI'}
          </button>
        )}

        {extracting && (
          <div style={{ marginTop: '1rem' }}>
            {/* Stage label */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', color: '#1B3A5C', fontWeight: 600, marginBottom: 6 }}>
              <span>
                {stage === 'compress' && 'Preparing photo…'}
                {stage === 'upload' && `Uploading… ${uploadPct}%`}
                {stage === 'ai' && `AI reading the report… ${aiSeconds}s`}
              </span>
              <span style={{ color: '#64748b', fontWeight: 400 }}>
                {stage === 'compress' && 'step 1 of 3'}
                {stage === 'upload' && 'step 2 of 3'}
                {stage === 'ai' && 'step 3 of 3 — usually 5–15s'}
              </span>
            </div>
            {/* Progress track */}
            <div style={{ height: 8, background: '#e2e8f0', borderRadius: 4, overflow: 'hidden', position: 'relative' }}>
              {stage === 'ai' ? (
                <div style={{
                  position: 'absolute', top: 0, bottom: 0, width: '35%',
                  background: 'linear-gradient(90deg, #2E5D8A, #4C9AD4)', borderRadius: 4,
                  animation: 'extract-slide 1.2s ease-in-out infinite',
                }} />
              ) : (
                <div style={{
                  height: '100%', borderRadius: 4, background: 'linear-gradient(90deg, #2E5D8A, #4C9AD4)',
                  width: stage === 'compress' ? '8%' : `${Math.max(8, uploadPct * 0.9)}%`,
                  transition: 'width 0.2s ease',
                }} />
              )}
            </div>
            <style>{'@keyframes extract-slide { 0% { left: -35%; } 100% { left: 100%; } }'}</style>
          </div>
        )}

        {extractNotes && (
          <div style={{ marginTop: '0.75rem', background: '#FFEB9C', color: '#856404', padding: '0.75rem 1rem', borderRadius: 6, fontSize: '0.875rem' }}>
            <strong>Reader notes:</strong> {extractNotes}
          </div>
        )}
      </div>

      {/* ── Step 2: Review & confirm ── */}
      <div className="glass-card">
        <h3 className="section-heading" style={{ marginTop: 0 }}>Step 2 — Review and confirm</h3>
        <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1.25rem' }}>
          Values are pre-filled from the report — correct anything the AI got wrong before saving.
        </p>

        {message && <div style={{ background: '#C6EFCE', color: '#006100', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: '1rem', fontWeight: 500 }}>{message}</div>}
        {error   && <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: '1rem', fontWeight: 500 }}>{error}</div>}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '1.25rem' }}>
            <label style={labelStyle}>Report Date</label>
            <input
              type="date"
              value={dateValue}
              onChange={handleDateChange}
              style={{ width: '100%', boxSizing: 'border-box' }}
            />
            <span style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '4px', display: 'block' }}>
              {MONTH_NAMES[fields.month - 1]} {fields.day ?? 1}, {fields.year}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            {FIELDS.map(f => (
              <div key={f.key}>
                <label style={labelStyle}>{f.label}{f.unit ? ` (${f.unit})` : ''}</label>
                <input type="number" name={f.key} step="0.01" value={fields[f.key]} onChange={handleChange} />
                <span style={hintStyle}>Limit: {f.hint}</span>
              </div>
            ))}
          </div>

          <button type="submit" disabled={saving}>
            <Save size={16} />
            {saving ? 'Saving…' : 'Save Compliance Record'}
          </button>
        </form>
      </div>
    </div>
  )
}
