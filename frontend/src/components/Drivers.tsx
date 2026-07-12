import React from 'react'
import { PageHeader } from './PageHeader'
import { DriversIntelligence } from './DriversIntelligence'
import { useAuth } from '../context/AuthContext'
import { NoData, SampleBanner } from '../lib/sampleData'
import {
  MONTH_NAMES,
  SOLAR_IRRADIANCE,
  MONTHLY_DATA,
  TEMP_SPECIES_DOMINANCE,
  NUTRIENT_SOURCES,
} from '../constants'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  LineChart,
  Line,
  Cell,
} from 'recharts'

const salinityRows = [
  { waterBody: 'Open Arabian Gulf',      salinity: '39–41',  risk: 'LOW',      significance: 'Reference baseline' },
  { waterBody: 'Bulk Lagoon Water',       salinity: '45–60+', risk: 'HIGH',     significance: 'Evaporative concentration' },
  { waterBody: 'TSE Inflow',             salinity: '1–3',    risk: 'CRITICAL', significance: 'Creates freshwater lens' },
  { waterBody: 'Freshwater Surface Lens', salinity: '1–15',  risk: 'CRITICAL', significance: 'Perfect cyanobacteria incubator' },
  { waterBody: 'Mixing Interface',        salinity: '~18',   risk: 'HIGH',     significance: 'Toxin release zone' },
]

function getRiskColor(risk: string): React.CSSProperties {
  if (risk === 'CRITICAL') return { color: '#9C0006', fontWeight: 700 }
  if (risk === 'HIGH')     return { color: '#856404', fontWeight: 700 }
  if (risk === 'MEDIUM')   return { color: '#856404', fontWeight: 700 }
  if (risk === 'LOW')      return { color: '#006100', fontWeight: 700 }
  if (risk === 'NONE')     return { color: '#9C0006', fontWeight: 700 }
  return {}
}

function getControllabilityColor(val: string): React.CSSProperties {
  if (val === 'HIGH')   return { color: '#006100', fontWeight: 700 }
  if (val === 'MEDIUM') return { color: '#856404', fontWeight: 700 }
  if (val === 'LOW')    return { color: '#856404', fontWeight: 700 }
  if (val === 'NONE')   return { color: '#9C0006', fontWeight: 700 }
  return {}
}

function getCyanoRowStyle(cyano: string, diatom: string): React.CSSProperties {
  if (cyano === 'AT OPTIMUM' || diatom === 'AT OPTIMUM') {
    return { background: '#FFF0F0' }
  }
  if (cyano === 'Near') {
    return { background: '#FFFBEB' }
  }
  return {}
}

function getCellHighlight(val: string): React.CSSProperties {
  if (val === 'AT OPTIMUM') return { color: '#9C0006', fontWeight: 700 }
  if (val === 'Near' || val === 'Near optimum') return { color: '#856404', fontWeight: 600 }
  return {}
}

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
  verticalAlign: 'middle',
}

