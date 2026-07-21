import React, { useEffect, useState } from 'react'
import { PageHeader } from './PageHeader'
import { useAuth } from '../context/AuthContext'
import { StatusBadge } from './ui'
import { COLORS, tableHeaderStyle, tableCellStyle } from '../lib/ui'
import { MONTH_NAMES } from '../constants'
import {
  useMonthlySeries, NoData, SampleBanner, fmt, meanOf, maxOf, minOf, type ParamKey,
} from '../lib/sampleData'
import {
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine, ComposedChart, Line, Bar
} from 'recharts'

/* ─── Laboratory certificates ─────────────────────────────────────────────────
 * Certificates returned by `/api/status/{site}` alongside the readings. The
 * verdict is rendered exactly as the API stored it — nothing here derives,
 * upgrades or softens a status.
 */
interface StatusCertificate {
  report_no: string | null
  sampled_at: string | null
  report_type: string | null
  asset_type: string | null
  laboratory: string | null
  standard_code: string | null
  overall_status: 'COMPLIANT' | 'NON_COMPLIANT' | 'INCOMPLETE' | null
  reviewer_status: 'pending' | 'approved' | 'corrected' | 'rejected' | null
  fail_count: number
  total_parameters: number
}

const VERDICT: Record<string, { tone: 'green' | 'amber' | 'red' | 'slate'; label: string }> = {
  COMPLIANT:     { tone: 'green', label: 'Compliant' },
  NON_COMPLIANT: { tone: 'red',   label: 'Not compliant' },
  INCOMPLETE:    { tone: 'amber', label: 'Incomplete — not a pass' },
}
const NO_VERDICT = { tone: 'slate' as const, label: 'No verdict recorded' }
const verdictOf = (c: StatusCertificate) => VERDICT[c.overall_status ?? ''] ?? NO_VERDICT

const REVIEW: Record<string, { tone: 'green' | 'amber' | 'red' | 'slate'; label: string }> = {
  approved:  { tone: 'green', label: 'Approved' },
  corrected: { tone: 'green', label: 'Approved (corrected)' },
  rejected:  { tone: 'red',   label: 'Rejected' },
  pending:   { tone: 'amber', label: 'Awaiting review' },
}
const reviewOf = (c: StatusCertificate) => REVIEW[c.reviewer_status ?? ''] ?? REVIEW.pending
const isApproved = (c: StatusCertificate) =>
  c.reviewer_status === 'approved' || c.reviewer_status === 'corrected'

/**
 * Certificates saved for this site. Kept deliberately separate from the monthly
 * series: it renders whether or not the site has a readings series.
 */
