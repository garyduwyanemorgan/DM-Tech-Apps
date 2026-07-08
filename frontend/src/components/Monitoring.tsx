import React, { useState, useEffect } from 'react'
import { PageHeader } from './PageHeader'
import { useAuth } from '../context/AuthContext'
import { MONTH_NAMES, MONTHLY_DATA } from '../constants'
import {
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine, ComposedChart, Line, Bar
} from 'recharts'

type MonthlyDataShape = typeof MONTHLY_DATA

interface LiveRow {
  month: number
  month_name: string
  ph: number; do: number; tss: number; turbidity: number; cod: number
  ammonia: number; phosphate: number; oil_grease: number; ecoli: number
  total_coliforms: number; chla: number; phycocyanin: number
  salinity: number; water_temp: number
}

export const Monitoring: React.FC<{ activeSite: string; useSampleData?: boolean }> = ({ activeSite, useSampleData = true }) => {
  const { organizationId, token } = useAuth()
  // The trend charts and annual stats use the static seasonal baseline (they need a full
  // 12-month series). The Monthly Data Log table below shows live saved readings for the
  // active site when they exist, falling back to sample data otherwise.
  const data = MONTHLY_DATA

  const [liveRows, setLiveRows] = useState<LiveRow[] | null>(null)

  useEffect(() => {
    if (!activeSite) { setLiveRows(null); return }
    let cancelled = false
    const load = async () => {
      try {
        const headers: HeadersInit = {}
        if (organizationId) headers['X-Organization-ID'] = organizationId
        if (token) headers['Authorization'] = `Bearer ${token}`
        const res = await fetch(`/api/readings/${encodeURIComponent(activeSite)}?year=${new Date().getFullYear()}`, { headers })
        const json = await res.json()
        if (!cancelled) setLiveRows(res.ok && Array.isArray(json.rows) ? json.rows : null)
      } catch {
        if (!cancelled) setLiveRows(null)
      }
    }
    load()
    return () => { cancelled = true }
  }, [activeSite, organizationId, token])

  const hasLive = !!liveRows && liveRows.length > 0

  const chartData = MONTH_NAMES.map((m, i) => ({
    month: m.slice(0, 3),
    do: data.do[i],
    chla: data.chla[i],
    temp: data.water_temp[i],
    salinity: data.salinity[i],
    phycocyanin: data.phycocyanin[i],
  }))

  // Cell color helpers
  const getCellStyle = (param: string, value: number): React.CSSProperties => {
    let bg = 'transparent'
    let color: string | undefined
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

  // Annual statistics
  const computeStats = (arr: number[]) => {
    const avg = (arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(1)
    const max = Math.max(...arr)
    const min = Math.min(...arr)
    return { avg, max, min }
  }

  const statsFields: { label: string; key: keyof MonthlyDataShape }[] = [
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

  if (!useSampleData && !activeSite) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Water Quality Monitoring" subtitle="Monthly Data Log" />
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: '3rem', textAlign: 'center', color: '#94a3b8' }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>📈</div>
          <div style={{ fontWeight: 600, color: '#64748b', marginBottom: '0.5rem' }}>No data to display</div>
          <div style={{ fontSize: '0.875rem' }}>Sample data is disabled. Select a live site or enable sample data in Settings.</div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      <PageHeader title="Water Quality Monitoring" subtitle={`Monthly Data Log — ${activeSite || 'Sample data'}`} />

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
              {hasLive ? (
                liveRows!.map(r => (
                  <tr key={r.month}>
                    <td style={{ ...tdStyle, fontWeight: 500, whiteSpace: 'nowrap' }}>{r.month_name.slice(0, 3)}</td>
                    <td style={tdStyle}>{r.ph.toFixed(1)}</td>
                    <td style={getCellStyle('do', r.do)}>{r.do.toFixed(1)}</td>
                    <td style={getCellStyle('tss', r.tss)}>{r.tss}</td>
                    <td style={tdStyle}>{r.turbidity}</td>
                    <td style={getCellStyle('cod', r.cod)}>{r.cod}</td>
                    <td style={getCellStyle('ammonia', r.ammonia)}>{r.ammonia.toFixed(1)}</td>
                    <td style={getCellStyle('phosphate', r.phosphate)}>{r.phosphate.toFixed(1)}</td>
                    <td style={tdStyle}>{r.chla}</td>
                    <td style={tdStyle}>{r.phycocyanin}</td>
                    <td style={tdStyle}>{r.salinity}</td>
                    <td style={tdStyle}>{r.water_temp}</td>
                  </tr>
                ))
              ) : (
                MONTH_NAMES.map((month, i) => (
                  <tr key={month}>
                    <td style={{ ...tdStyle, fontWeight: 500, whiteSpace: 'nowrap' }}>{month.slice(0, 3)}</td>
                    <td style={tdStyle}>{data.ph[i].toFixed(1)}</td>
                    <td style={getCellStyle('do', data.do[i])}>{data.do[i].toFixed(1)}</td>
                    <td style={getCellStyle('tss', data.tss[i])}>{data.tss[i]}</td>
                    <td style={tdStyle}>{data.turbidity[i]}</td>
                    <td style={getCellStyle('cod', data.cod[i])}>{data.cod[i]}</td>
                    <td style={getCellStyle('ammonia', data.ammonia[i])}>{data.ammonia[i].toFixed(1)}</td>
                    <td style={getCellStyle('phosphate', data.phosphate[i])}>{data.phosphate[i].toFixed(1)}</td>
                    <td style={tdStyle}>{data.chla[i]}</td>
                    <td style={tdStyle}>{data.phycocyanin[i]}</td>
                    <td style={tdStyle}>{data.salinity[i]}</td>
                    <td style={tdStyle}>{data.water_temp[i]}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {hasLive && (
          <div style={{ marginTop: '0.75rem', fontSize: '0.8rem', color: '#64748b' }}>
            Showing {liveRows!.length} saved reading{liveRows!.length === 1 ? '' : 's'} for {activeSite}. The trend charts and annual statistics below still use the seasonal baseline.
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
                    const s = computeStats(data[f.key] as number[])
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