export const Drivers: React.FC = () => {
  const { showSampleData } = useAuth()

  const solarData = MONTH_NAMES.map((m, i) => ({
    month: m.slice(0, 3),
    value: SOLAR_IRRADIANCE[i],
  }))

  const tempData = MONTH_NAMES.map((m, i) => ({
    month: m.slice(0, 3),
    temp: MONTHLY_DATA.water_temp[i],
  }))

  // The Bloom Pressure Index and both charts are built on the seasonal sample baseline
  // (see Chemistry). The nutrient-source and species-dominance tables below are domain
  // reference material rather than site data, but the page as a whole reads as a site
  // diagnosis — so with sample data off, none of it renders.
  if (!showSampleData) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Environmental Drivers" subtitle="The Four Key Drivers of Algae Dynamics in Dubai Lagoons" />
        <NoData icon="🌡️" title="Driver intelligence runs on the sample baseline" />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      <PageHeader title="Environmental Drivers" subtitle="The Four Key Drivers of Algae Dynamics in Dubai Lagoons" />

      <SampleBanner />

      {/* 0. INTELLIGENCE — Bloom Pressure synthesis of the four drivers */}
      <DriversIntelligence />

      {/* 1. SOLAR RADIATION */}
      <div className="glass-card" style={{ padding: '1.5rem' }}>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '1.25rem' }}>
          Solar Radiation
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={solarData} margin={{ top: 16, right: 24, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="month" tick={{ fill: '#64748b', fontSize: 12 }} />
            <YAxis
              tick={{ fill: '#64748b', fontSize: 12 }}
              domain={[0, 8]}
              label={{ value: 'kWh/m²/day', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11, dy: 50 }}
            />
            <Tooltip
              contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8, color: '#374151' }}
              formatter={(value) => [`${value} kWh/m²/day`, 'Solar Irradiance']}
            />
            <ReferenceLine
              y={6.0}
              stroke="#ef4444"
              strokeDasharray="4 4"
              label={{ value: 'High algae growth risk (6.0)', position: 'right', fill: '#ef4444', fontSize: 11 }}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {solarData.map((entry, index) => (
                <Cell
                  key={`solar-cell-${index}`}
                  fill={entry.value >= 6.5 ? '#f59e0b' : '#4472C4'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        <div style={{
          marginTop: '1.25rem',
          background: '#D6E4F0',
          border: '1px solid #93c5fd',
          borderRadius: 8,
          padding: '1rem 1.25rem',
          color: '#1B3A5C',
          fontSize: '0.875rem',
          lineHeight: 1.6,
        }}>
          UAE receives ~6.0 kWh/m²/day average, ~3,500+ sunshine hours/year. Pre-treat March–April before radiation ramp; maintain May–September.
        </div>
      </div>

      {/* 2. WATER TEMPERATURE & SPECIES DOMINANCE */}
      <div className="glass-card" style={{ padding: '1.5rem' }}>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '1.25rem' }}>
          Water Temperature &amp; Species Dominance
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={tempData} margin={{ top: 16, right: 24, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="month" tick={{ fill: '#64748b', fontSize: 12 }} />
            <YAxis
              tick={{ fill: '#64748b', fontSize: 12 }}
              domain={[15, 38]}
              label={{ value: '°C', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 12, dy: 10 }}
            />
            <Tooltip
              contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8, color: '#374151' }}
              formatter={(value) => [`${value}°C`, 'Water Temperature']}
            />
            <ReferenceLine
              y={30.6}
              stroke="#c0392b"
              strokeDasharray="4 4"
              label={{ value: 'Cyanobacteria optimum (30.6°C)', position: 'right', fill: '#c0392b', fontSize: 10 }}
            />
            <ReferenceLine
              y={25.7}
              stroke="#27ae60"
              strokeDasharray="4 4"
              label={{ value: 'Chlorophyte optimum (25.7°C)', position: 'right', fill: '#27ae60', fontSize: 10 }}
            />
            <ReferenceLine
              y={24.0}
              stroke="#3498db"
              strokeDasharray="4 4"
              label={{ value: 'Diatom optimum (24°C)', position: 'right', fill: '#3498db', fontSize: 10 }}
            />
            <Line
              type="monotone"
              dataKey="temp"
              stroke="#ef4444"
              strokeWidth={2.5}
              dot={{ fill: '#ef4444', r: 4 }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>

        {/* Species dominance table */}
        <div style={{ overflowX: 'auto', marginTop: '1.5rem', borderRadius: 8, border: '1px solid #e2e8f0' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 640 }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                <th style={tableHeaderStyle}>Month</th>
                <th style={tableHeaderStyle}>Temp (°C)</th>
                <th style={tableHeaderStyle}>Cyanobacteria</th>
                <th style={tableHeaderStyle}>Chlorophytes</th>
                <th style={tableHeaderStyle}>Diatoms</th>
                <th style={tableHeaderStyle}>Dominant Group</th>
              </tr>
            </thead>
            <tbody>
              {TEMP_SPECIES_DOMINANCE.map((row, i) => (
                <tr
                  key={i}
                  style={{
                    ...getCyanoRowStyle(row.cyano, row.diatom),
                    transition: 'background 0.15s',
                  }}
                >
                  <td style={tableCellStyle}>{row.month}</td>
                  <td style={{ ...tableCellStyle, fontWeight: 600 }}>{row.temp}</td>
                  <td style={{ ...tableCellStyle, ...getCellHighlight(row.cyano) }}>{row.cyano}</td>
                  <td style={{ ...tableCellStyle, ...getCellHighlight(row.chloro) }}>{row.chloro}</td>
                  <td style={{ ...tableCellStyle, ...getCellHighlight(row.diatom) }}>{row.diatom}</td>
                  <td style={{ ...tableCellStyle, color: '#1B3A5C', fontWeight: 600 }}>{row.dominant}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{
          marginTop: '1.25rem',
          background: '#FFF0F0',
          border: '1px solid #fecaca',
          borderRadius: 8,
          padding: '1rem 1.25rem',
          color: '#374151',
          fontSize: '0.875rem',
          lineHeight: 1.6,
        }}>
          <strong style={{ color: '#9C0006' }}>Key insight:</strong> Dubai summer water (33°C) sits precisely at cyanobacteria's thermal optimum (30.6 ± 2.3°C) while suppressing all competitors.
        </div>
      </div>

      {/* 3. NUTRIENT SOURCES */}
      <div className="glass-card" style={{ padding: '1.5rem' }}>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '1.25rem' }}>
          Nutrient Sources
        </h2>
        <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid #e2e8f0' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 700 }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                <th style={tableHeaderStyle}>Rank</th>
                <th style={tableHeaderStyle}>Source</th>
                <th style={tableHeaderStyle}>Contribution</th>
                <th style={tableHeaderStyle}>Controllability</th>
                <th style={tableHeaderStyle}>Monitoring</th>
                <th style={tableHeaderStyle}>Mechanism</th>
              </tr>
            </thead>
            <tbody>
              {NUTRIENT_SOURCES.map((row, i) => (
                <tr key={i}>
                  <td style={{ ...tableCellStyle, fontWeight: 700, color: '#1B3A5C' }}>{row.rank}</td>
                  <td style={{ ...tableCellStyle, fontWeight: 600 }}>{row.source}</td>
                  <td style={tableCellStyle}>{row.contribution}</td>
                  <td style={{ ...tableCellStyle, ...getControllabilityColor(row.controllability) }}>
                    {row.controllability}
                  </td>
                  <td style={{ ...tableCellStyle, color: '#64748b' }}>{row.monitoring}</td>
                  <td style={{ ...tableCellStyle, color: '#64748b' }}>{row.mechanism}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{
          marginTop: '1.25rem',
          background: '#FFEB9C',
          border: '1px solid #fcd34d',
          borderRadius: 8,
          padding: '1rem 1.25rem',
          color: '#374151',
          fontSize: '0.875rem',
          lineHeight: 1.6,
        }}>
          <strong style={{ color: '#856404' }}>Critical finding:</strong> Unlike most marine basins where agricultural runoff dominates, in Dubai lagoons municipal wastewater effluent (TSE) is the dominant source of anthropogenic N and P.
        </div>
      </div>

      {/* 4. SALINITY & MIXING */}
      <div className="glass-card" style={{ padding: '1.5rem' }}>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '1.25rem' }}>
          Salinity &amp; Mixing
        </h2>
        <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid #e2e8f0' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 560 }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                <th style={tableHeaderStyle}>Water Body</th>
                <th style={tableHeaderStyle}>Salinity (PSU)</th>
                <th style={tableHeaderStyle}>Risk</th>
                <th style={tableHeaderStyle}>Significance</th>
              </tr>
            </thead>
            <tbody>
              {salinityRows.map((row, i) => (
                <tr key={i}>
                  <td style={{ ...tableCellStyle, fontWeight: 600 }}>{row.waterBody}</td>
                  <td style={{ ...tableCellStyle, fontFamily: 'monospace' }}>{row.salinity}</td>
                  <td style={{ ...tableCellStyle, ...getRiskColor(row.risk) }}>{row.risk}</td>
                  <td style={{ ...tableCellStyle, color: '#64748b' }}>{row.significance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{
          marginTop: '1.25rem',
          background: '#FFF0F0',
          border: '1px solid #fecaca',
          borderRadius: 8,
          padding: '1rem 1.25rem',
          color: '#374151',
          fontSize: '0.875rem',
          lineHeight: 1.6,
        }}>
          <strong style={{ color: '#9C0006' }}>Stratification Trap:</strong> Low-salinity TSE floats on dense saline lagoon water &rarr; freshwater lens at surface = perfect cyanobacteria incubator. Continuous aeration/destratification is essential.
        </div>
      </div>
    </div>
  )
}
