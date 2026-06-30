import React from 'react'
import { ALERT_COLORS, ALERT_LABELS, ALERT_THRESHOLDS, TREATMENT_ACTIONS } from '../constants'
import { PageHeader } from './PageHeader'

const levels = [1, 2, 3, 4] as const

const TH: React.CSSProperties = {
  padding: '10px 14px',
  textAlign: 'left',
  fontSize: '0.78rem',
  fontWeight: 700,
  color: '#64748b',
  background: '#f8fafc',
  borderBottom: '2px solid #e2e8f0',
  whiteSpace: 'nowrap',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
}

const TD: React.CSSProperties = {
  padding: '10px 14px',
  fontSize: '0.875rem',
  color: '#374151',
  borderBottom: '1px solid #f1f5f9',
  verticalAlign: 'top',
}

export const Alerts: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <PageHeader
        title="Alert & Response Protocol"
        subtitle="Operations Guide — Decision Matrix & Treatment Actions"
        icon="🚨"
      />

      {/* Alert Level Decision Matrix */}
      <div className="glass-card">
        <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Alert Level Decision Matrix</h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '700px', fontSize: '0.875rem' }}>
            <thead>
              <tr>
                {['Alert Level', 'Bloom Prob.', 'Chl-a', 'DO', 'Phycocyanin', 'Temp'].map(col => (
                  <th key={col} style={TH}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {levels.map(level => {
                const t = ALERT_THRESHOLDS[level]
                const color = ALERT_COLORS[level]
                return (
                  <tr key={level}>
                    <td style={{ ...TD, padding: '8px 14px' }}>
                      <span style={{
                        display: 'inline-block',
                        background: color,
                        color: '#fff',
                        fontWeight: 700,
                        fontSize: '0.78rem',
                        borderRadius: '5px',
                        padding: '4px 10px',
                        whiteSpace: 'nowrap',
                      }}>
                        {ALERT_LABELS[level]}
                      </span>
                    </td>
                    <td style={TD}>{t.bloomRange}</td>
                    <td style={TD}>{t.chla}</td>
                    <td style={TD}>{t.doVal}</td>
                    <td style={TD}>{t.phyco}</td>
                    <td style={TD}>{t.temp}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Treatment Actions by Alert Level */}
      <div>
        <h2 style={{ fontSize: '1.1rem', color: '#1B3A5C', marginBottom: '1rem' }}>Treatment Actions by Alert Level</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {levels.map(level => {
            const actions = TREATMENT_ACTIONS[level]
            const color = ALERT_COLORS[level]
            const label = ALERT_LABELS[level]
            const rows = [
              { label: 'Enzymes',    value: actions.enzyme },
              { label: 'Aeration',   value: actions.aeration },
              { label: 'Ultrasound', value: actions.ultrasound },
              { label: 'Monitoring', value: actions.monitoring },
            ]
            return (
              <div key={level} className="glass-card" style={{ borderLeft: `4px solid ${color}`, padding: '1.25rem 1.5rem' }}>
                <h3 style={{ margin: '0 0 0.85rem 0', color, fontWeight: 700, fontSize: '1rem' }}>{label}</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                  <tbody>
                    {rows.map(row => (
                      <tr key={row.label} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '7px 12px 7px 0', color: '#64748b', fontWeight: 600, whiteSpace: 'nowrap', width: '120px' }}>
                          {row.label}
                        </td>
                        <td style={{ padding: '7px 0', color: '#374151' }}>{row.value}</td>
                      </tr>
                    ))}
                    {actions.doNot !== '—' && (
                      <tr>
                        <td colSpan={2} style={{ padding: '10px 0 0' }}>
                          <div style={{
                            background: '#FFC7CE',
                            border: '1px solid #f87171',
                            borderRadius: '6px',
                            padding: '8px 12px',
                            color: '#9C0006',
                            fontWeight: 700,
                            fontSize: '0.875rem',
                          }}>
                            {String.fromCodePoint(0x26D4)} {actions.doNot}
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )
          })}
        </div>
      </div>

      {/* Escalation Rules */}
      <div>
        <h2 style={{ fontSize: '1.1rem', color: '#1B3A5C', marginBottom: '1rem' }}>Escalation Rules</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.25rem' }}>
          <div className="glass-card" style={{ flex: '1 1 280px', borderLeft: '4px solid #ef4444' }}>
            <h3 style={{ marginBottom: '0.85rem', color: '#9C0006' }}>Fast Escalation</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              {[
                'Chl-a doubles in 48h → Level 3 minimum (emergency protocol)',
                'DO < 2 mg/L at any time → Level 4 regardless of Chl-a',
                'Phycocyanin > 200 µg/L → Level 3 minimum (cyano emergency)',
              ].map((text, i) => (
                <div key={i} style={{ background: '#FFF0F0', border: '1px solid #fecaca', borderRadius: '6px', padding: '8px 12px', color: '#9C0006', fontSize: '0.875rem', lineHeight: 1.5 }}>
                  {text}
                </div>
              ))}
            </div>
          </div>

          <div className="glass-card" style={{ flex: '1 1 280px', borderLeft: '4px solid #16a34a' }}>
            <h3 style={{ marginBottom: '0.85rem', color: '#006100' }}>De-escalation (Slow)</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              {[
                'Level 4 → 3: DO > 3 AND Chl-a declining for 7 days AND no toxin',
                'Level 3 → 2: All params below threshold for 14 consecutive days',
                'Level 2 → 1: Weekly samples compliant for 4 consecutive weeks',
              ].map((text, i) => (
                <div key={i} style={{ background: '#C6EFCE', border: '1px solid #86efac', borderRadius: '6px', padding: '8px 12px', color: '#006100', fontSize: '0.875rem', lineHeight: 1.5 }}>
                  {text}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{ marginTop: '1rem', background: '#D6E4F0', border: '1px solid #93c5fd', borderRadius: '8px', padding: '12px 16px', color: '#1B3A5C', fontSize: '0.9rem', lineHeight: 1.6 }}>
          <strong>Design Principle:</strong> De-escalation is always slower than escalation — prevents costly oscillating treatment cycles.
        </div>
      </div>
    </div>
  )
}