export const SiteCertificates: React.FC<{ activeSite: string }> = ({ activeSite }) => {
  const { token, organizationId } = useAuth()
  const [certs, setCerts] = useState<StatusCertificate[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!activeSite) { setCerts([]); setError(null); setLoading(false); return }
    let cancelled = false
    const load = async () => {
      setLoading(true); setError(null)
      try {
        const headers: HeadersInit = {}
        if (token) headers['Authorization'] = `Bearer ${token}`
        if (organizationId) headers['X-Organization-ID'] = organizationId
        const res = await fetch(`/api/status/${encodeURIComponent(activeSite)}`, { headers })
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          throw new Error(err.detail || `Server error ${res.status}`)
        }
        const data = await res.json()
        if (!cancelled) setCerts(Array.isArray(data.certificates) ? data.certificates : [])
      } catch (e: any) {
        // null certs = "we do not know", which renders as unavailable, not as zero.
        if (!cancelled) { setError(e?.message || 'Could not load certificates'); setCerts(null) }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [activeSite, token, organizationId])

  const rows = certs ?? []
  const awaiting = rows.filter(c => !isApproved(c)).length

  return (
    <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div>
        <h3 className="section-heading" style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: COLORS.navy }}>
          Laboratory Certificates
        </h3>
        <p style={{ fontSize: '0.875rem', color: COLORS.slate, margin: '0.35rem 0 0' }}>
          Certificates saved for {activeSite || 'the selected site'}, with the verdict recorded
          against the standard each was judged by.
        </p>
      </div>

      {loading ? (
        <p style={{ color: COLORS.slateLight, fontSize: '0.875rem', margin: 0 }}>Loading certificates…</p>
      ) : error ? (
        <div style={{ padding: '1rem', border: `1px solid ${COLORS.redBorder}`, background: COLORS.redBg, color: COLORS.redFg, borderRadius: 8, fontSize: '0.875rem' }}>
          <strong>Certificate data is unavailable.</strong> {error}. No count is shown — this is not
          a statement that the site has no certificates.
        </div>
      ) : rows.length === 0 ? (
        <div style={{ padding: '1.5rem', textAlign: 'center', border: `1px dashed ${COLORS.border}`, borderRadius: 8, background: COLORS.surface }}>
          <p style={{ fontSize: '0.9rem', color: '#374151', fontWeight: 600, margin: 0 }}>
            No laboratory certificates saved yet.
          </p>
          <p style={{ fontSize: '0.82rem', color: COLORS.slate, margin: '0.4rem 0 0' }}>
            Certificates appear here once you save one from <strong>Upload Lab Report</strong>.
          </p>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.875rem', color: '#374151', fontWeight: 600 }}>
              {rows.length} certificate{rows.length === 1 ? '' : 's'}.
            </span>
            {awaiting > 0 && (
              <StatusBadge tone="amber" variant="count">{awaiting} awaiting human review</StatusBadge>
            )}
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '820px' }}>
              <thead>
                <tr>
                  {['Report No', 'Date Sampled', 'Asset Type', 'Governing Standard', 'Parameters', 'Status', 'Review'].map(h => (
                    <th key={h} scope="col" style={tableHeaderStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((c, i) => {
                  const v = verdictOf(c)
                  const r = reviewOf(c)
                  const approved = isApproved(c)
                  return (
                    <tr key={`${c.report_no ?? 'cert'}-${c.sampled_at ?? ''}-${i}`} style={{
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
                      <td style={tableCellStyle}>
                        {c.asset_type || '—'}
                        {c.laboratory && (
                          <span style={{ display: 'block', fontSize: '0.72rem', color: COLORS.slate }}>
                            {c.laboratory}
                          </span>
                        )}
                      </td>
                      <td style={tableCellStyle}>
                        {c.standard_code
                          ? <span style={{ fontWeight: 600, color: '#2E5D8A' }}>{c.standard_code}</span>
                          : <span style={{ color: COLORS.slate, fontStyle: 'italic' }}>None cited</span>}
                      </td>
                      <td style={{ ...tableCellStyle, whiteSpace: 'nowrap' }}>
                        {c.total_parameters} tested
                        <span style={{
                          display: 'block', fontSize: '0.72rem',
                          color: c.fail_count > 0 ? COLORS.redFg : COLORS.slate,
                          fontWeight: c.fail_count > 0 ? 700 : 400,
                        }}>
                          {c.fail_count} failing
                        </span>
                      </td>
                      <td style={tableCellStyle}>
                        <StatusBadge tone={v.tone}>{v.label}</StatusBadge>
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

export const Monitoring: React.FC<{ activeSite: string }> = ({ activeSite }) => {
  // Table, trend charts, and annual statistics all read the SAME series. Previously the
  // charts and stats were hardwired to the sample baseline while the table showed live
  // readings, so a site with real data got real rows under synthetic trend lines.
  const { series, source } = useMonthlySeries(activeSite)

  const hasLive = source === 'live'

  const chartData = MONTH_NAMES.map((m, i) => ({
    month: m.slice(0, 3),
    // recharts renders null as a gap in the line, which is what an unsampled month is.
    do: series?.do[i] ?? null,
    chla: series?.chla[i] ?? null,
    temp: series?.water_temp[i] ?? null,
    salinity: series?.salinity[i] ?? null,
    phycocyanin: series?.phycocyanin[i] ?? null,
  }))

  // Cell color helpers
  const getCellStyle = (param: string, value: number | null): React.CSSProperties => {
    let bg = 'transparent'
    let color: string | undefined
    if (value === null) {
      return { padding: '0.75rem 0.85rem', color: '#94a3b8' }
    }
    if (param === 'do') {
      if (value <= 4.0) { bg = '#FFC7CE'; color = '#9C0006' }
      else if (value <= 5.0) { bg = '#FFEB9C'; color = '#856404' }
    } else if (param === 'tss') {
      if (value >= 50) { bg = '#FFC7CE'; color = '#9C0006' }
      else if (value >= 40) { bg = '#FFEB9C'; color = '#856404' }
    } else if (param === 'cod') {
      if (value >= 50) { bg = '#FFC7CE'; color = '#9C0006' }
      else if (value >= 40) { bg = '#FFEB9C'; color = '#856404' }
    } else if (param === 'ammonia') {
      if (value >= 5.0) { bg = '#FFC7CE'; color = '#9C0006' }
      else if (value >= 4.0) { bg = '#FFEB9C'; color = '#856404' }
    } else if (param === 'phosphate') {
      if (value >= 5.0) { bg = '#FFC7CE'; color = '#9C0006' }
      else if (value >= 4.0) { bg = '#FFEB9C'; color = '#856404' }
    }
    return { padding: '0.75rem 0.85rem', background: bg, borderRadius: '4px', ...(color ? { color, fontWeight: 600 } : {}) }
  }

  // Annual statistics — computed only over the months that carry a reading.
  const computeStats = (arr: (number | null)[]) => ({
    avg: fmt(meanOf(arr), 1),
    max: fmt(maxOf(arr), 1),
    min: fmt(minOf(arr), 1),
  })

  const statsFields: { label: string; key: ParamKey }[] = [
    { label: 'pH', key: 'ph' },
    { label: 'DO (mg/L)', key: 'do' },
    { label: 'TSS (mg/L)', key: 'tss' },
    { label: 'Chl-a (µg/L)', key: 'chla' },
    { label: 'Temp (°C)', key: 'water_temp' },
    { label: 'Salinity (PSU)', key: 'salinity' },
  ]

  const thStyle: React.CSSProperties = {
    padding: '0.75rem 1rem',
    fontSize: '0.8rem',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    fontWeight: 700,
    color: '#64748b',
    whiteSpace: 'nowrap',
    background: '#f8fafc',
    borderBottom: '2px solid #e2e8f0',
  }

  const tdStyle: React.CSSProperties = {
    padding: '0.75rem 1rem',
    fontSize: '0.9rem',
    color: '#374151',
    borderBottom: '1px solid #f1f5f9',
  }

  const tooltipStyle = {
    contentStyle: { background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', color: '#374151' },
    labelStyle: { color: '#1B3A5C', fontWeight: 600 },
    itemStyle: { color: '#374151' },
  }

  if (!series) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Water Quality Monitoring" subtitle="Monthly Data Log" />
        {/* Saved certificates do not depend on the monthly series, so they still
            render when this site has no monthly readings. */}
        <SiteCertificates activeSite={activeSite} />
        <NoData icon="📈" />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      <PageHeader title="Water Quality Monitoring" subtitle={`Monthly Data Log — ${activeSite || 'Sample data'}`} />

      {!hasLive && <SampleBanner />}

      {/* SECTION 0: LABORATORY CERTIFICATES (real uploaded lab reports) */}
      <SiteCertificates activeSite={activeSite} />

      {/* SECTION 1: MONTHLY DATA TABLE */}
      <div className="glass-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1.25rem' }}>
          <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600 }}>
            Monthly Water Quality Data
          </h3>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, borderRadius: 4, padding: '2px 10px', ...(hasLive ? { background: '#C6EFCE', color: '#006100' } : { background: '#f1f5f9', color: '#64748b' }) }}>
            {hasLive ? `● Live — ${activeSite}` : '○ Sample data'}
          </span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: '900px' }}>
            <thead>
              <tr>
                {['Month', 'pH', 'DO (mg/L)', 'TSS (mg/L)', 'Turbidity (NTU)', 'COD (mg/L)', 'Ammonia', 'Phosphate', 'Chl-a', 'Phycocyanin', 'Salinity', 'Temp'].map(col => (
                  <th key={col} style={thStyle}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {MONTH_NAMES.map((month, i) => (
                <tr key={month}>
                  <td style={{ ...tdStyle, fontWeight: 500, whiteSpace: 'nowrap' }}>{month.slice(0, 3)}</td>
                  <td style={tdStyle}>{fmt(series.ph[i], 1)}</td>
                  <td style={getCellStyle('do', series.do[i])}>{fmt(series.do[i], 1)}</td>
                  <td style={getCellStyle('tss', series.tss[i])}>{fmt(series.tss[i], 0)}</td>
                  <td style={tdStyle}>{fmt(series.turbidity[i], 0)}</td>
                  <td style={getCellStyle('cod', series.cod[i])}>{fmt(series.cod[i], 0)}</td>
                  <td style={getCellStyle('ammonia', series.ammonia[i])}>{fmt(series.ammonia[i], 1)}</td>
                  <td style={getCellStyle('phosphate', series.phosphate[i])}>{fmt(series.phosphate[i], 1)}</td>
                  <td style={tdStyle}>{fmt(series.chla[i], 0)}</td>
                  <td style={tdStyle}>{fmt(series.phycocyanin[i], 0)}</td>
                  <td style={tdStyle}>{fmt(series.salinity[i], 0)}</td>
                  <td style={tdStyle}>{fmt(series.water_temp[i], 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {hasLive && (
          <div style={{ marginTop: '0.75rem', fontSize: '0.8rem', color: '#64748b' }}>
            Live readings for {activeSite}. Months with no logged reading show “—” and are
            excluded from the trend charts and annual statistics below.
          </div>
        )}
        <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', flexWrap: 'wrap', fontSize: '0.8rem', opacity: 0.7 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', color: '#64748b' }}>
            <span style={{ width: 12, height: 12, borderRadius: 2, background: '#FFC7CE', border: '1px solid #f87171', display: 'inline-block' }} />
            Exceeds compliance limit
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', color: '#64748b' }}>
            <span style={{ width: 12, height: 12, borderRadius: 2, background: '#FFEB9C', border: '1px solid #fcd34d', display: 'inline-block' }} />
            Within 20% of limit
          </span>
        </div>
      </div>

      {/* SECTION 2: WATER QUALITY TRENDS CHART */}
      <div className="glass-card">
        <h3 style={{ marginBottom: '1.25rem', fontSize: '1.05rem', fontWeight: 600 }}>
          Water Quality Trends
        </h3>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="month" tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={tooltipStyle.contentStyle}
              labelStyle={tooltipStyle.labelStyle}
              itemStyle={tooltipStyle.itemStyle}
            />
            <Legend wrapperStyle={{ paddingTop: '1rem', fontSize: '0.85rem' }} />
            <ReferenceLine y={4.0} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'Compliance DO Limit (4.0)', fill: '#ef4444', fontSize: 11, position: 'insideTopLeft' }} />
            <Line
              type="monotone"
              dataKey="do"
              name="DO (mg/L)"
              stroke="#4472C4"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5 }}
            />
            <Line
              type="monotone"
              dataKey="chla"
              name="Chl-a (µg/L)"
              stroke="#10b981"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* SECTION 3: TEMPERATURE & PHYCOCYANIN CHART */}
      <div className="glass-card">
        <h3 style={{ marginBottom: '1.25rem', fontSize: '1.05rem', fontWeight: 600 }}>
          Temperature, Salinity &amp; Phycocyanin
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="month" tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={tooltipStyle.contentStyle}
              labelStyle={tooltipStyle.labelStyle}
              itemStyle={tooltipStyle.itemStyle}
            />
            <Legend wrapperStyle={{ paddingTop: '1rem', fontSize: '0.85rem' }} />
            <Bar dataKey="salinity" name="Salinity (PSU)" fill="#3b82f6" fillOpacity={0.5} />
            <Line
              type="monotone"
              dataKey="phycocyanin"
              name="Phycocyanin (µg/L)"
              stroke="#9b59b6"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5 }}
            />
            <Line
              type="monotone"
              dataKey="temp"
              name="Temperature (°C)"
              stroke="#ef4444"
              strokeWidth={2}
              strokeDasharray="5 3"
              dot={false}
              activeDot={{ r: 5 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* SECTION 4: ANNUAL STATISTICS TABLE */}
      <div className="glass-card">
        <h3 style={{ marginBottom: '1.25rem', fontSize: '1.05rem', fontWeight: 600 }}>
          Annual Statistics
        </h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr>
                <th style={thStyle}>Statistic</th>
                {statsFields.map(f => (
                  <th key={f.key} style={thStyle}>{f.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(['avg', 'max', 'min'] as const).map(stat => (
                <tr key={stat}>
                  <td style={{ ...tdStyle, fontWeight: 600, textTransform: 'capitalize' }}>
                    {stat === 'avg' ? 'Average' : stat === 'max' ? 'Maximum' : 'Minimum'}
                  </td>
                  {statsFields.map(f => {
                    const s = computeStats(series[f.key])
                    return (
                      <td key={f.key} style={tdStyle}>
                        {stat === 'avg' ? s.avg : stat === 'max' ? s.max : s.min}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
