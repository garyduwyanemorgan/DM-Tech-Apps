import React, { useEffect, useState } from 'react'
import { PageHeader } from './PageHeader'
import { StatusBadge } from './ui'
import { useAuth } from '../context/AuthContext'
import { COLORS, tableHeaderStyle, tableCellStyle } from '../lib/ui'
import { MONTH_NAMES, COMPLIANCE_LIMITS } from '../constants'
import {
  useMonthlySeries, NoData, SampleBanner, fmt, meanOf, maxOf, minOf,
  type Series, type ParamKey,
} from '../lib/sampleData'

/* ─── Laboratory certificates ─────────────────────────────────────────────────
 * Saved certificates (lab_samples) reaching the compliance report. The verdict
 * is rendered exactly as the API stored it — nothing here derives, upgrades or
 * softens a status.
 */
interface LabCertificate {
  id: string
  report_no: string | null
  report_type: string | null
  laboratory: string | null
  asset_type: string | null
  sampled_at: string | null
  sampling_point: string | null
  standard_code: string | null
  standard_title: string | null
  overall_status: 'COMPLIANT' | 'NON_COMPLIANT' | 'INCOMPLETE' | null
  reviewer_status: string | null
  parameters: number
  failing_parameters: number
  not_assessed_parameters: number
}

/**
 * Verdict presentation. INCOMPLETE is amber and says so in words: parameters
 * were not assessed, which is not a pass. An absent status is not a pass either
 * — it is reported as "no verdict recorded" rather than assumed compliant.
 */
const VERDICT: Record<string, { tone: 'green' | 'amber' | 'red' | 'slate'; label: string; note: string }> = {
  COMPLIANT:     { tone: 'green', label: 'Compliant',              note: 'Met the cited specification' },
  NON_COMPLIANT: { tone: 'red',   label: 'Not compliant',          note: 'One or more parameters exceeded the specification' },
  INCOMPLETE:    { tone: 'amber', label: 'Incomplete — not a pass', note: 'Some parameters were not assessed against a specification' },
}
const NO_VERDICT = { tone: 'slate' as const, label: 'No verdict recorded', note: 'The certificate carries no overall status' }

const verdictOf = (c: LabCertificate) => VERDICT[c.overall_status ?? ''] ?? NO_VERDICT

/** Human review state. Only approved/corrected has been confirmed by a person. */
const REVIEW: Record<string, { tone: 'green' | 'amber' | 'red' | 'slate'; label: string }> = {
  approved:  { tone: 'green', label: 'Approved' },
  corrected: { tone: 'green', label: 'Approved (corrected)' },
  rejected:  { tone: 'red',   label: 'Rejected' },
  pending:   { tone: 'amber', label: 'Pending review' },
}
const reviewOf = (c: LabCertificate) => REVIEW[c.reviewer_status ?? ''] ?? REVIEW.pending
const isApproved = (c: LabCertificate) =>
  c.reviewer_status === 'approved' || c.reviewer_status === 'corrected'

