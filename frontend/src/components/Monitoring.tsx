import React from 'react'
import { PageHeader } from './PageHeader'
import { MONTH_NAMES } from '../constants'
import {
  useMonthlySeries, NoData, SampleBanner, fmt, meanOf, maxOf, minOf, type ParamKey,
} from '../lib/sampleData'
import {
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine, ComposedChart, Line, Bar
} from 'recharts'

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
        <NoData icon="📈" />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      <PageHeader title="Water Quality Monitoring" subtitle={`Monthly Data Log — ${activeSite || 'Sample data'}`} />

      {!hasLive && <SampleBanner />}

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
