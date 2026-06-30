import React from 'react'
import { SLUDGE_ZONES } from '../constants'
import { PageHeader } from './PageHeader'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell,
} from 'recharts'

const ABBREV: Record<string, string> = {
  'Zone A — Inlet':        'Zone A',
  'Zone B — Central':      'Zone B',
  'Zone C — Deep Basin':   'Zone C',
  'Zone D — Shallow Edge': 'Zone D',
  'Zone E — Outlet':       'Zone E',
}

type ZoneStatus = 'OK' | 'WARNING' | 'CRITICAL'

interface ZoneData {
  name: string
  totalDepth: number
  sludgeDepth: number
  effectiveDepth: number
  capacityLoss: number
  status: ZoneStatus
}

const computeZones = (): ZoneData[] =>
  SLUDGE_ZONES.map(z => {
    const effectiveDepth = z.totalDepth - z.sludgeDepth
    const capacityLoss = (z.sludgeDepth / z.totalDepth) * 100
    const status: ZoneStatus =
      capacityLoss > 30 ? 'CRITICAL' : capacityLoss > 20 ? 'WARNING' : 'OK'
    return { ...z, effectiveDepth, capacityLoss, status }
  })

const STATUS_STYLES: Record<ZoneStatus, React.CSSProperties> = {
  OK:       { background: '#C6EFCE', color: '#006100', border: '1px solid #86efac' },
  WARNING:  { background: '#FFEB9C', color: '#856404', border: '1px solid #fcd34d' },
  CRITICAL: { background: '#FFC7CE', color: '#9C0006', border: '1px solid #f87171' },
}

const PIE_DATA = [
  { name: 'Dead algae + bacteria', value: 40, color: '#e74c3c' },
  { name: 'Organic detritus',      value: 26, color: '#f59e0b' },
  { name: 'Sand / silt',           value: 17, color: '#94a3b8' },
  { name: 'Minerals',              value: 17, color: '#64748b' },
]

const COMPOSITION_TABLE = [
  { component: 'Dead algae + bacteria', pct: '~40%', digestible: 'YES', treatment: 'Cellulase + protease + lipase' },
  { component: 'Organic detritus',      pct: '~26%', digestible: 'YES', treatment: 'Enzyme cocktail + bacteria' },
  { component: 'Sand / silt',           pct: '~17%', digestible: 'NO',  treatment: 'Physical removal only' },
  { component: 'Minerals',              pct: '~17%', digestible: 'NO',  treatment: 'Physical removal only' },
]

const NUTRIENT_LOADING_TABLE = [
  {
    condition:    'Bottom DO < 2 mg/L',
    mechanism:    'Fe³⁺ → Fe²⁺ releases bound PO₄',
    contribution: '30–60% of total P',
    prevention:   'Bottom aeration to keep DO > 2',
  },
  {
    condition:    'Water Temp > 30°C',
    mechanism:    'Accelerated sediment P release',
    contribution: 'Proportional to temp',
    prevention:   'Manage via aeration',
  },
  {
    condition:    'Sludge Depth > 3 ft',
    mechanism:    'Large nutrient reservoir in water contact',
    contribution: 'Can feed blooms for years',
    prevention:   'Enzyme bio-dredging + physical removal',
  },
  {
    condition:    'Sediment DOM release',
    mechanism:    'Dissolved organic matter stimulates algae',
    contribution: 'Difficult to quantify',
    prevention:   'Sludge reduction programme',
  },
]

const tableHeaderStyle: React.CSSProperties = {
  padding: '10px 14px',
  textAlign: 'left',
  fontSize: '0.75rem',
  fontWeight: 700,
  color: '#64748b',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  borderBottom: '2px solid #e2e8f0',
  background: '#f8fafc',
  whiteSpace: 'nowrap',
}

const tableCellStyle: React.CSSProperties = {
  padding: '10px 14px',
  fontSize: '0.85rem',
  color: '#374151',
  borderBottom: '1px solid #f1f5f9',
}