const LabCertificates: React.FC<{ activeSite: string }> = ({ activeSite }) => {
  const { token, organizationId } = useAuth()
  const [certs, setCerts] = useState<LabCertificate[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true); setError(null)
      try {
        const headers: HeadersInit = {}
        if (token) headers['Authorization'] = `Bearer ${token}`
        if (organizationId) headers['X-Organization-ID'] = organizationId
        const qs = activeSite ? `?site=${encodeURIComponent(activeSite)}` : ''
        const res = await fetch(`/api/lab-samples${qs}`, { headers })
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          throw new Error(err.detail || `Server error ${res.status}`)
        }
        const data = await res.json()
        if (!cancelled) setCerts(data.samples || [])
      } catch (e: any) {
        if (!cancelled) { setError(e.message || 'Could not load certificates'); setCerts([]) }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [activeSite, token, organizationId])

  const rows = certs ?? []
  const tally = {
    compliant:    rows.filter(c => c.overall_status === 'COMPLIANT').length,
    nonCompliant: rows.filter(c => c.overall_status === 'NON_COMPLIANT').length,
    incomplete:   rows.filter(c => c.overall_status === 'INCOMPLETE').length,
    unknown:      rows.filter(c => !c.overall_status).length,
    pending:      rows.filter(c => !isApproved(c)).length,
  }
  const summary = [
    `${tally.compliant} compliant`,
    `${tally.nonCompliant} not compliant`,
    `${tally.incomplete} incomplete`,
    ...(tally.unknown ? [`${tally.unknown} with no verdict recorded`] : []),
  ].join(', ')

  return (
    <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div>
        <h2 className="section-heading" style={{ fontSize: '1.1rem', fontWeight: 700, color: COLORS.navy, marginBottom: '0.35rem' }}>
          Laboratory Certificates
        </h2>
        <p style={{ fontSize: '0.9rem', color: COLORS.slate, margin: 0 }}>
          Certificates saved from Upload Lab Report for {activeSite || 'the selected site'}, with the
          verdict recorded against the standard each was judged by.
        </p>
      </div>

      {error && (
        <div style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.65rem 1rem', borderRadius: 6, fontSize: '0.875rem' }}>
          {error}
        </div>
      )}

      {loading ? (
        <p style={{ color: COLORS.slateLight, fontSize: '0.875rem' }}>Loading certificates…</p>
      ) : rows.length === 0 ? (
        <div style={{
          padding: '1.5rem', textAlign: 'center', border: `1px dashed ${COLORS.border}`,
          borderRadius: 8, background: COLORS.surface,
        }}>
          <p style={{ fontSize: '0.9rem', color: '#374151', fontWeight: 600, margin: 0 }}>
            No laboratory certificates saved yet.
          </p>
          <p style={{ fontSize: '0.82rem', color: COLORS.slate, margin: '0.4rem 0 0' }}>
            Certificates appear here once you save one from <strong>Upload Lab Report</strong> —
            saving is the point at which you confirm the extracted result is correct.
          </p>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.875rem', color: '#374151', fontWeight: 600 }}>
              {rows.length} certificate{rows.length === 1 ? '' : 's'}: {summary}.
            </span>
            {tally.pending > 0 && (
              <StatusBadge tone="amber" variant="count">
                {tally.pending} awaiting human review
              </StatusBadge>
            )}
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '860px' }}>
              <thead>
                <tr>
                  {['Report No', 'Date Sampled', 'Laboratory', 'Asset Type', 'Governing Standard', 'Parameters', 'Status', 'Review'].map(h => (
                    <th key={h} style={tableHeaderStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(c => {
                  const v = verdictOf(c)
                  const r = reviewOf(c)
                  const approved = isApproved(c)
                  return (
                    <tr key={c.id} style={{
                      // An unreviewed certificate must not read like a confirmed
                      // compliance record: it is tinted and left-flagged amber.
                      background: approved ? 'transparent' : COLORS.amberBg,
                      borderLeft: `4px solid ${approved ? 'transparent' : COLORS.amberBorder}`,
                    }}>
                      <td style={{ ...tableCellStyle, fontWeight: 600, whiteSpace: 'nowrap' }}>
                        {c.report_no || '—'}
                        {c.report_type && (
                          <span style={{ display: 'block', fontSize: '0.72rem', color: COLORS.slate, fontWeight: 400 }}>
                            {c.report_type}
                          </span>
                        )}
                      </td>
                      <td style={{ ...tableCellStyle, whiteSpace: 'nowrap' }}>{c.sampled_at || '—'}</td>
                      <td style={tableCellStyle}>{c.laboratory || '—'}</td>
                      <td style={tableCellStyle}>
                        {c.asset_type || '—'}
                        {c.sampling_point && (
                          <span style={{ display: 'block', fontSize: '0.72rem', color: COLORS.slate }}>
                            {c.sampling_point}
                          </span>
                        )}
                      </td>
                      <td style={tableCellStyle}>
                        {c.standard_code
                          ? <span style={{ fontWeight: 600, color: '#2E5D8A' }}>{c.standard_code}</span>
                          : <span style={{ color: COLORS.slate, fontStyle: 'italic' }}>None cited</span>}
                        {c.standard_title && (
                          <span style={{ display: 'block', fontSize: '0.72rem', color: COLORS.slate }}>
                            {c.standard_title}
                          </span>
                        )}
                      </td>
                      <td style={{ ...tableCellStyle, whiteSpace: 'nowrap' }}>
                        {c.parameters} tested
                        <span style={{
                          display: 'block', fontSize: '0.72rem',
                          color: c.failing_parameters > 0 ? COLORS.redFg : COLORS.slate,
                          fontWeight: c.failing_parameters > 0 ? 700 : 400,
                        }}>
                          {c.failing_parameters} failing
                          {c.not_assessed_parameters > 0 && `, ${c.not_assessed_parameters} not assessed`}
                        </span>
                      </td>
                      <td style={tableCellStyle}>
                        <StatusBadge tone={v.tone}>{v.label}</StatusBadge>
                        <span style={{ display: 'block', fontSize: '0.72rem', color: COLORS.slate, marginTop: '0.25rem' }}>
                          {v.note}
                        </span>
                      </td>
                      <td style={tableCellStyle}>
                        <StatusBadge tone={r.tone} variant="count">{r.label}</StatusBadge>
                        {!approved && (
                          <span style={{ display: 'block', fontSize: '0.72rem', color: COLORS.amberFg, marginTop: '0.25rem', fontWeight: 600 }}>
                            Not yet approved by a reviewer
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', paddingTop: '0.5rem', borderTop: `1px solid ${COLORS.border}` }}>
            {[
              { bg: COLORS.greenBg, fg: COLORS.greenFg, label: 'Compliant — met the cited specification' },
              { bg: COLORS.redBg, fg: COLORS.redFg, label: 'Not compliant — a parameter exceeded it' },
              { bg: COLORS.amberBg, fg: COLORS.amberFg, label: 'Incomplete — not a pass; parameters unassessed' },
              { bg: '#f1f5f9', fg: COLORS.slate, label: 'No verdict recorded on the certificate' },
            ].map(({ bg, fg, label }) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <div style={{ width: 24, height: 16, borderRadius: 3, background: bg, border: `1px solid ${fg}` }} />
                <span style={{ fontSize: '0.75rem', color: COLORS.slate }}>{label}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// Month abbreviations for heatmap columns
const MONTH_ABBR = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

/**
 * Compliance for every parameter across the year.
 *
 * A month with no reading is `null` throughout — NOT a pass, NOT a fail, and never
 * back-filled from the sample baseline. This page previously merged sample values
 * under whatever the API returned, so its compliance percentages could disagree with
 * the PDF that a regulator actually receives.
 */
function computeCompliance(data: Series) {
  const result: Record<string, {
    compliant: (boolean | null)[]
    margin_pct: (number | null)[]
    values: (number | null)[]
  }> = {}

  for (const key of Object.keys(COMPLIANCE_LIMITS)) {
    const limit = COMPLIANCE_LIMITS[key]
    // COMPLIANCE_LIMITS calls it total_coliforms; the series calls it coliforms.
    const dataKey = (key === 'total_coliforms' ? 'coliforms' : key) as ParamKey
    const rawValues = data[dataKey] ?? Array(12).fill(null)

    const compliant: (boolean | null)[] = []
    const margin_pct: (number | null)[] = []
    const values: (number | null)[] = []

    for (let i = 0; i < 12; i++) {
      const val = rawValues[i]
      values.push(val ?? null)

      if (typeof val !== 'number') {
        compliant.push(null)
        margin_pct.push(null)
        continue
      }

      const minOk = limit.min === null || val >= limit.min
      const maxOk = limit.max === null || val <= limit.max
      compliant.push(minOk && maxOk)

      // Margin percent: how far from the limit
      if (limit.max !== null) {
        margin_pct.push(((limit.max - val) / limit.max) * 100)
      } else if (limit.min !== null) {
        margin_pct.push(((val - limit.min) / limit.min) * 100)
      } else {
        margin_pct.push(100)
      }
    }

    result[key] = { compliant, margin_pct, values }
  }

  return result
}

function marginColor(pct: number | null): string {
  if (pct === null) return '#94a3b8'
  if (pct < 0) return '#9C0006'
  if (pct < 25) return '#856404'
  return '#006100'
}

function marginBg(pct: number | null): string {
  if (pct === null) return '#f1f5f9'
  if (pct < 0) return '#FFC7CE'
  if (pct < 25) return '#FFEB9C'
  return '#C6EFCE'
}

export const ComplianceReport: React.FC<{ activeSite: string }> = ({ activeSite }) => {
  const { token, organizationId } = useAuth()
  const { series, source, loading } = useMonthlySeries(activeSite)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)

  const downloadPdf = async (draft: boolean) => {
    if (!activeSite) return
    setPdfLoading(true); setPdfError(null)
    try {
      const headers: HeadersInit = {}
      if (token) headers['Authorization'] = `Bearer ${token}`
      if (organizationId) headers['X-Organization-ID'] = organizationId
      const res = await fetch(`/api/report/${encodeURIComponent(activeSite)}?draft=${draft}`, { headers })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Server error ${res.status}`)
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Compliance_${activeSite}_2026${draft ? '_DRAFT' : ''}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      setPdfError(e.message || 'PDF generation failed')
    } finally {
      setPdfLoading(false)
    }
  }

  if (!series) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Regulatory Compliance Report" subtitle={`Reporting Period: 2026 — ${activeSite || 'All Sites'}`} />
        {/* Saved certificates do not depend on the monthly `readings` series, so
            they still render when there is no monthly data for this site. */}
        <LabCertificates activeSite={activeSite} />
        <NoData icon="📄" />
      </div>
    )
  }

  const isLive = source === 'live'
  const compliance = computeCompliance(series)
  const paramKeys = Object.keys(COMPLIANCE_LIMITS)

  // Annual statistics per parameter. Every denominator counts only the months that
  // carry a reading — a year with three sampled months reads "3/3", not "3/12".
  const annualStats = paramKeys.map(key => {
    const { compliant, values } = compliance[key]
    const limit = COMPLIANCE_LIMITS[key]
    const assessed = compliant.filter((c): c is boolean => c !== null)
    const monthsCompliant = assessed.filter(Boolean).length
    const compPct = assessed.length ? Math.round((monthsCompliant / assessed.length) * 100) : null
    const allCompliant = assessed.length > 0 && monthsCompliant === assessed.length
    return {
      key, limit, values,
      avg: meanOf(values), max: maxOf(values), min: minOf(values),
      monthsCompliant, monthsAssessed: assessed.length, compPct, allCompliant,
    }
  })

  // Overall compliance across every parameter-month that was actually measured.
  const assessedCount = paramKeys.reduce(
    (acc, key) => acc + compliance[key].compliant.filter(c => c !== null).length, 0)
  const compliantCount = paramKeys.reduce(
    (acc, key) => acc + compliance[key].compliant.filter(c => c === true).length, 0)
  const overallPct = assessedCount ? Math.round((compliantCount / assessedCount) * 100) : null
  const allPerfect = overallPct === 100
  const zeroExceedance = annualStats.filter(s => s.allCompliant).length
  const monthsSampled = new Set(
    paramKeys.flatMap(k => compliance[k].compliant
      .map((c, i) => (c === null ? -1 : i))
      .filter(i => i >= 0)),
  ).size

  // Every parameter-month that failed its limit, as an incident row.
  const incidents = paramKeys.flatMap(key => {
    const limit = COMPLIANCE_LIMITS[key]
    const { compliant, values, margin_pct } = compliance[key]
    return compliant.flatMap((c, i) =>
      c === false
        ? [{
            key,
            monthIndex: i,
            parameter: limit.parameter,
            unit: limit.unit,
            display: limit.display,
            value: values[i],
            margin: margin_pct[i] ?? 0,
          }]
        : [],
    )
  }).sort((a, b) => a.monthIndex - b.monthIndex)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>

      <PageHeader title="Regulatory Compliance Report" subtitle={`Reporting Period: 2026 — ${activeSite || 'All Sites'}`} />

      {!isLive && <SampleBanner />}

      {!isLive && (
        <div style={{ background: '#FFF5F5', color: '#9C0006', border: '1px solid #f87171', borderRadius: 6, padding: '0.65rem 1rem', fontSize: '0.85rem', lineHeight: 1.5 }}>
          The figures below are the sample baseline. The <strong>PDF export is generated from
          real stored readings only</strong>, so it will not match this page until this site has
          lab readings logged.
        </div>
      )}

      {/* ─── 1b. LABORATORY CERTIFICATES ────────────────────────────── */}
      <LabCertificates activeSite={activeSite} />

      {/* ─── 2. PDF DOWNLOAD SECTION ────────────────────────────────── */}
      <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '0.35rem' }}>
            📄 Export Official Report
          </h2>
          <p style={{ fontSize: '0.9rem', color: '#64748b' }}>
            Generate a formatted, submission-ready compliance PDF for {activeSite || 'the selected site'}.
          </p>
        </div>
        {[pdfLoading, pdfError].includes(pdfLoading) && pdfError && (
          <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.65rem 1rem', borderRadius: 6, fontSize: '0.875rem' }}>{pdfError}</div>
        )}
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button onClick={() => downloadPdf(false)} disabled={pdfLoading || !activeSite}>
            {pdfLoading ? 'Generating PDF…' : 'Download Official Report (PDF)'}
          </button>
          <button className="secondary" onClick={() => downloadPdf(true)} disabled={pdfLoading || !activeSite}>
            Preview Draft (Watermarked)
          </button>
        </div>
        {!activeSite && <p style={{ fontSize: '0.8rem', color: '#f59e0b' }}>Select a site in the sidebar to enable PDF generation.</p>}
      </div>

      {/* ─── 3. MONTHLY COMPLIANCE SUMMARY TABLE ────────────────────── */}
      <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C' }}>
          Monthly Compliance Summary
        </h2>
        {loading ? (
          <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>Loading data…</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', minWidth: '700px' }}>
              <thead>
                <tr>
                  {['Parameter','Unit','Compliance Limit','Annual Avg','Annual Max','Annual Min','Months Compliant','Compliance %','Status'].map(h => (
                    <th key={h} style={{
                      padding: '0.6rem 0.75rem',
                      textAlign: 'left',
                      color: '#64748b',
                      fontWeight: 700,
                      whiteSpace: 'nowrap',
                      background: '#f8fafc',
                      borderBottom: '2px solid #e2e8f0',
                      textTransform: 'uppercase',
                      fontSize: '0.75rem',
                      letterSpacing: '0.04em',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {annualStats.map(({ key, limit, avg, max, min, monthsCompliant, monthsAssessed, compPct, allCompliant }) => (
                  <tr key={key} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151', fontWeight: 500, whiteSpace: 'nowrap' }}>
                      {limit.parameter}
                    </td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#64748b', whiteSpace: 'nowrap' }}>{limit.unit}</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#2E5D8A', fontWeight: 600, whiteSpace: 'nowrap' }}>{limit.display}</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>{fmt(avg)}</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>{fmt(max)}</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>{fmt(min)}</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>
                      {monthsAssessed ? `${monthsCompliant}/${monthsAssessed}` : '—'}
                    </td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>
                      {compPct === null ? '—' : `${compPct}%`}
                    </td>
                    <td style={{ padding: '0.55rem 0.75rem' }}>
                      {monthsAssessed === 0 ? (
                        <span style={{ display: 'inline-block', background: '#e0f2fe', color: '#075985', fontWeight: 700, fontSize: '0.75rem', borderRadius: 4, padding: '3px 8px', whiteSpace: 'nowrap' }}>
                          NO READINGS
                        </span>
                      ) : (
                        <span style={{
                          display: 'inline-block',
                          background: allCompliant ? '#C6EFCE' : '#FFC7CE',
                          color: allCompliant ? '#006100' : '#9C0006',
                          fontWeight: 700, fontSize: '0.75rem', borderRadius: 4, padding: '3px 8px', whiteSpace: 'nowrap',
                        }}>
                          {allCompliant ? 'FULL COMPLIANCE' : 'EXCEEDANCE'}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ─── 4. ANNUAL SCORECARD ────────────────────────────────────── */}
      <div>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '1rem' }}>
          Annual Scorecard
        </h2>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem',
        }}>
          {/* Overall Compliance */}
          <div className="glass-card" style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
              Overall Compliance
            </p>
            <p style={{ fontSize: '2.2rem', fontWeight: 800, color: overallPct === null ? '#94a3b8' : allPerfect ? '#006100' : '#9C0006', lineHeight: 1 }}>
              {overallPct === null ? '—' : `${overallPct}%`}
            </p>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.35rem' }}>
              {overallPct === null
                ? 'No readings logged'
                : allPerfect ? 'All measured parameters within limits' : 'Some exceedances detected'}
            </p>
          </div>

          {/* Zero-Exceedance Params */}
          <div className="glass-card" style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
              Zero-Exceedance Params
            </p>
            <p style={{ fontSize: '2.2rem', fontWeight: 800, color: '#1B3A5C', lineHeight: 1 }}>
              {zeroExceedance}/{paramKeys.length}
            </p>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.35rem' }}>
              Compliant in every month sampled
            </p>
          </div>

          {/* Months sampled — replaces a hardcoded "2,160 monitoring hours / 24/7 sensor
              coverage", which claimed continuous telemetry the platform does not have. */}
          <div className="glass-card" style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
              Months Sampled
            </p>
            <p style={{ fontSize: '2.2rem', fontWeight: 800, color: '#2E5D8A', lineHeight: 1 }}>
              {monthsSampled}/12
            </p>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.35rem' }}>
              Months with a logged lab reading
            </p>
          </div>

          {/* Exceedances — counted from the series, not hardcoded to zero. */}
          <div className="glass-card" style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
              Exceedances
            </p>
            <p style={{ fontSize: '2.2rem', fontWeight: 800, color: assessedCount - compliantCount > 0 ? '#9C0006' : '#006100', lineHeight: 1 }}>
              {assessedCount - compliantCount}
            </p>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.35rem' }}>
              Parameter-months outside limits
            </p>
          </div>
        </div>
      </div>

      {/* ─── 5. COMPLIANCE HEATMAP ──────────────────────────────────── */}
      <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C' }}>
          Monthly Parameter Status Heatmap
        </h2>
        {loading ? (
          <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>Loading data…</p>
        ) : (
          <>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '2px', fontSize: '0.75rem', minWidth: '780px' }}>
                <thead>
                  <tr>
                    <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left', color: '#64748b', fontWeight: 600, width: '140px' }}>
                      Parameter
                    </th>
                    {MONTH_ABBR.map(m => (
                      <th key={m} style={{ padding: '0.5rem 0.35rem', color: '#64748b', fontWeight: 600, textAlign: 'center' }}>{m}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paramKeys.map(key => {
                    const limit = COMPLIANCE_LIMITS[key]
                    const { margin_pct, values } = compliance[key]
                    return (
                      <tr key={key}>
                        <td style={{ padding: '0.35rem 0.75rem', color: '#374151', fontWeight: 500, whiteSpace: 'nowrap', fontSize: '0.78rem' }}>
                          {limit.parameter}
                        </td>
                        {margin_pct.map((pct, i) => (
                          <td key={i} style={{
                            padding: '0.3rem 0.2rem',
                            textAlign: 'center',
                            borderRadius: '4px',
                            background: marginBg(pct),
                            color: marginColor(pct),
                            fontWeight: 600,
                            fontSize: '0.7rem',
                            minWidth: '42px',
                          }}
                          title={pct === null
                            ? `${limit.parameter} ${MONTH_NAMES[i]}: no reading logged`
                            : `${limit.parameter} ${MONTH_NAMES[i]}: ${values[i]} ${limit.unit} (margin ${pct.toFixed(1)}%)`}
                          >
                            {pct === null ? '–' : pct >= 0 ? `+${pct.toFixed(0)}%` : `${pct.toFixed(0)}%`}
                          </td>
                        ))}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Legend */}
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', paddingTop: '0.5rem', borderTop: '1px solid #e2e8f0' }}>
              {[
                { color: '#006100', bg: '#C6EFCE', label: 'Safe margin >25%' },
                { color: '#856404', bg: '#FFEB9C', label: 'Approaching limit (<25%)' },
                { color: '#9C0006', bg: '#FFC7CE', label: 'Exceeded' },
                { color: '#94a3b8', bg: '#f1f5f9', label: 'No reading logged' },
              ].map(({ color, bg, label }) => (
                <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <div style={{
                    width: '24px', height: '16px', borderRadius: '3px',
                    background: bg, border: `1px solid ${color}`,
                  }} />
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>{label}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* ─── 6. INCIDENT LOG ────────────────────────────────────────── */}
      <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C' }}>
          Incident Log
        </h2>

        {/* Derived from the series. The old version hardcoded a green "no incidents"
            notice and an empty table, which asserted full compliance even when the
            heatmap directly above it showed exceedances. */}
        {incidents.length === 0 ? (
          <div style={{
            padding: '0.85rem 1rem',
            background: '#C6EFCE',
            border: '1px solid #86efac',
            borderRadius: '0.5rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.6rem',
          }}>
            <span style={{ fontSize: '1.1rem' }}>&#x2705;</span>
            <p style={{ fontSize: '0.875rem', color: '#006100', fontWeight: 500, margin: 0 }}>
              No exceedances in the {monthsSampled} month(s) sampled. Months with no reading are
              not assessed.
            </p>
          </div>
        ) : (
          <div style={{
            padding: '0.85rem 1rem',
            background: '#FFC7CE',
            border: '1px solid #f87171',
            borderRadius: '0.5rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.6rem',
          }}>
            <span style={{ fontSize: '1.1rem' }}>&#x26A0;</span>
            <p style={{ fontSize: '0.875rem', color: '#9C0006', fontWeight: 500, margin: 0 }}>
              {incidents.length} exceedance(s) recorded in the reporting period.
            </p>
          </div>
        )}

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', minWidth: '620px' }}>
            <thead>
              <tr>
                {['Month','Parameter','Measured Value','Compliance Limit','Margin'].map(h => (
                  <th key={h} style={{
                    padding: '0.6rem 0.75rem',
                    textAlign: 'left',
                    color: '#64748b',
                    fontWeight: 700,
                    whiteSpace: 'nowrap',
                    background: '#f8fafc',
                    borderBottom: '2px solid #e2e8f0',
                    textTransform: 'uppercase',
                    fontSize: '0.72rem',
                    letterSpacing: '0.04em',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {incidents.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: '#475569', fontSize: '0.85rem', fontStyle: 'italic' }}>
                    No exceedances to display for this reporting period.
                  </td>
                </tr>
              ) : incidents.map(inc => (
                <tr key={`${inc.key}-${inc.monthIndex}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>{MONTH_NAMES[inc.monthIndex]}</td>
                  <td style={{ padding: '0.55rem 0.75rem', color: '#374151', fontWeight: 500 }}>{inc.parameter}</td>
                  <td style={{ padding: '0.55rem 0.75rem', color: '#9C0006', fontWeight: 700 }}>{fmt(inc.value)} {inc.unit}</td>
                  <td style={{ padding: '0.55rem 0.75rem', color: '#2E5D8A', fontWeight: 600 }}>{inc.display}</td>
                  <td style={{ padding: '0.55rem 0.75rem', color: '#9C0006', fontWeight: 600 }}>{inc.margin.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  )
}
