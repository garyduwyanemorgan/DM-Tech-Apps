import React, { useState, useRef, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { Save, Upload, Sparkles, FileText, AlertTriangle, Clock, CheckCircle2, XCircle, HelpCircle, ScrollText } from 'lucide-react'
import { PageHeader } from './PageHeader'
import { StatusBadge } from './ui'
import { COLORS, tableHeaderStyle, tableCellStyle } from '../lib/ui'

// ── Lab sample (POST /api/extract response) ──────────────────────────────────
export type LabResultStatus = 'PASS' | 'FAIL' | 'NOT_ASSESSED'
export type ReviewerStatus = 'pending' | 'approved' | 'corrected' | 'rejected'
/** Whole-certificate verdict against the cited standard. */
export type OverallStatus = 'COMPLIANT' | 'NON_COMPLIANT' | 'INCOMPLETE'

export interface LabResult {
  parameter: string
  test_method?: string | null
  unit?: string | null
  /** Verbatim as printed on the certificate ("<1", "Not Detected", "7.42").
   *  Always displayed as-is — never substitute value_num. */
  value_raw?: string | null
  value_num?: number | null
  qualifier?: string | null
  loq?: string | null
  mou?: string | null
  specification?: string | null
  status?: LabResultStatus | null
  /** One plain sentence explaining the status. Absent on scanned reports. */
  status_reason?: string | null
}

export interface LabSample {
  laboratory?: string | null
  report_no?: string | null
  form_type?: string | null
  /** 'scanned' for the OCR/no-structure fallback path. */
  report_type?: string | null
  sampling_point?: string | null
  sample_location?: string | null
  sample_identification?: string | null
  source_of_sample?: string | null
  sample_description?: string | null
  sampled_at?: string | null
  received_at?: string | null
  reported_at?: string | null
  analysis_start?: string | null
  analysis_end?: string | null
  sampling_time?: string | null
  sampled_by?: string | null
  sampling_method?: string | null
  sampling_apparatus?: string | null
  sample_volume?: string | null
  temperature_c?: number | string | null
  analyst?: string | null
  reviewed_by?: string | null
  remarks?: string | null
  results?: LabResult[] | null
  source_filename?: string | null
  source_sha256?: string | null
  extraction_method?: string | null
  /** 0–1 model confidence; rendered as a percentage. */
  extraction_confidence?: number | null
  reviewer_status?: ReviewerStatus | null
  anomalies?: string[] | null

  // ── Governing standard (absent on scanned reports and on certificates that
  //    cite no compliance specification at all). ──
  standard_code?: string | null
  standard_title?: string | null
  standard_year?: string | null
  standard_authority?: string | null
  /** Full verbatim citation — the audit trail a reviewer may quote back. */
  standard_citation?: string | null
  additional_standards?: string[] | null
  test_procedure?: string | null
  medium_used?: string | null
  detection_limit?: string | null
  filtered_volume?: string | null
  overall_status?: OverallStatus | null
}

// ── Report types ─────────────────────────────────────────────────────────────
/** Scope decides which specification set a result may be judged against. It is a
 *  property of the ASSET a certificate is about, not of the analysis performed —
 *  a Legionella count means one thing in a stored tank and another in an open
 *  moat. Declared here because the upload flow displays it; owned by Assets. */
export type ReportScope = 'lagoon' | 'facilities'

export interface ReportTypeOption {
  key: string
  label: string
  builtin?: boolean
}

/** Returned by /api/extract when the selected type and the certificate disagree.
 *  Never auto-resolved — the user decides. */
export interface TypeConflict {
  selected: string
  selected_label: string
  detected: string
  detected_label: string
  message: string
}

/** One editable row in Step 2. Built from the extraction, not from a fixed list —
 *  a certificate with 23 parameters gets 23 rows, one with 1 gets 1. */
interface FormRow {
  key: string
  label: string
  unit: string
  /** Verbatim printed value, kept alongside the editable number so a reviewer can
   *  always see what the certificate actually said. */
  printed?: string
  hint?: string
  value: string
}

const ADD_NEW = '__add_new__'

/** A sampled asset — the thing a certificate is about, and the thing that
 *  carries the specification scope. */
export interface AssetTypeOption {
  key: string
  label: string
  asset_class?: string | null
  scope?: ReportScope | null
  builtin?: boolean
}

export interface SampledAsset {
  id: string
  name: string
  asset_type?: string | null
  scope?: ReportScope | null
}

/** Em-dash placeholder so empty cells read as "not on the certificate"
 *  rather than as a broken table. */
const DASH = '—'
const show = (v: unknown): string => {
  if (v === null || v === undefined) return DASH
  const s = String(v).trim()
  return s === '' ? DASH : s
}

// NOT_ASSESSED is deliberately amber, not grey: "nobody checked this" is an
// open item on a regulatory submission, not a neutral non-event.
const STATUS_TONE: Record<LabResultStatus, 'green' | 'red' | 'amber'> = {
  PASS: 'green', FAIL: 'red', NOT_ASSESSED: 'amber',
}
const STATUS_LABEL: Record<LabResultStatus, string> = {
  PASS: 'Pass', FAIL: 'Fail', NOT_ASSESSED: 'Not assessed',
}

// ── Whole-certificate verdict ─────────────────────────────────────────────────
// INCOMPLETE must never read as a pass: amber/warning treatment, its own icon,
// and wording that states outright that the assessment is unfinished.
const OVERALL_COPY: Record<OverallStatus, {
  tone: 'green' | 'red' | 'amber'
  label: string
  note: string
  bg: string; fg: string; border: string
  Icon: React.ComponentType<{ size?: number; style?: React.CSSProperties; 'aria-hidden'?: boolean | 'true' | 'false' }>
}> = {
  COMPLIANT: {
    tone: 'green', label: 'Compliant', note: 'Met the cited specification',
    bg: COLORS.greenBg, fg: COLORS.greenFg, border: COLORS.greenBorder, Icon: CheckCircle2,
  },
  NON_COMPLIANT: {
    tone: 'red', label: 'Not compliant', note: 'One or more parameters exceeded the specification',
    bg: COLORS.redBg, fg: COLORS.redFg, border: COLORS.redBorder, Icon: XCircle,
  },
  INCOMPLETE: {
    tone: 'amber', label: 'Incomplete — not a pass', note: 'Not fully assessed — see unassessed parameters below',
    bg: COLORS.amberBg, fg: COLORS.amberFg, border: COLORS.amberBorder, Icon: HelpCircle,
  },
}

/** Top-of-panel verdict banner — the first thing a reviewer sees. */
const OverallStatusBanner: React.FC<{ status: OverallStatus }> = ({ status }) => {
  const c = OVERALL_COPY[status]
  const { Icon } = c
  return (
    <div
      role={status === 'COMPLIANT' ? undefined : 'alert'}
      style={{
        display: 'flex', gap: '0.75rem', alignItems: 'center',
        background: c.bg, color: c.fg, border: `2px solid ${c.border}`,
        borderRadius: 8, padding: '0.9rem 1.1rem', margin: '0.9rem 0 1.1rem',
      }}
    >
      <Icon size={22} style={{ flexShrink: 0 }} aria-hidden="true" />
      <div>
        <div style={{ fontWeight: 800, fontSize: '1rem', letterSpacing: '0.01em' }}>{c.label}</div>
        <div style={{ fontSize: '0.85rem', marginTop: 2 }}>{c.note}</div>
      </div>
    </div>
  )
}

/** The governing standard this certificate was judged against. */
const AssessedAgainst: React.FC<{ sample: LabSample }> = ({ sample }) => {
  const [showCitation, setShowCitation] = useState(false)
  const extras = (sample.additional_standards ?? []).filter(s => (s ?? '').trim() !== '')

  const detail: { label: string; value: string }[] = [
    { label: 'Test procedure', value: show(sample.test_procedure) },
    { label: 'Medium used', value: show(sample.medium_used) },
    { label: 'Detection limit', value: show(sample.detection_limit) },
    { label: 'Filtered volume', value: show(sample.filtered_volume) },
  ].filter(d => d.value !== DASH)

  const heading = (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: COLORS.slate, marginBottom: '0.55rem' }}>
      <ScrollText size={14} aria-hidden="true" />
      Assessed against
    </div>
  )

  // No cited standard (e.g. the chemistry certificate) — say so outright rather
  // than render an empty panel a reviewer might read as "checked, all fine".
  if (!(sample.standard_code ?? '').trim() && !(sample.standard_title ?? '').trim()) {
    return (
      <div style={{ border: `1px dashed ${COLORS.border}`, borderRadius: 8, padding: '0.9rem 1.1rem', marginBottom: '1.25rem', background: COLORS.surface }}>
        {heading}
        <p style={{ margin: 0, fontSize: '0.875rem', color: '#1B3A5C', fontWeight: 600 }}>
          This certificate cites no compliance standard.
        </p>
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.82rem', color: COLORS.slate }}>
          Results below are reported values only — they have not been judged against any specification.
        </p>
        {extras.length > 0 && (
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.82rem', color: COLORS.slate }}>
            Other standards referenced: {extras.join(', ')}
          </p>
        )}
      </div>
    )
  }

  return (
    <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '0.9rem 1.1rem', marginBottom: '1.25rem', background: COLORS.surface }}>
      {heading}

      <div style={{ fontSize: '1rem', fontWeight: 800, color: '#1B3A5C', wordBreak: 'break-word' }}>
        {show(sample.standard_code)}
        {(sample.standard_year ?? '').trim() && (
          <span style={{ fontWeight: 600, color: COLORS.slate }}> ({sample.standard_year})</span>
        )}
      </div>
      {(sample.standard_title ?? '').trim() && (
        <div style={{ fontSize: '0.9rem', color: '#1B3A5C', marginTop: 2 }}>{sample.standard_title}</div>
      )}
      {(sample.standard_authority ?? '').trim() && (
        <div style={{ fontSize: '0.82rem', color: COLORS.slate, marginTop: 4 }}>{sample.standard_authority}</div>
      )}

      {extras.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.4rem', marginTop: '0.6rem' }}>
          <span style={{ fontSize: '0.78rem', color: COLORS.slate }}>Also referenced:</span>
          {extras.map(s => <StatusBadge key={s} tone="blue" variant="count">{s}</StatusBadge>)}
        </div>
      )}

      {detail.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.6rem 1.25rem', marginTop: '0.85rem' }}>
          {detail.map(d => (
            <div key={d.label}>
              <div style={{ fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: COLORS.slate }}>{d.label}</div>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#1B3A5C', wordBreak: 'break-word' }}>{d.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Full citation kept verbatim but collapsed — it is long, and it is the
          audit trail rather than something read on every visit. */}
      {(sample.standard_citation ?? '').trim() && (
        <div style={{ marginTop: '0.85rem' }}>
          <button
            type="button"
            onClick={() => setShowCitation(v => !v)}
            aria-expanded={showCitation}
            style={{
              background: 'none', border: 'none', padding: 0, cursor: 'pointer',
              font: 'inherit', fontSize: '0.8rem', fontWeight: 700, color: '#2E5D8A', textDecoration: 'underline',
            }}
          >
            {showCitation ? 'Hide full citation' : 'Show full citation'}
          </button>
          {showCitation && (
            <p style={{
              margin: '0.5rem 0 0', fontSize: '0.8rem', lineHeight: 1.55, color: '#374151',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              borderLeft: `3px solid ${COLORS.border}`, paddingLeft: '0.75rem',
            }}>
              {sample.standard_citation}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

const REVIEW_COPY: Record<ReviewerStatus, { tone: 'amber' | 'green' | 'blue' | 'red'; label: string; note: string }> = {
  pending: { tone: 'amber', label: 'Pending review', note: 'Nothing has been saved yet. A person must check these values against the certificate and approve them before they enter the record.' },
  approved: { tone: 'green', label: 'Approved', note: 'These values have been checked against the certificate and approved.' },
  corrected: { tone: 'blue', label: 'Corrected', note: 'A reviewer has amended these values against the certificate.' },
  rejected: { tone: 'red', label: 'Rejected', note: 'A reviewer rejected this extraction — do not use these values.' },
}

const confidencePct = (c?: number | null): string =>
  c === null || c === undefined || Number.isNaN(c) ? DASH : `${Math.round((c <= 1 ? c * 100 : c))}%`

/** Provenance + results + anomalies for one extracted certificate. */
const ExtractedSample: React.FC<{ sample: LabSample }> = ({ sample }) => {
  const results = sample.results ?? []
  const anomalies = sample.anomalies ?? []
  const review = REVIEW_COPY[sample.reviewer_status ?? 'pending'] ?? REVIEW_COPY.pending
  const scanned = (sample.report_type ?? '').toLowerCase() === 'scanned'
  const overall = sample.overall_status && OVERALL_COPY[sample.overall_status] ? sample.overall_status : null
  const notAssessed = results.filter(r => (r.status ?? 'NOT_ASSESSED') === 'NOT_ASSESSED').length

  const meta: { label: string; value: string }[] = [
    { label: 'Laboratory', value: show(sample.laboratory) },
    { label: 'Report No.', value: show(sample.report_no) },
    { label: 'Report Type', value: show(sample.report_type) },
    { label: 'Sampling Point', value: show(sample.sampling_point || sample.sample_location) },
    { label: 'Sampled', value: show(sample.sampled_at) },
    { label: 'Reported', value: show(sample.reported_at) },
    { label: 'Analyst', value: show(sample.analyst) },
    { label: 'Reviewed By', value: show(sample.reviewed_by) },
    { label: 'Extracted By', value: show(sample.extraction_method) },
    { label: 'Extraction Confidence', value: confidencePct(sample.extraction_confidence) },
  ]

  return (
    <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}>
        <h3 className="section-heading" style={{ marginTop: 0, marginBottom: 0 }}>Extracted certificate</h3>
        <StatusBadge tone={review.tone}>{review.label}</StatusBadge>
      </div>

      {/* Verdict against the cited standard — first thing a reviewer sees. */}
      {overall && <OverallStatusBanner status={overall} />}

      {/* Not-yet-saved banner — the single most important message on this panel. */}
      <div style={{
        display: 'flex', gap: '0.6rem', alignItems: 'flex-start',
        background: COLORS.amberBg, color: COLORS.amberFg, border: `1px solid ${COLORS.amberBorder}`,
        padding: '0.75rem 1rem', borderRadius: 6, margin: '0.9rem 0 1.1rem', fontSize: '0.875rem',
      }}>
        <Clock size={16} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
        <span><strong>{review.label}.</strong> {review.note}</span>
      </div>

      {/* Data-quality findings — must be impossible to miss. */}
      {anomalies.length > 0 && (
        <div
          role="alert"
          style={{
            background: COLORS.redBg, color: COLORS.redFg, border: `2px solid ${COLORS.redBorder}`,
            borderRadius: 8, padding: '0.9rem 1.1rem', marginBottom: '1.1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 800, fontSize: '0.9rem', marginBottom: '0.5rem' }}>
            <AlertTriangle size={18} aria-hidden="true" />
            {anomalies.length} data-quality {anomalies.length === 1 ? 'issue' : 'issues'} found — check before approving
          </div>
          <ul style={{ margin: 0, paddingLeft: '1.5rem', fontSize: '0.85rem', lineHeight: 1.55 }}>
            {anomalies.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      )}

      {scanned && (
        <p style={{ fontSize: '0.82rem', color: COLORS.slate, marginBottom: '1rem' }}>
          This report was read as a scan, so header details and per-parameter methods or specifications may be missing.
          Blank cells ({DASH}) mean the value was not present on the certificate.
        </p>
      )}

      {/* Governing standard */}
      <AssessedAgainst sample={sample} />

      {/* Provenance */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '0.9rem 1.25rem', marginBottom: '1.5rem' }}>
        {meta.map(m => (
          <div key={m.label}>
            <div style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: COLORS.slate }}>{m.label}</div>
            <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#1B3A5C', wordBreak: 'break-word' }}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Results */}
      {results.length === 0 ? (
        <p style={{ fontSize: '0.875rem', color: COLORS.slate }}>No individual test results were found in this report.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          {/* Unassessed parameters are an open item, not a quiet default —
              state the count so it cannot be skimmed past. */}
          {notAssessed > 0 && (
            <div
              role="alert"
              style={{
                display: 'flex', gap: '0.6rem', alignItems: 'flex-start',
                background: COLORS.amberBg, color: COLORS.amberFg, border: `1px solid ${COLORS.amberBorder}`,
                borderRadius: 6, padding: '0.7rem 1rem', marginBottom: '0.9rem', fontSize: '0.85rem',
              }}
            >
              <HelpCircle size={16} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
              <span>
                <strong>{notAssessed} of {results.length} parameters were not assessed.</strong>{' '}
                Nobody has checked {notAssessed === 1 ? 'it' : 'them'} against a specification — treat{' '}
                {notAssessed === 1 ? 'it' : 'them'} as open before submitting to the regulator.
              </span>
            </div>
          )}
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 640 }}>
            <caption style={{ captionSide: 'top', textAlign: 'left', fontSize: '0.8rem', color: COLORS.slate, paddingBottom: '0.5rem' }}>
              {results.length} test {results.length === 1 ? 'result' : 'results'} — shown exactly as printed on the certificate.
            </caption>
            <thead>
              <tr>
                <th scope="col" style={tableHeaderStyle}>Parameter</th>
                <th scope="col" style={tableHeaderStyle}>Result</th>
                <th scope="col" style={tableHeaderStyle}>Unit</th>
                <th scope="col" style={tableHeaderStyle}>Method</th>
                <th scope="col" style={tableHeaderStyle}>Specification</th>
                <th scope="col" style={tableHeaderStyle}>Status</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => {
                const status = (r.status ?? 'NOT_ASSESSED') as LabResultStatus
                const tone = STATUS_TONE[status] ?? 'slate'
                return (
                  <tr key={`${r.parameter}-${i}`}>
                    <th scope="row" style={{ ...tableCellStyle, textAlign: 'left', fontWeight: 600, color: '#1B3A5C' }}>
                      {show(r.parameter)}
                      {(r.status_reason ?? '').trim() && (
                        <div style={{
                          fontWeight: 400, fontSize: '0.78rem', lineHeight: 1.45, marginTop: 3,
                          color: status === 'NOT_ASSESSED' ? COLORS.amberFg : COLORS.slate,
                        }}>
                          {r.status_reason}
                        </div>
                      )}
                    </th>
                    {/* value_raw verbatim: '<1' and 'Not Detected' are regulatorily meaningful. */}
                    <td style={{ ...tableCellStyle, fontWeight: 600, whiteSpace: 'nowrap' }}>{show(r.value_raw)}</td>
                    <td style={tableCellStyle}>{show(r.unit)}</td>
                    <td style={tableCellStyle}>{show(r.test_method)}</td>
                    <td style={tableCellStyle}>{show(r.specification)}</td>
                    <td style={tableCellStyle}>
                      <StatusBadge tone={tone} variant="count">{STATUS_LABEL[status] ?? STATUS_LABEL.NOT_ASSESSED}</StatusBadge>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Modals ────────────────────────────────────────────────────────────────────
// Deliberately in-app rather than window.confirm(): a native dialog blocks the
// page, cannot show the scope consequence, and only offers OK/Cancel where this
// needs a three-way choice.

const Modal: React.FC<{ title: string; onClose: () => void; children: React.ReactNode }> = ({ title, onClose, children }) => (
  <div
    role="dialog" aria-modal="true" aria-label={title}
    onClick={onClose}
    style={{
      position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem',
    }}
  >
    <div
      onClick={e => e.stopPropagation()}
      style={{
        background: '#fff', borderRadius: 10, padding: '1.5rem', maxWidth: 560, width: '100%',
        maxHeight: '85vh', overflowY: 'auto', boxShadow: '0 20px 50px rgba(15,23,42,0.28)',
      }}
    >
      <h3 className="section-heading" style={{ marginTop: 0 }}>{title}</h3>
      {children}
    </div>
  </div>
)

/** Add an organisation-defined report type: a name and a scope, nothing else.
 *  Fields come from whatever the extraction finds, so the certificate stays the
 *  source of truth. */
const AddReportTypeModal: React.FC<{
  onCancel: () => void
  onCreate: (name: string) => Promise<void>
}> = ({ onCancel, onCreate }) => {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async () => {
    if (!name.trim()) { setErr('Give the report type a name.'); return }
    setBusy(true); setErr(null)
    try { await onCreate(name.trim()) }
    catch (e: any) { setErr(e?.message || 'Could not create the report type.'); setBusy(false) }
  }

  return (
    <Modal title="Add a new report type" onClose={onCancel}>
      <label htmlFor="new-report-type" style={{ fontSize: '0.82rem', fontWeight: 600, color: '#1B3A5C', display: 'block', marginBottom: 4 }}>
        Name
      </label>
      <input
        id="new-report-type" autoFocus value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') submit() }}
        placeholder="e.g. Cooling Tower Water"
        style={{ width: '100%', boxSizing: 'border-box', marginBottom: '1rem' }}
      />

      <p style={{ fontSize: '0.78rem', color: COLORS.slate, marginTop: 0, marginBottom: '1rem', lineHeight: 1.5 }}>
        You do not list the parameters — they are read from each certificate you
        upload, so the document stays the source of truth. Which limits apply is
        decided by the asset a certificate is about, not by the type of analysis.
      </p>

      {err && <div role="alert" style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.6rem 0.9rem', borderRadius: 6, marginBottom: '0.9rem', fontSize: '0.85rem' }}>{err}</div>}

      <div style={{ display: 'flex', gap: '0.6rem', justifyContent: 'flex-end' }}>
        <button type="button" onClick={onCancel} disabled={busy} style={{ background: '#e2e8f0', color: '#1B3A5C' }}>Cancel</button>
        <button type="button" onClick={submit} disabled={busy}>{busy ? 'Adding…' : 'Add report type'}</button>
      </div>
    </Modal>
  )
}

/** The certificate disagrees with the chosen type. Offer the choice; resolve nothing. */
const TypeConflictModal: React.FC<{
  conflict: TypeConflict
  onKeepDetected: () => void
  onKeepSelected: () => void
  onCancel: () => void
}> = ({ conflict, onKeepDetected, onKeepSelected, onCancel }) => (
  <Modal title="This certificate is a different report type" onClose={onCancel}>
    <p style={{ fontSize: '0.9rem', color: '#1B3A5C', lineHeight: 1.55, marginTop: 0 }}>{conflict.message}</p>

    <div role="alert" style={{
      background: COLORS.amberBg, color: COLORS.amberFg, border: `1px solid ${COLORS.amberBorder}`,
      borderRadius: 6, padding: '0.75rem 1rem', margin: '0.9rem 0', fontSize: '0.85rem', lineHeight: 1.55,
    }}>
      Filing a certificate under the wrong analysis misdescribes what the laboratory
      actually did. It does not by itself change which limits apply — that follows
      from the asset the sample came from — but the record would be wrong.
    </div>

    <p style={{ fontSize: '0.85rem', color: COLORS.slate, lineHeight: 1.55 }}>
      The type read from the document is normally the reliable one — it comes from the
      laboratory's own form code. Keep your selection only if you know the certificate is
      mislabelled.
    </p>

    <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', justifyContent: 'flex-end', marginTop: '1.1rem' }}>
      <button type="button" onClick={onCancel} style={{ background: '#e2e8f0', color: '#1B3A5C' }}>Cancel upload</button>
      <button type="button" onClick={onKeepSelected} style={{ background: '#e2e8f0', color: '#1B3A5C' }}>
        Keep “{conflict.selected_label}”
      </button>
      <button type="button" onClick={onKeepDetected}>
        Use “{conflict.detected_label}” from the document
      </button>
    </div>
  </Modal>
)

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

const FIELD_KEYS = new Set(FIELDS.map(f => f.key))

/**
 * Prefill the Step 2 compliance form from an extracted sample.
 *
 * Only applies to scanned reports: the vision extractor emits exactly the 15
 * lagoon compliance parameters, keyed by the same names as FIELDS. Wimpey
 * certificates are microbiological/Legionella/full-chemistry and do NOT map onto
 * this form — prefilling from them would put the wrong numbers in front of a
 * reviewer, which is worse than leaving the defaults visible.
 *
 * Returns how many fields were populated, so the caller can say so.
 */
function prefillFromSample(
  sample: LabSample | null,
  setFields: React.Dispatch<React.SetStateAction<FieldValues>>,
): number {
  if (!sample || sample.report_type !== 'scanned') return 0

  const patch: FieldValues = {}
  for (const r of sample.results ?? []) {
    if (FIELD_KEYS.has(r.parameter) && typeof r.value_num === 'number' && isFinite(r.value_num)) {
      patch[r.parameter] = r.value_num
    }
  }
  // Date the reading from the certificate rather than today, when it says.
  if (sample.sampled_at) {
    const [y, m, d] = sample.sampled_at.split('-').map(Number)
    if (y && m && d) Object.assign(patch, { year: y, month: m, day: d })
  }

  const count = Object.keys(patch).filter(k => FIELD_KEYS.has(k)).length
  if (count || sample.sampled_at) setFields(prev => ({ ...prev, ...patch }))
  return count
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
  const [sample, setSample] = useState<LabSample | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [reportTypes, setReportTypes] = useState<ReportTypeOption[]>([])
  const [selectedType, setSelectedType] = useState<string>('lagoon')
  const [showAddType, setShowAddType] = useState(false)
  const [conflict, setConflict] = useState<TypeConflict | null>(null)
  /** Step 2 rows. Empty until an extraction (or the lagoon manual fallback)
   *  populates it — the form has exactly as many fields as there are results. */
  const [rows, setRows] = useState<FormRow[]>([])
  /** Sampled assets only — a certificate is never about a dosing pump. */
  const [assets, setAssets] = useState<SampledAsset[]>([])
  const [assetId, setAssetId] = useState<string>('')
  /** The register: built-in types plus this organisation's own, so an asset
   *  created under a custom type still shows a human label here. */
  const [assetTypes, setAssetTypes] = useState<AssetTypeOption[]>([])

  const authHeaders = React.useCallback(async (json = true): Promise<HeadersInit> => {
    const h: HeadersInit = {}
    if (json) h['Content-Type'] = 'application/json'
    if (organizationId) h['X-Organization-ID'] = organizationId
    const t = await getToken()
    if (t) h['Authorization'] = `Bearer ${t}`
    if (email) h['X-User-Email'] = email
    return h
  }, [organizationId, getToken, email])

  // Legacy routing: the lagoon product predates assets entirely and writes the
  // fixed monthly `readings` table, so it is identified by its own report type.
  // Everything else is a certificate about an asset and goes to lab_samples.
  const isLagoon = selectedType === 'lagoon'
  const selectedAsset = assets.find(a => a.id === assetId) ?? null
  /** Human label for an asset type, from the register (built-in + org-defined). */
  const typeLabel = (key?: string | null): string =>
    assetTypes.find(t => t.key === key)?.label ?? (key ?? '').replace(/_/g, ' ')

  // Load the dropdown. Built-ins always exist, so a failure here degrades to the
  // built-in list rather than blocking the upload.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const h = await authHeaders(false)
        const [tRes, aRes, atRes] = await Promise.all([
          fetch('/api/report-types', { headers: h }),
          fetch('/api/assets?asset_class=sampled', { headers: h }),
          fetch('/api/asset-types?asset_class=sampled', { headers: h }),
        ])
        if (tRes.ok) {
          const data = await tRes.json()
          if (!cancelled && Array.isArray(data?.types)) setReportTypes(data.types)
        }
        if (aRes.ok) {
          const data = await aRes.json()
          if (!cancelled && Array.isArray(data?.assets)) setAssets(data.assets)
        }
        if (atRes.ok) {
          const data = await atRes.json()
          if (!cancelled && Array.isArray(data?.types)) setAssetTypes(data.types)
        }
      } catch { /* built-ins are unavailable only if the API is down entirely */ }
    })()
    return () => { cancelled = true }
  }, [authHeaders])

  /** Rebuild Step 2 from an extraction: one row per reported parameter. */
  const rowsFromSample = (s: LabSample): FormRow[] =>
    (s.results ?? []).map((r, i) => ({
      key: `${r.parameter}-${i}`,
      label: r.parameter,
      unit: (r.unit ?? '').trim(),
      printed: (r.value_raw ?? '').trim(),
      hint: (r.specification ?? '').trim() ? `Specification: ${r.specification}` : undefined,
      value: r.value_num === null || r.value_num === undefined ? '' : String(r.value_num),
    }))

  /** Manual-entry fallback for the lagoon scope, which has a known parameter set
   *  even before anything is extracted. Still rendered through the same dynamic
   *  form — there is no static panel any more. */
  const lagoonRows = (): FormRow[] =>
    FIELDS.map(f => ({
      key: f.key, label: f.label, unit: f.unit,
      hint: `Limit: ${f.hint}`, value: String(f.default),
    }))

  // Seed the lagoon rows when that type is chosen and nothing is extracted yet.
  useEffect(() => {
    if (!sample && isLagoon && rows.length === 0) setRows(lagoonRows())
    if (!sample && !isLagoon) setRows([])
  }, [selectedType, sample, isLagoon])  // eslint-disable-line react-hooks/exhaustive-deps

  const setRowValue = (key: string, value: string) =>
    setRows(prev => prev.map(r => (r.key === key ? { ...r, value } : r)))
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    setFile(f)
    setExtractNotes(null)
    setSample(null)
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
    setSample(null)
    setUploadPct(0)
    try {
      setStage('compress')
      const compact = await compressImage(file)

      setStage('upload')
      const form = new FormData()
      form.append('file', compact)
      // The chosen type is sent so the server can report a disagreement with the
      // certificate's own form code. It never overrides what the document says.
      form.append('report_type', selectedType)
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
      const extracted = res.json as LabSample & { type_conflict?: TypeConflict | null }
      setSample(extracted)
      if (extracted?.remarks) setExtractNotes(extracted.remarks)
      const found = extracted?.results?.length ?? 0

      // Step 2 is now built from the document: one field per reported parameter.
      setRows(rowsFromSample(extracted))
      const prefilled = prefillFromSample(extracted, setFields)

      if (extracted.type_conflict) setConflict(extracted.type_conflict)

      setMessage(
        `Read ${found} test ${found === 1 ? 'result' : 'results'}` +
        (prefilled ? `, ${prefilled} prefilled below` : '') +
        ' — nothing is saved until you review and confirm below.'
      )
    } catch (e: any) {
      setError(e.message || 'AI extraction failed. Enter values manually.')
    } finally {
      setExtracting(false)
      setStage('idle')
    }
  }

  // Step 2's parameter inputs are driven by `rows` (setRowValue) now that the
  // form is built from the certificate; `fields` still carries the report date
  // and the lagoon defaults that seed those rows.
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
      const headers = await authHeaders()

      // Lagoon readings keep the fixed monthly path: `readings` has fourteen
      // columns and one row per site per month, and the alert engine, dashboards
      // and monthly reporting all read from it. Everything else is a certificate
      // with an arbitrary parameter list and goes to lab_samples/lab_results.
      if (isLagoon) {
        const byKey = Object.fromEntries(rows.map(r => [r.key, Number(r.value) || 0]))
        const payload = {
          site: activeSite, year: Number(fields.year), month: Number(fields.month),
          day: Number(fields.day ?? 1), overwrite: true,
          ...Object.fromEntries(FIELDS.map(f => [f.key, byKey[f.key] ?? fields[f.key]])),
        }
        const res = await fetch('/api/log', { method: 'POST', headers, body: JSON.stringify(payload) })
        const data = await res.json()
        if (data.saved) {
          setMessage(`Saved — ${activeSite}, ${MONTH_NAMES[Number(fields.month) - 1]} ${fields.day ?? 1}, ${fields.year}.`)
          setFile(null); setPreview(null)
        } else {
          setError(data.message || 'Failed to save reading.')
        }
        return
      }

      if (!sample) { setError('Upload and extract a certificate before saving.'); return }

      // Carry the reviewer's corrections back onto the parsed rows, keeping every
      // field the certificate supplied (method, unit, specification, verdict).
      const edited = (sample.results ?? []).map((r, i) => {
        const row = rows.find(x => x.key === `${r.parameter}-${i}`)
        const n = row && row.value.trim() !== '' ? Number(row.value) : null
        return { ...r, value_num: n === null || Number.isNaN(n) ? r.value_num : n }
      })

      const res = await fetch('/api/lab-samples', {
        method: 'POST', headers,
        body: JSON.stringify({ sample, results: edited, site: activeSite,
                               report_type: selectedType, asset_id: assetId || null }),
      })
      const data = await res.json()
      if (res.ok) {
        setMessage(`Saved certificate ${data.report_no} — ${data.parameters} parameters recorded.`)
        setFile(null); setPreview(null)
      } else {
        setError(data.detail || 'Failed to save the certificate.')
      }
    } catch {
      setError('Network error — please try again.')
    } finally {
      setSaving(false)
    }
  }

  const createReportType = async (name: string) => {
    const res = await fetch('/api/report-types', {
      method: 'POST', headers: await authHeaders(),
      body: JSON.stringify({ name }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Could not create the report type.')
    setReportTypes(prev => [...prev, data])
    setSelectedType(data.key)
    setShowAddType(false)
    setMessage(`Report type “${data.label}” added.`)
  }

  const labelStyle: React.CSSProperties = { fontSize: '0.82rem', fontWeight: 600, color: '#1B3A5C', display: 'block', marginBottom: '4px' }
  const hintStyle: React.CSSProperties = { fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }

  return (
    <div style={{ maxWidth: 860 }}>
      <PageHeader title="Upload Lab Report" subtitle="Photo or PDF → AI auto-fill → review → save" icon="📷" />

      {/* ── Step 1: Upload ── */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <h3 className="section-heading" style={{ marginTop: 0 }}>Step 1 — Upload the lab report</h3>

        {/* Chosen first: the asset is the subject of the certificate, and it is
            what carries the specification scope. Always visible — hiding it for
            the default report type would hide the primary selection on load. */}
        <div style={{ marginBottom: '1.1rem' }}>
          <label htmlFor="sampled-asset" style={labelStyle}>Asset this certificate is about</label>
          <select
            id="sampled-asset" value={assetId}
            onChange={e => setAssetId(e.target.value)}
            style={{ width: '100%', boxSizing: 'border-box' }}
          >
            <option value="">— not selected —</option>
            {assets.map(a => (
              <option key={a.id} value={a.id}>
                {a.name}{a.asset_type ? ` (${typeLabel(a.asset_type)})` : ''}
              </option>
            ))}
          </select>
          {isLagoon ? (
            <span style={hintStyle}>
              Not used for a monthly lagoon reading — that path predates assets and is
              saved against the site.
            </span>
          ) : assets.length === 0 ? (
            <span style={{ ...hintStyle, color: COLORS.amberFg }}>
              No sampled assets exist yet. Add one under Assets &amp; Maintenance, using a
              type from the Asset Register in Settings, or this certificate cannot be
              judged against any specification.
            </span>
          ) : selectedAsset ? (
            <span style={hintStyle}>
              {selectedAsset.scope
                ? `Scope: ${selectedAsset.scope === 'lagoon'
                    ? 'lagoon — man-made / closed lagoon limits'
                    : 'facilities management — DM technical guidelines'}`
                : 'This asset has no scope set, so results stay unassessed until it does.'}
            </span>
          ) : (
            <span style={{ ...hintStyle, color: COLORS.amberFg }}>
              Without an asset the scope is unknown, so nothing can be judged against a
              specification — results are recorded but stay unassessed.
            </span>
          )}
        </div>

        <div style={{ marginBottom: '1.1rem' }}>
          <label htmlFor="report-type" style={labelStyle}>Report type</label>
          <select
            id="report-type"
            value={selectedType}
            onChange={e => {
              const v = e.target.value
              if (v === ADD_NEW) { setShowAddType(true); return }   // keep the current selection
              setSelectedType(v)
            }}
            style={{ width: '100%', boxSizing: 'border-box' }}
          >
            {reportTypes.map(t => (
              <option key={t.key} value={t.key}>{t.label}</option>
            ))}
            <option value={ADD_NEW}>+ Add new report type…</option>
          </select>
          <span style={hintStyle}>
            {isLagoon
              ? 'Monthly lagoon reading — saved to the compliance record.'
              : 'Which limits apply is decided by the asset this certificate is about.'}
          </span>
        </div>

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

      {/* ── Extracted certificate (provenance + results + anomalies) ── */}
      {sample && <ExtractedSample sample={sample} />}

      {/* ── Step 2: Review & confirm ── */}
      <div className="glass-card">
        <h3 className="section-heading" style={{ marginTop: 0 }}>Step 2 — Review and confirm</h3>
        <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1.25rem' }}>
          {sample
            ? 'Confirm the compliance values against the extracted certificate above. Nothing is stored until you save.'
            : 'Enter or correct the compliance values for this reading before saving.'}
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

          {/* One field per reported parameter — the form is built from the
              certificate, so a 23-parameter report gets 23 fields and a
              single-parameter Legionella report gets one. */}
          {rows.length === 0 ? (
            <p style={{ fontSize: '0.875rem', color: COLORS.slate, marginBottom: '1.5rem' }}>
              {isLagoon
                ? 'No parameters yet.'
                : 'Upload and extract a certificate above — the fields here are built from what it reports.'}
            </p>
          ) : (
            <>
              <p style={{ fontSize: '0.8rem', color: COLORS.slate, marginBottom: '0.75rem' }}>
                {rows.length} {rows.length === 1 ? 'parameter' : 'parameters'}
                {sample ? ' read from the certificate' : ''}.
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                {rows.map(r => (
                  <div key={r.key}>
                    <label htmlFor={`row-${r.key}`} style={labelStyle}>
                      {r.label}{r.unit ? ` (${r.unit})` : ''}
                    </label>
                    <input
                      id={`row-${r.key}`} type="number" step="any"
                      value={r.value}
                      onChange={e => setRowValue(r.key, e.target.value)}
                      style={{ width: '100%', boxSizing: 'border-box' }}
                    />
                    {/* The printed value stays visible: '<1' and 'Not Detected'
                        cannot be represented in a number input, and the reviewer
                        needs to see what the certificate actually said. */}
                    {r.printed && (
                      <span style={hintStyle}>Printed: <strong>{r.printed}</strong></span>
                    )}
                    {r.hint && <span style={hintStyle}>{r.hint}</span>}
                  </div>
                ))}
              </div>
            </>
          )}

          <button type="submit" disabled={saving || rows.length === 0}>
            <Save size={16} />
            {saving ? 'Saving…' : isLagoon ? 'Save Compliance Record' : 'Save Certificate'}
          </button>
        </form>
      </div>

      {showAddType && (
        <AddReportTypeModal onCancel={() => setShowAddType(false)} onCreate={createReportType} />
      )}

      {conflict && (
        <TypeConflictModal
          conflict={conflict}
          onKeepDetected={() => { setSelectedType(conflict.detected); setConflict(null) }}
          onKeepSelected={() => setConflict(null)}
          onCancel={() => {
            // Discard the extraction entirely — nothing filed under a type the
            // reviewer is not willing to stand behind.
            setConflict(null); setSample(null); setRows([]); setFile(null); setPreview(null)
            setMessage(null); setError('Upload cancelled — the report type was not confirmed.')
          }}
        />
      )}
    </div>
  )
}
