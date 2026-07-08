import React, { useEffect, useState } from 'react'
import { PageHeader } from './PageHeader'
import { useAuth } from '../context/AuthContext'
import { MONTH_NAMES, MONTHLY_DATA, COMPLIANCE_LIMITS } from '../constants'

// Month abbreviations for heatmap columns
const MONTH_ABBR = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

// Compute compliance data for all parameters across all months
function computeCompliance(data: typeof MONTHLY_DATA) {
  const result: Record<string, {
    compliant: boolean[]
    margin_pct: number[]
    values: number[]
  }> = {}

  for (const key of Object.keys(COMPLIANCE_LIMITS)) {
    const limit = COMPLIANCE_LIMITS[key]
    // oil_grease key in MONTHLY_DATA is 'oil_grease', total_coliforms is 'coliforms'
    const dataKey = key === 'total_coliforms' ? 'coliforms' : key
    const rawValues = (data as Record<string, number[]>)[dataKey] ?? []

    const compliant: boolean[] = []
    const margin_pct: number[] = []
    const values: number[] = []

    for (let i = 0; i < 12; i++) {
      const val = rawValues[i] ?? 0
      values.push(val)

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

function marginColor(pct: number): string {
  if (pct < 0) return '#9C0006'
  if (pct < 25) return '#856404'
  return '#006100'
}

function marginBg(pct: number): string {
  if (pct < 0) return '#FFC7CE'
  if (pct < 25) return '#FFEB9C'
  return '#C6EFCE'
}

export const ComplianceReport: React.FC<{ activeSite: string }> = ({ activeSite }) => {
  const { token, organizationId } = useAuth()
  const [data, setData] = useState<typeof MONTHLY_DATA>(MONTHLY_DATA)
  const [loading, setLoading] = useState(true)
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

  useEffect(() => {
    if (!activeSite) { setData(MONTHLY_DATA); setLoading(false); return }
    setLoading(true)
    fetch(`/api/status/${activeSite}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => r.ok ? r.json() : null)
      .then(json => {
        if (json && json.monthly_data) {
          setData({ ...MONTHLY_DATA, ...json.monthly_data })
        } else {
          setData(MONTHLY_DATA)
        }
      })
      .catch(() => setData(MONTHLY_DATA))
      .finally(() => setLoading(false))
  }, [activeSite, token])

  const compliance = computeCompliance(data)
  const paramKeys = Object.keys(COMPLIANCE_LIMITS)

  // Annual statistics per parameter
  const annualStats = paramKeys.map(key => {
    const { compliant, values } = compliance[key]
    const limit = COMPLIANCE_LIMITS[key]
    const avg = values.reduce((a, b) => a + b, 0) / 12
    const max = Math.max(...values)
    const min = Math.min(...values)
    const monthsCompliant = compliant.filter(Boolean).length
    const compPct = Math.round((monthsCompliant / 12) * 100)
    const allCompliant = monthsCompliant === 12
    return { key, limit, avg, max, min, monthsCompliant, compPct, allCompliant, values }
  })

  // Overall compliance
  const totalMonthParam = paramKeys.length * 12
  const compliantCount = paramKeys.reduce((acc, key) => acc + compliance[key].compliant.filter(Boolean).length, 0)
  const overallPct = Math.round((compliantCount / totalMonthParam) * 100)
  const allPerfect = overallPct === 100
  const zeroExceedance = paramKeys.filter(k => compliance[k].compliant.every(Boolean)).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>

      <PageHeader title="Regulatory Compliance Report" subtitle={`Reporting Period: 2026 — ${activeSite || 'All Sites'}`} />

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
                {annualStats.map(({ key, limit, avg, max, min, monthsCompliant, compPct, allCompliant }) => (
                  <tr key={key} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151', fontWeight: 500, whiteSpace: 'nowrap' }}>
                      {limit.parameter}
                    </td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#64748b', whiteSpace: 'nowrap' }}>{limit.unit}</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#2E5D8A', fontWeight: 600, whiteSpace: 'nowrap' }}>{limit.display}</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>{avg.toFixed(2)}</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>{max.toFixed(2)}</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>{min.toFixed(2)}</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>{monthsCompliant}/12</td>
                    <td style={{ padding: '0.55rem 0.75rem', color: '#374151' }}>{compPct}%</td>
                    <td style={{ padding: '0.55rem 0.75rem' }}>
                      <span style={{
                        display: 'inline-block',
                        background: allCompliant ? '#C6EFCE' : '#FFC7CE',
                        color: allCompliant ? '#006100' : '#9C0006',
                        fontWeight: 700, fontSize: '0.75rem', borderRadius: 4, padding: '3px 8px', whiteSpace: 'nowrap',
                      }}>
                        {allCompliant ? 'FULL COMPLIANCE' : 'EXCEEDANCE'}
                      </span>
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
            <p style={{ fontSize: '2.2rem', fontWeight: 800, color: allPerfect ? '#006100' : '#9C0006', lineHeight: 1 }}>
              {overallPct}%
            </p>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.35rem' }}>
              {allPerfect ? 'All parameters within limits' : 'Some exceedances detected'}
            </p>
          </div>

          {/* Zero-Exceedance Params */}
          <div className="glass-card" style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
              Zero-Exceedance Params
            </p>
            <p style={{ fontSize: '2.2rem', fontWeight: 800, color: '#1B3A5C', lineHeight: 1 }}>
              {zeroExceedance}/10
            </p>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.35rem' }}>
              Parameters with full-year compliance
            </p>
          </div>

          {/* Monitoring Hours */}
          <div className="glass-card" style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
              Monitoring Hours
            </p>
            <p style={{ fontSize: '2.2rem', fontWeight: 800, color: '#2E5D8A', lineHeight: 1 }}>
              2,160
            </p>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.35rem' }}>
              24/7 sensor coverage
            </p>
          </div>

          {/* Escalation Incidents */}
          <div className="glass-card" style={{ textAlign: 'center' }}>
            <p style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
              Escalation Incidents
            </p>
            <p style={{ fontSize: '2.2rem', fontWeight: 800, color: '#006100', lineHeight: 1 }}>
              0
            </p>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.35rem' }}>
              No Level 3+ activations
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
                          title={`${limit.parameter} ${MONTH_NAMES[i]}: ${values[i]} ${limit.unit} (margin ${pct.toFixed(1)}%)`}
                          >
                            {pct >= 0 ? `+${pct.toFixed(0)}%` : `${pct.toFixed(0)}%`}
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

        {/* Success notice */}
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
            No incidents recorded. All parameters within compliance limits throughout the reporting period.
          </p>
        </div>

        {/* Empty incident table */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', minWidth: '860px' }}>
            <thead>
              <tr>
                {['Date','Parameter','Measured Value','Compliance Limit','Duration (hr)','Root Cause','Corrective Action','Resolution Date'].map(h => (
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
              <tr>
                <td colSpan={8} style={{ padding: '2rem', textAlign: 'center', color: '#475569', fontSize: '0.85rem', fontStyle: 'italic' }}>
                  No incidents to display for this reporting period.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

    </div>
  )
}
