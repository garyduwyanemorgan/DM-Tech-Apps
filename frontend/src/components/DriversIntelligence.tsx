import React, { useState } from 'react'
import { MONTH_NAMES } from '../constants'
import { analyzeMonth, annualBpi, classifyBpi } from '../lib/driversIntelligence'
import { DriversGraph } from './DriversGraph'

const ANNUAL = annualBpi()

const cardBase: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: 12,
  padding: '1rem 1.15rem',
}

const questionLabel: React.CSSProperties = {
  fontSize: '0.7rem',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: '#94a3b8',
  marginBottom: '0.4rem',
}

// ── Circular Bloom Pressure gauge ────────────────────────────────────────────
const Gauge: React.FC<{ bpi: number; color: string; level: string }> = ({ bpi, color, level }) => {
  const R = 54
  const C = 2 * Math.PI * R
  const dash = (bpi / 100) * C
  return (
    <div style={{ position: 'relative', width: 140, height: 140, flexShrink: 0 }}>
      <svg width={140} height={140} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={70} cy={70} r={R} fill="none" stroke="#eef2f7" strokeWidth={12} />
        <circle
          cx={70}
          cy={70}
          r={R}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${C}`}
          style={{ transition: 'stroke-dasharray 0.6s ease, stroke 0.4s ease' }}
        />
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div style={{ fontSize: '2.1rem', fontWeight: 800, color, lineHeight: 1 }}>{Math.round(bpi)}</div>
        <div style={{ fontSize: '0.62rem', fontWeight: 700, letterSpacing: '0.08em', color: '#94a3b8', textTransform: 'uppercase', marginTop: 2 }}>
          BPI
        </div>
        <div style={{ fontSize: '0.72rem', fontWeight: 700, color, marginTop: 4 }}>{level}</div>
      </div>
    </div>
  )
}

const trendGlyph = (t: string) => (t === 'rising' ? '▲' : t === 'falling' ? '▼' : '▬')

export const DriversIntelligence: React.FC = () => {
  const [month, setMonth] = useState<number>(new Date().getMonth())
  const intel = analyzeMonth(month)
  const maxContribution = Math.max(...intel.drivers.map((d) => d.contribution))

  return (
    <div className="glass-card" style={{ padding: '1.5rem' }}>
      {/* Header + month selector */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#1B3A5C', marginBottom: 2 }}>
            Bloom Pressure Intelligence
          </h2>
          <p style={{ fontSize: '0.8rem', color: '#64748b' }}>
            The four drivers fused into one signal — what’s changing, why, what’s next, and what to do.
          </p>
        </div>
      </div>

      {/* Month chips */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: '1.25rem' }}>
        {MONTH_NAMES.map((m, i) => {
          const active = i === intel.monthIndex
          const st = classifyBpi(ANNUAL[i])
          return (
            <button
              key={m}
              onClick={() => setMonth(i)}
              title={`${m} · BPI ${Math.round(ANNUAL[i])} (${st.level})`}
              style={{
                cursor: 'pointer',
                fontSize: '0.72rem',
                fontWeight: active ? 700 : 500,
                padding: '5px 10px',
                borderRadius: 8,
                border: active ? `1.5px solid ${st.color}` : '1px solid #e2e8f0',
                background: active ? st.bg : '#ffffff',
                color: active ? st.color : '#64748b',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                transition: 'all 0.15s',
              }}
            >
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: st.color, display: 'inline-block' }} />
              {m.slice(0, 3)}
            </button>
          )
        })}
      </div>

      {/* HERO: Obsidian-style systems graph */}
      <div style={{ marginBottom: '1.25rem' }}>
        <DriversGraph intel={intel} />
      </div>

      {/* Top: gauge + four questions */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) 2fr', gap: '1.25rem', alignItems: 'stretch' }}>
        {/* Gauge card */}
        <div style={{ ...cardBase, background: intel.state.bg, border: `1px solid ${intel.state.border}`, display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <Gauge bpi={intel.bpi} color={intel.state.color} level={intel.state.level} />
          <div>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8' }}>
              {intel.monthName}
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 800, color: intel.state.color, lineHeight: 1.15 }}>
              {intel.state.level}
            </div>
            <div style={{ fontSize: '0.8rem', color: '#475569', marginTop: 4, fontWeight: 600 }}>
              {trendGlyph(intel.trend)} {intel.trend}
              {intel.delta !== 0 && (
                <span style={{ color: '#94a3b8', fontWeight: 500 }}>
                  {' '}
                  ({intel.delta > 0 ? '+' : ''}
                  {intel.delta} vs prev)
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Four questions */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
          <div style={cardBase}>
            <div style={questionLabel}>What is changing</div>
            <div style={{ fontSize: '0.85rem', color: '#334155', lineHeight: 1.5 }}>{intel.headline}</div>
          </div>
          <div style={cardBase}>
            <div style={questionLabel}>Why · root cause</div>
            <div style={{ fontSize: '0.85rem', color: '#334155', lineHeight: 1.5 }}>{intel.cause}</div>
          </div>
          <div style={cardBase}>
            <div style={questionLabel}>What happens next</div>
            <div style={{ fontSize: '0.85rem', color: '#334155', lineHeight: 1.5 }}>{intel.outlook}</div>
          </div>
          <div style={{ ...cardBase, background: '#F8FAFC' }}>
            <div style={questionLabel}>Priority</div>
            <div style={{ fontSize: '0.95rem', color: intel.state.color, fontWeight: 700, lineHeight: 1.4 }}>
              {intel.action.priority}
            </div>
          </div>
        </div>
      </div>

      {/* Driver contribution bars */}
      <div style={{ ...cardBase, marginTop: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.9rem' }}>
          <div style={questionLabel}>Driver contribution to bloom pressure</div>
          <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>score × weight</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.7rem' }}>
          {intel.drivers.map((d) => {
            const isRoot = d.key === intel.dominant.key
            const isBrake = d.key === intel.limiting.key
            return (
              <div key={d.key} style={{ display: 'grid', gridTemplateColumns: '180px 1fr auto', gap: '0.75rem', alignItems: 'center' }}>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#334155', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 3, background: d.color, display: 'inline-block' }} />
                    {d.label}
                    {isRoot && (
                      <span style={{ fontSize: '0.6rem', fontWeight: 700, color: '#9C0006', background: '#FFF0F0', border: '1px solid #fecaca', borderRadius: 4, padding: '1px 5px' }}>
                        ROOT CAUSE
                      </span>
                    )}
                    {isBrake && !isRoot && (
                      <span style={{ fontSize: '0.6rem', fontWeight: 700, color: '#15803d', background: '#F0FDF4', border: '1px solid #bbf7d0', borderRadius: 4, padding: '1px 5px' }}>
                        BRAKE
                      </span>
                    )}
                  </span>
                  <span style={{ fontSize: '0.72rem', color: '#94a3b8', fontFamily: 'monospace' }}>{d.value}</span>
                </div>

                {/* bar: full width = score 0-100, filled portion tinted by identity */}
                <div style={{ position: 'relative', height: 22, background: '#f1f5f9', borderRadius: 6, overflow: 'hidden' }}>
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      width: `${d.score}%`,
                      background: d.color,
                      opacity: 0.85,
                      borderRadius: 6,
                      transition: 'width 0.5s ease',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'flex-end',
                      paddingRight: 8,
                    }}
                  >
                    <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#fff' }}>{Math.round(d.score)}</span>
                  </div>
                </div>

                <div style={{ minWidth: 96, textAlign: 'right' }}>
                  <span
                    style={{
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      color: d.contribution === maxContribution ? d.color : '#64748b',
                    }}
                  >
                    +{d.contribution.toFixed(1)}
                  </span>
                  <span style={{ fontSize: '0.68rem', color: '#cbd5e1' }}> pts</span>
                </div>
              </div>
            )
          })}
        </div>
        <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.85rem', lineHeight: 1.5 }}>
          Bars show each driver’s favourability (0–100) to a cyanobacteria bloom. Weighted contributions sum to the
          Bloom Pressure Index. Temperature and nutrients carry the most weight (0.30 each); solar and stratification 0.20.
        </div>
      </div>

      {/* Trajectory + recommended action */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: '1.25rem', marginTop: '1.25rem' }}>
        {/* Trajectory */}
        <div style={cardBase}>
          <div style={questionLabel}>Trajectory · prev → +2 months</div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.6rem', height: 120, marginTop: '0.5rem' }}>
            {intel.trajectory.map((pt) => (
              <div key={pt.monthIndex} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: '0.7rem', fontWeight: 700, color: pt.state.color }}>{Math.round(pt.bpi)}</span>
                <div
                  style={{
                    width: '100%',
                    height: `${Math.max(6, pt.bpi)}%`,
                    background: pt.state.color,
                    opacity: pt.kind === 'current' ? 1 : pt.kind === 'forecast' ? 0.45 : 0.7,
                    borderRadius: '6px 6px 0 0',
                    border: pt.kind === 'current' ? `2px solid ${pt.state.color}` : 'none',
                    transition: 'height 0.5s ease',
                  }}
                />
                <span style={{ fontSize: '0.68rem', color: pt.kind === 'current' ? '#1B3A5C' : '#94a3b8', fontWeight: pt.kind === 'current' ? 700 : 500 }}>
                  {pt.monthName.slice(0, 3)}
                </span>
                <span style={{ fontSize: '0.58rem', color: '#cbd5e1', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  {pt.kind === 'forecast' ? 'fcst' : pt.kind === 'current' ? 'now' : 'past'}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Recommended action */}
        <div style={{ ...cardBase, background: intel.state.bg, border: `1px solid ${intel.state.border}` }}>
          <div style={questionLabel}>Recommended operational response</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', margin: '0.35rem 0 0.75rem' }}>
            {intel.action.enzyme && (
              <span style={{ fontSize: '0.72rem', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 6, padding: '3px 8px', color: '#475569' }}>
                <strong style={{ color: '#1B3A5C' }}>Enzyme:</strong> {intel.action.enzyme}
              </span>
            )}
            {intel.action.aeration && (
              <span style={{ fontSize: '0.72rem', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 6, padding: '3px 8px', color: '#475569' }}>
                <strong style={{ color: '#1B3A5C' }}>Aeration:</strong> {intel.action.aeration}
              </span>
            )}
          </div>
          <ol style={{ margin: 0, paddingLeft: '1.1rem', display: 'flex', flexDirection: 'column', gap: 5 }}>
            {intel.action.steps.map((s, i) => (
              <li key={i} style={{ fontSize: '0.82rem', color: '#334155', lineHeight: 1.45 }}>
                {s}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  )
}
