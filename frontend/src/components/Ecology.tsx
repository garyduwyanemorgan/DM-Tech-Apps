import React, { useState } from 'react'
import { PageHeader } from './PageHeader'
import { EcologyGraph } from './EcologyGraph'
import { MONTH_NAMES, MONTHLY_DATA } from '../constants'
import { analyzeEcology, annualEsi, classifyEsi, stressColor } from '../lib/ecologyIntelligence'
import { useAuth } from '../context/AuthContext'
import { NoData, SampleBanner } from '../lib/sampleData'

const ANNUAL = annualEsi()

const cardBase: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: 12,
  padding: '1rem 1.15rem',
}
const questionLabel: React.CSSProperties = {
  fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8', marginBottom: '0.4rem',
}
const th: React.CSSProperties = {
  padding: '9px 12px', textAlign: 'left', fontSize: '0.72rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
  letterSpacing: '0.04em', borderBottom: '2px solid #e2e8f0', background: '#f8fafc', whiteSpace: 'nowrap',
}
const td: React.CSSProperties = { padding: '9px 12px', fontSize: '0.85rem', color: '#374151', borderBottom: '1px solid #f1f5f9' }

const Gauge: React.FC<{ value: number; color: string; level: string }> = ({ value, color, level }) => {
  const RAD = 54
  const C = 2 * Math.PI * RAD
  const dash = (value / 100) * C
  return (
    <div style={{ position: 'relative', width: 140, height: 140, flexShrink: 0 }}>
      <svg width={140} height={140} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={70} cy={70} r={RAD} fill="none" stroke="#eef2f7" strokeWidth={12} />
        <circle cx={70} cy={70} r={RAD} fill="none" stroke={color} strokeWidth={12} strokeLinecap="round" strokeDasharray={`${dash} ${C}`} style={{ transition: 'stroke-dasharray 0.6s ease, stroke 0.4s ease' }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ fontSize: '2.1rem', fontWeight: 800, color, lineHeight: 1 }}>{Math.round(value)}</div>
        <div style={{ fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.08em', color: '#94a3b8', textTransform: 'uppercase', marginTop: 2 }}>ESI</div>
        <div style={{ fontSize: '0.72rem', fontWeight: 700, color, marginTop: 4 }}>{level}</div>
      </div>
    </div>
  )
}

const trendGlyph = (t: string) => (t === 'rising' ? '▲' : t === 'falling' ? '▼' : '▬')

// biological indicators for the supporting table (reference thresholds, not all formal limits)
const INDICATORS: { key: keyof typeof MONTHLY_DATA; label: string; unit: string; threshold: number; note: string }[] = [
  { key: 'chla', label: 'Chlorophyll-a', unit: 'µg/L', threshold: 30, note: '> 30 = bloom warning' },
  { key: 'phycocyanin', label: 'Phycocyanin', unit: 'µg/L', threshold: 200, note: '> 200 = cyano warning' },
  { key: 'ecoli', label: 'E. coli', unit: 'CFU/100mL', threshold: 200, note: '< 200 limit' },
  { key: 'coliforms', label: 'Total Coliforms', unit: 'CFU/100mL', threshold: 1000, note: '< 1000 limit' },
  { key: 'do', label: 'Dissolved Oxygen', unit: 'mg/L', threshold: 4, note: '> 4 (fish floor)' },
]

export const Ecology: React.FC = () => {
  const { showSampleData } = useAuth()
  const [month, setMonth] = useState<number>(new Date().getMonth())
  const intel = analyzeEcology(month)
  const maxContribution = Math.max(...intel.processes.map((p) => p.contribution))

  // Ecological Stress Index is derived from the seasonal sample baseline (see Chemistry).
  if (!showSampleData) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Ecology" subtitle="The Ecology Loop — the lagoon's biological response as one living system" />
        <NoData icon="🌿" title="Ecology intelligence runs on the sample baseline" />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      <PageHeader title="Ecology" subtitle="The Ecology Loop — the lagoon's biological response as one living system" />

      <SampleBanner />

      <div className="glass-card" style={{ padding: '1.5rem' }}>
        <div style={{ marginBottom: '1rem' }}>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1B3A5C', marginBottom: 2 }}>Ecological Stress Intelligence</h2>
          <p style={{ fontSize: '0.8rem', color: '#64748b' }}>
            Eight biological processes fused into one signal — what’s changing, why, what’s next, and what to do.
          </p>
        </div>

        {/* month chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: '1.25rem' }}>
          {MONTH_NAMES.map((m, i) => {
            const active = i === intel.monthIndex
            const st = classifyEsi(ANNUAL[i])
            return (
              <button key={m} onClick={() => setMonth(i)} title={`${m} · ESI ${Math.round(ANNUAL[i])} (${st.level})`}
                style={{
                  cursor: 'pointer', fontSize: '0.72rem', fontWeight: active ? 700 : 500, padding: '5px 10px', borderRadius: 8,
                  border: active ? `1.5px solid ${st.color}` : '1px solid #e2e8f0', background: active ? st.bg : '#ffffff',
                  color: active ? st.color : '#64748b', display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s',
                }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: st.color, display: 'inline-block' }} />
                {m.slice(0, 3)}
              </button>
            )
          })}
        </div>

        {/* HERO graph */}
        <div style={{ marginBottom: '1.25rem' }}>
          <EcologyGraph intel={intel} />
        </div>

        {/* gauge + four questions */}
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) 2fr', gap: '1.25rem', alignItems: 'stretch' }}>
          <div style={{ ...cardBase, background: intel.state.bg, border: `1px solid ${intel.state.border}`, display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <Gauge value={intel.esi} color={intel.state.color} level={intel.state.level} />
            <div>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8' }}>{intel.monthName}</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, color: intel.state.color, lineHeight: 1.15 }}>{intel.state.level}</div>
              <div style={{ fontSize: '0.8rem', color: '#475569', marginTop: 4, fontWeight: 600 }}>
                {trendGlyph(intel.trend)} {intel.trend}
                {intel.delta !== 0 && <span style={{ color: '#94a3b8', fontWeight: 500 }}> ({intel.delta > 0 ? '+' : ''}{intel.delta} vs prev)</span>}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div style={cardBase}><div style={questionLabel}>What is changing</div><div style={{ fontSize: '0.85rem', color: '#334155', lineHeight: 1.5 }}>{intel.headline}</div></div>
            <div style={cardBase}><div style={questionLabel}>Why · root cause</div><div style={{ fontSize: '0.85rem', color: '#334155', lineHeight: 1.5 }}>{intel.cause}</div></div>
            <div style={cardBase}><div style={questionLabel}>What happens next</div><div style={{ fontSize: '0.85rem', color: '#334155', lineHeight: 1.5 }}>{intel.outlook}</div></div>
            <div style={{ ...cardBase, background: '#F8FAFC' }}><div style={questionLabel}>Priority</div><div style={{ fontSize: '0.95rem', color: intel.state.color, fontWeight: 700, lineHeight: 1.4 }}>{intel.action.priority}</div></div>
          </div>
        </div>

        {/* process contribution bars */}
        <div style={{ ...cardBase, marginTop: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.9rem' }}>
            <div style={questionLabel}>Process contribution to ecological stress</div>
            <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>stress × weight</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {intel.processes.map((p) => {
              const isRoot = p.key === intel.dominant.key
              return (
                <div key={p.key} style={{ display: 'grid', gridTemplateColumns: '190px 1fr auto', gap: '0.75rem', alignItems: 'center' }}>
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#334155', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ width: 9, height: 9, borderRadius: '50%', background: stressColor(p.stress), display: 'inline-block' }} />
                      {p.label}
                      {p.modelled && <span style={{ fontSize: '0.58rem', color: '#94a3b8', border: '1px solid #e2e8f0', borderRadius: 4, padding: '0 4px' }}>modelled</span>}
                      {isRoot && <span style={{ fontSize: '0.6rem', fontWeight: 700, color: '#9C0006', background: '#FFF0F0', border: '1px solid #fecaca', borderRadius: 4, padding: '1px 5px' }}>ROOT CAUSE</span>}
                    </span>
                    <span style={{ fontSize: '0.72rem', color: '#94a3b8', fontFamily: 'monospace' }}>{p.value}</span>
                  </div>
                  <div style={{ position: 'relative', height: 20, background: '#f1f5f9', borderRadius: 6, overflow: 'hidden' }}>
                    <div style={{ position: 'absolute', inset: 0, width: `${p.stress}%`, background: stressColor(p.stress), opacity: 0.85, borderRadius: 6, transition: 'width 0.5s ease', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 8 }}>
                      <span style={{ fontSize: '0.66rem', fontWeight: 700, color: '#fff' }}>{Math.round(p.stress)}</span>
                    </div>
                  </div>
                  <div style={{ minWidth: 84, textAlign: 'right' }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 700, color: p.contribution === maxContribution ? stressColor(p.stress) : '#64748b' }}>+{p.contribution.toFixed(1)}</span>
                    <span style={{ fontSize: '0.68rem', color: '#cbd5e1' }}> pts</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* trajectory + action */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: '1.25rem', marginTop: '1.25rem' }}>
          <div style={cardBase}>
            <div style={questionLabel}>Trajectory · prev → +2 months</div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.6rem', height: 120, marginTop: '0.5rem' }}>
              {intel.trajectory.map((pt) => (
                <div key={pt.monthIndex} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: '0.7rem', fontWeight: 700, color: pt.state.color }}>{Math.round(pt.esi)}</span>
                  <div style={{ width: '100%', height: `${Math.max(6, pt.esi)}%`, background: pt.state.color, opacity: pt.kind === 'current' ? 1 : pt.kind === 'forecast' ? 0.45 : 0.7, borderRadius: '6px 6px 0 0', border: pt.kind === 'current' ? `2px solid ${pt.state.color}` : 'none', transition: 'height 0.5s ease' }} />
                  <span style={{ fontSize: '0.68rem', color: pt.kind === 'current' ? '#1B3A5C' : '#94a3b8', fontWeight: pt.kind === 'current' ? 700 : 500 }}>{pt.monthName.slice(0, 3)}</span>
                  <span style={{ fontSize: '0.58rem', color: '#cbd5e1', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{pt.kind === 'forecast' ? 'fcst' : pt.kind === 'current' ? 'now' : 'past'}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={{ ...cardBase, background: intel.state.bg, border: `1px solid ${intel.state.border}` }}>
            <div style={questionLabel}>Recommended operational response</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', margin: '0.35rem 0 0.75rem' }}>
              {intel.action.enzyme && <span style={{ fontSize: '0.72rem', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 6, padding: '3px 8px', color: '#475569' }}><strong style={{ color: '#1B3A5C' }}>Enzyme:</strong> {intel.action.enzyme}</span>}
              {intel.action.ultrasound && <span style={{ fontSize: '0.72rem', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 6, padding: '3px 8px', color: '#475569' }}><strong style={{ color: '#1B3A5C' }}>Ultrasound:</strong> {intel.action.ultrasound}</span>}
            </div>
            <ol style={{ margin: 0, paddingLeft: '1.1rem', display: 'flex', flexDirection: 'column', gap: 5 }}>
              {intel.action.steps.map((s, i) => (<li key={i} style={{ fontSize: '0.82rem', color: '#334155', lineHeight: 1.45 }}>{s}</li>))}
            </ol>
          </div>
        </div>
      </div>

      {/* supporting biological indicator table */}
      <div className="glass-card" style={{ padding: '1.5rem' }}>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '1rem' }}>
          {intel.monthName} — Biological Indicators
        </h2>
        <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid #e2e8f0' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 560 }}>
            <thead>
              <tr>
                <th style={th}>Indicator</th>
                <th style={th}>Reading</th>
                <th style={th}>Reference</th>
                <th style={th}>Unit</th>
                <th style={th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {INDICATORS.map((ind) => {
                const val = MONTHLY_DATA[ind.key][intel.monthIndex]
                // DO is a floor (low = bad); everything else is a ceiling (high = bad)
                const breach = ind.key === 'do' ? val < ind.threshold : val > ind.threshold
                return (
                  <tr key={ind.key}>
                    <td style={{ ...td, fontWeight: 600 }}>{ind.label}</td>
                    <td style={{ ...td, fontFamily: 'monospace', fontWeight: 700, color: breach ? '#9C0006' : '#15803d' }}>{val}</td>
                    <td style={{ ...td, color: '#64748b' }}>{ind.note}</td>
                    <td style={{ ...td, color: '#94a3b8' }}>{ind.unit}</td>
                    <td style={td}>
                      <span style={{ fontSize: '0.72rem', fontWeight: 700, color: breach ? '#9C0006' : '#15803d', background: breach ? '#FFF0F0' : '#F0FDF4', border: `1px solid ${breach ? '#fecaca' : '#bbf7d0'}`, borderRadius: 5, padding: '2px 8px' }}>
                        {breach ? 'ALERT' : 'OK'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.85rem', lineHeight: 1.5 }}>
          Biofilms and aquatic plants have no direct laboratory value — they are modelled from temperature, organic load
          and turbidity, and appear in the graph with a dashed identity ring.
        </div>
      </div>
    </div>
  )
}
