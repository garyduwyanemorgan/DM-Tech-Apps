import React from 'react'
import { PageHeader } from './PageHeader'
import { SEASONAL_PHASES, TREATMENT_CALENDAR } from '../constants'

// Phase widths: 3, 2, 4, 3 months out of 12
const PHASE_WIDTHS = ['25%', '16.67%', '33.33%', '25%']

const MONTH_ABBRS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function getRiskStyle(risk: string): React.CSSProperties {
  switch (risk) {
    case 'Low':
      return { background: '#27ae60', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontWeight: 600, whiteSpace: 'nowrap' }
    case 'Rising':
      return { background: '#f59e0b', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontWeight: 600, whiteSpace: 'nowrap' }
    case 'Moderate':
      return { background: '#f59e0b', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontWeight: 600, whiteSpace: 'nowrap' }
    case 'High':
      return { background: '#e67e22', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontWeight: 600, whiteSpace: 'nowrap' }
    case 'HIGH':
      return { background: '#e67e22', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontWeight: 600, whiteSpace: 'nowrap' }
    case 'VERY HIGH':
      return { background: '#ef4444', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontWeight: 600, whiteSpace: 'nowrap' }
    case 'CRITICAL':
      return { background: '#7f1d1d', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontWeight: 700, whiteSpace: 'nowrap' }
    default:
      return { background: '#f1f5f9', color: '#374151', padding: '2px 8px', borderRadius: '4px', whiteSpace: 'nowrap' }
  }
}

function getPhaseColor(phaseName: string): string {
  const found = SEASONAL_PHASES.find(p => phaseName.startsWith(p.name) || p.name.startsWith(phaseName.split(':')[0]))
  return found ? found.color : '#6366f1'
}

// Map phase name in TREATMENT_CALENDAR to SEASONAL_PHASES entry
// Month range string for a phase
function monthRangeLabel(months: number[]): string {
  const abbrs = months.map(m => MONTH_ABBRS[m - 1])
  if (abbrs.length === 1) return abbrs[0]
  return `${abbrs[0]} – ${abbrs[abbrs.length - 1]}`
}

export const Calendar: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <PageHeader title="Seasonal Treatment Calendar" subtitle="Annual Plan — Four-Phase Treatment Cycle" />

      {/* 2. PHASE TIMELINE */}
      <div className="glass-card" style={{ padding: '24px', marginBottom: '28px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '16px' }}>
          Annual Phase Timeline
        </h2>

        {/* Colored phase bar */}
        <div style={{ display: 'flex', width: '100%', borderRadius: '8px', overflow: 'hidden', marginBottom: '8px' }}>
          {SEASONAL_PHASES.map((phase, i) => (
            <div
              key={phase.name}
              style={{
                width: PHASE_WIDTHS[i],
                background: phase.color,
                padding: '12px 8px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                minHeight: '72px',
                boxSizing: 'border-box',
              }}
            >
              <span style={{ fontWeight: 700, fontSize: '0.78rem', color: '#fff', textAlign: 'center', lineHeight: 1.3 }}>
                {phase.name}
              </span>
              <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.85)', textAlign: 'center', marginTop: '4px', lineHeight: 1.3 }}>
                {phase.objective}
              </span>
            </div>
          ))}
        </div>

        {/* Month abbreviation row */}
        <div style={{ display: 'flex', width: '100%' }}>
          {MONTH_ABBRS.map((abbr) => (
            <div
              key={abbr}
              style={{
                flex: '1 1 0',
                textAlign: 'center',
                fontSize: '0.72rem',
                color: '#64748b',
                paddingTop: '4px',
                fontWeight: 500,
              }}
            >
              {abbr}
            </div>
          ))}
        </div>
      </div>

      {/* 3. MONTHLY TREATMENT TABLE */}
      <div className="glass-card" style={{ padding: '24px', marginBottom: '28px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '16px' }}>
          Monthly Treatment Protocol
        </h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '780px' }}>
            <thead>
              <tr>
                {['Month', 'Phase', 'Enzyme Dosing', 'Aeration Level', 'Ultrasound Mode', 'Risk Level'].map(col => (
                  <th
                    key={col}
                    style={{
                      padding: '10px 12px',
                      textAlign: 'left',
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      color: '#64748b',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      whiteSpace: 'nowrap',
                      background: '#f8fafc',
                      borderBottom: '2px solid #e2e8f0',
                    }}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {TREATMENT_CALENDAR.map((row, i) => {
                const phaseColor = getPhaseColor(row.phase)
                return (
                  <tr
                    key={row.month}
                    style={{
                      borderBottom: '1px solid #f1f5f9',
                      background: i % 2 === 0 ? '#fafafa' : 'transparent',
                    }}
                  >
                    <td style={{ padding: '10px 12px', fontWeight: 600, fontSize: '0.85rem', color: '#374151', whiteSpace: 'nowrap' }}>
                      {row.month}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span
                        style={{
                          background: phaseColor,
                          color: '#fff',
                          padding: '2px 10px',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {row.phase}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', fontSize: '0.82rem', color: '#374151' }}>
                      {row.enzyme}
                    </td>
                    <td style={{ padding: '10px 12px', fontSize: '0.82rem', color: '#374151' }}>
                      {row.aeration}
                    </td>
                    <td style={{ padding: '10px 12px', fontSize: '0.82rem', color: '#374151' }}>
                      {row.ultrasound}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={getRiskStyle(row.risk)}>{row.risk}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 4. PHASE SUMMARY CARDS */}
      <div className="glass-card" style={{ padding: '24px', marginBottom: '28px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '16px' }}>
          Phase Summary
        </h2>
        <div className="grid-cols-3" style={{ gap: '16px' }}>
          {SEASONAL_PHASES.map((phase) => (
            <div
              key={phase.name}
              style={{
                borderLeft: `4px solid ${phase.color}`,
                background: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: '0 8px 8px 0',
                padding: '16px 18px',
                display: 'flex',
                flexDirection: 'column',
                gap: '6px',
              }}
            >
              <span
                style={{
                  fontWeight: 700,
                  fontSize: '0.95rem',
                  color: phase.color,
                }}
              >
                {phase.name}
              </span>
              <span style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 500 }}>
                {monthRangeLabel(phase.months)}
              </span>
              <span style={{ fontSize: '0.82rem', color: '#374151', lineHeight: 1.5 }}>
                {phase.objective}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 5. CRITICAL RULE CALLOUT */}
      <div
        style={{
          background: '#FFF0F0',
          border: '1.5px solid #fecaca',
          borderRadius: '10px',
          padding: '20px 24px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '14px',
        }}
      >
        <span style={{ fontSize: '1.4rem', lineHeight: 1, marginTop: '2px' }}>&#9888;</span>
        <div>
          <div style={{ fontWeight: 800, fontSize: '0.95rem', color: '#9C0006', marginBottom: '6px', letterSpacing: '0.03em' }}>
            CRITICAL RULE (Phase 3)
          </div>
          <div style={{ fontSize: '0.88rem', color: '#374151', lineHeight: 1.6 }}>
            NEVER deploy algicide during peak season. A bloom crash releases massive BOD &rarr; DO crash &rarr; worse than managed decline.
          </div>
        </div>
      </div>
    </div>
  )
}