export const Sludge: React.FC = () => {
  const zones = computeZones()

  const avgCapacityLoss = zones.reduce((s, z) => s + z.capacityLoss, 0) / zones.length
  const criticalCount = zones.filter(z => z.status === 'CRITICAL').length

  const avgColor =
    avgCapacityLoss > 25 ? '#9C0006' : avgCapacityLoss > 15 ? '#856404' : '#006100'

  const barData = zones.map(z => ({
    name: ABBREV[z.name] ?? z.name,
    'Effective Depth': parseFloat(z.effectiveDepth.toFixed(2)),
    'Sludge Depth':    parseFloat(z.sludgeDepth.toFixed(2)),
  }))

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>

      <PageHeader title="Sludge & Sediment Management" subtitle="Capacity Tracking, Composition & Internal Nutrient Loading" />

      {/* 2. CAPACITY TRACKER TABLE */}
      <div className="glass-card" style={{ marginBottom: '28px', overflowX: 'auto' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '16px' }}>
          Capacity Tracker
        </h2>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '600px' }}>
          <thead>
            <tr>
              {['Zone', 'Total Depth (ft)', 'Sludge Depth (ft)', 'Effective Depth (ft)', 'Capacity Loss %', 'Status'].map(h => (
                <th key={h} style={tableHeaderStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {zones.map(z => (
              <tr key={z.name} style={{ transition: 'background 0.15s' }}>
                <td style={{ ...tableCellStyle, fontWeight: 600, color: '#1B3A5C' }}>{z.name}</td>
                <td style={{ ...tableCellStyle, textAlign: 'center' }}>{z.totalDepth}</td>
                <td style={{ ...tableCellStyle, textAlign: 'center' }}>{z.sludgeDepth}</td>
                <td style={{ ...tableCellStyle, textAlign: 'center' }}>{z.effectiveDepth.toFixed(1)}</td>
                <td style={{ ...tableCellStyle, textAlign: 'center' }}>{z.capacityLoss.toFixed(1)}%</td>
                <td style={{ ...tableCellStyle, textAlign: 'center' }}>
                  <span style={{
                    ...STATUS_STYLES[z.status],
                    padding: '3px 12px',
                    borderRadius: '9999px',
                    fontSize: '0.78rem',
                    fontWeight: 700,
                    display: 'inline-block',
                  }}>
                    {z.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 3. STACKED BAR CHART */}
      <div className="glass-card" style={{ marginBottom: '28px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '16px' }}>
          Zone Depth Breakdown
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={barData} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} unit=" ft" />
            <Tooltip
              contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', color: '#374151' }}
              cursor={{ fill: 'rgba(0,0,0,0.04)' }}
            />
            <Legend wrapperStyle={{ color: '#64748b', fontSize: '0.82rem' }} />
            <Bar dataKey="Effective Depth" stackId="a" fill="#4472C4" radius={[0, 0, 0, 0]} />
            <Bar dataKey="Sludge Depth"    stackId="a" fill="#e74c3c" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* 4. KPI CARDS */}
      <div className="grid-cols-3" style={{ marginBottom: '28px' }}>
        {/* Avg Capacity Loss */}
        <div className="glass-card" style={{ textAlign: 'center' }}>
          <p style={{ color: '#94a3b8', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '8px' }}>
            Avg Capacity Loss
          </p>
          <p style={{ fontSize: '2.4rem', fontWeight: 700, color: avgColor, margin: '0 0 6px' }}>
            {avgCapacityLoss.toFixed(1)}%
          </p>
          <p style={{ color: '#64748b', fontSize: '0.8rem' }}>Across all monitored zones</p>
        </div>

        {/* Critical Zones */}
        <div className="glass-card" style={{ textAlign: 'center' }}>
          <p style={{ color: '#94a3b8', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '8px' }}>
            Critical Zones
          </p>
          <p style={{ fontSize: '2.4rem', fontWeight: 700, color: criticalCount > 0 ? '#9C0006' : '#006100', margin: '0 0 6px' }}>
            {criticalCount}
          </p>
          <p style={{ color: '#64748b', fontSize: '0.8rem' }}>Capacity loss &gt; 30%</p>
        </div>

        {/* Bio-Digestible Fraction */}
        <div className="glass-card" style={{ textAlign: 'center' }}>
          <p style={{ color: '#94a3b8', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '8px' }}>
            Bio-Digestible Fraction
          </p>
          <p style={{ fontSize: '2.4rem', fontWeight: 700, color: '#006100', margin: '0 0 6px' }}>
            ~66%
          </p>
          <p style={{ color: '#64748b', fontSize: '0.8rem' }}>Treatable with enzyme cocktail</p>
        </div>
      </div>

      {/* 5. SLUDGE COMPOSITION */}
      <div className="glass-card" style={{ marginBottom: '28px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '20px' }}>
          Sludge Composition
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '24px', alignItems: 'flex-start' }}>

          {/* Donut */}
          <div style={{ flex: '0 0 280px', minWidth: '240px' }}>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={PIE_DATA}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  dataKey="value"
                  paddingAngle={2}
                >
                  {PIE_DATA.map(entry => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', color: '#374151' }}
                  formatter={(value) => [`${value}%`, '']}
                />
                <Legend
                  layout="vertical"
                  align="right"
                  verticalAlign="middle"
                  wrapperStyle={{ color: '#64748b', fontSize: '0.78rem', lineHeight: '1.8' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Composition table */}
          <div style={{ flex: '1 1 320px', overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '340px' }}>
              <thead>
                <tr>
                  {['Component', 'Percentage', 'Digestible', 'Treatment'].map(h => (
                    <th key={h} style={tableHeaderStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPOSITION_TABLE.map(row => (
                  <tr key={row.component}>
                    <td style={tableCellStyle}>{row.component}</td>
                    <td style={{ ...tableCellStyle, textAlign: 'center', fontWeight: 600 }}>{row.pct}</td>
                    <td style={{ ...tableCellStyle, textAlign: 'center' }}>
                      <span style={{
                        color: row.digestible === 'YES' ? '#006100' : '#9C0006',
                        fontWeight: 700,
                      }}>
                        {row.digestible}
                      </span>
                    </td>
                    <td style={{ ...tableCellStyle }}>{row.treatment}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

        </div>
      </div>

      {/* 6. INTERNAL NUTRIENT LOADING TABLE */}
      <div className="glass-card" style={{ marginBottom: '28px', overflowX: 'auto' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '4px' }}>
          Internal Nutrient Loading
        </h2>
        <p style={{ color: '#94a3b8', fontSize: '0.82rem', marginBottom: '16px' }}>Risk Assessment</p>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '620px' }}>
          <thead>
            <tr>
              {['Condition', 'Mechanism', 'P Contribution', 'Prevention'].map(h => (
                <th key={h} style={tableHeaderStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {NUTRIENT_LOADING_TABLE.map(row => (
              <tr key={row.condition}>
                <td style={{ ...tableCellStyle, fontWeight: 600, color: '#856404', whiteSpace: 'nowrap' }}>{row.condition}</td>
                <td style={tableCellStyle}>{row.mechanism}</td>
                <td style={{ ...tableCellStyle, color: '#9C0006', fontWeight: 500 }}>{row.contribution}</td>
                <td style={tableCellStyle}>{row.prevention}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 7. INTERNAL LOADING TRAP CALLOUT */}
      <div style={{
        background: '#FFF0F0',
        border: '1px solid #fecaca',
        borderRadius: '12px',
        padding: '20px 24px',
        marginBottom: '8px',
      }}>
        <p style={{ fontWeight: 700, color: '#9C0006', fontSize: '1rem', marginBottom: '8px' }}>
          The Internal Loading Trap
        </p>
        <p style={{ color: '#374151', fontSize: '0.88rem', lineHeight: '1.65', margin: 0 }}>
          Even with zero external nutrient inputs, sludge can feed blooms for years. At 33°C, sediment P
          release accelerates dramatically. Sludge management is not optional — it's a prerequisite for
          long-term control.
        </p>
      </div>

    </div>
  )
}
