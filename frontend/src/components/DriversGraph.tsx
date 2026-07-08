import React, { useState } from 'react'
import { TEMP_SPECIES_DOMINANCE } from '../constants'
import type { MonthIntelligence } from '../lib/driversIntelligence'

// ─────────────────────────────────────────────────────────────────────────────
// Environmental Drivers — Obsidian-style systems graph.
//
// Drivers (left) → Bloom Pressure hub (centre) → live outcome/event nodes (right).
// Deterministic radial layout on a dark canvas so the colours pop. No physics
// library — SVG + CSS only. Fill = health colour, outer ring = identity colour,
// edges carry animated "flowing particles" showing direction of influence.
// ─────────────────────────────────────────────────────────────────────────────

const W = 840
const H = 480
const HUB = { x: 420, y: 240 }

// score (0–100) → health colour (green → red)
function healthColor(score: number): string {
  if (score >= 80) return '#ef4444'
  if (score >= 60) return '#f97316'
  if (score >= 40) return '#eab308'
  if (score >= 20) return '#38bdf8'
  return '#22c55e'
}

function speciesColor(dominant: string): string {
  const d = dominant.toLowerCase()
  if (d.includes('cyano')) return '#ef4444'
  if (d.includes('diatom')) return '#38bdf8'
  if (d.includes('chloro')) return '#22c55e'
  return '#94a3b8'
}

interface GNode {
  id: string
  x: number
  y: number
  r: number
  fill: string // health colour
  ring: string // identity / loop colour
  label: string
  sub?: string
  pulse?: boolean
  active?: boolean
}

interface GEdge {
  id: string
  from: { x: number; y: number }
  to: { x: number; y: number }
  color: string
  width: number
  opacity: number
  speed: number
  connects: [string, string]
}

export const DriversGraph: React.FC<{ intel: MonthIntelligence }> = ({ intel }) => {
  const [hover, setHover] = useState<string | null>(null)

  const byKey = (k: string) => intel.drivers.find((d) => d.key === k)!
  const species = TEMP_SPECIES_DOMINANCE[intel.monthIndex]?.dominant ?? '—'

  // ── driver nodes (left fan) ────────────────────────────────────────────────
  const driverY = [88, 190, 292, 394]
  const driverNodes: GNode[] = intel.drivers.map((d, i) => ({
    id: d.key,
    x: 150,
    y: driverY[i],
    r: 20 + (d.contribution / 27) * 18, // sized by weighted contribution
    fill: healthColor(d.score),
    ring: d.color,
    label: d.label,
    sub: `${Math.round(d.score)} · ${d.value}`,
    active: true,
  }))

  // ── hub node (centre) ──────────────────────────────────────────────────────
  const hubNode: GNode = {
    id: 'hub',
    x: HUB.x,
    y: HUB.y,
    r: 34 + (intel.bpi / 100) * 26,
    fill: intel.state.color,
    ring: '#ffffff',
    label: 'Bloom Pressure',
    sub: `BPI ${intel.bpi} · ${intel.state.level}`,
    pulse: intel.bpi >= 60,
    active: true,
  }

  // ── outcome / event nodes (right, appear when triggered) ────────────────────
  const strat = byKey('stratification').score
  const nut = byKey('nutrients').score
  const temp = byKey('temperature').score

  const outcomes: { id: string; label: string; color: string; pulse?: boolean }[] = [
    { id: 'species', label: `Dominant: ${species}`, color: speciesColor(species) },
  ]
  if (intel.bpi >= 60) outcomes.push({ id: 'bloom', label: 'Cyanobacteria Bloom Risk', color: '#dc2626', pulse: true })
  if (strat >= 55) outcomes.push({ id: 'lens', label: 'Freshwater Lens', color: '#38bdf8' })
  if (nut >= 50 && temp >= 60) outcomes.push({ id: 'anoxia', label: 'Low Bottom DO', color: '#a855f7' })

  const oY =
    outcomes.length === 1
      ? [240]
      : outcomes.length === 2
      ? [160, 320]
      : outcomes.length === 3
      ? [130, 240, 350]
      : [96, 192, 288, 384]
  const outcomeNodes: GNode[] = outcomes.map((o, i) => ({
    id: o.id,
    x: 700,
    y: oY[i],
    r: 24,
    fill: o.color,
    ring: o.color,
    label: o.label,
    pulse: o.pulse,
    active: true,
  }))

  // ── edges ──────────────────────────────────────────────────────────────────
  const edges: GEdge[] = [
    ...driverNodes.map((n, i) => {
      const d = intel.drivers[i]
      return {
        id: `e-${n.id}`,
        from: { x: n.x, y: n.y },
        to: { x: hubNode.x, y: hubNode.y },
        color: d.color,
        width: 1.5 + d.contribution / 2.5,
        opacity: Math.max(0.3, d.score / 100),
        speed: 2.4 - d.score / 100, // hotter driver = faster flow
        connects: [n.id, 'hub'] as [string, string],
      }
    }),
    ...outcomeNodes.map((n) => ({
      id: `e-${n.id}`,
      from: { x: hubNode.x, y: hubNode.y },
      to: { x: n.x, y: n.y },
      color: n.fill,
      width: 3,
      opacity: 0.85,
      speed: 1.6,
      connects: ['hub', n.id] as [string, string],
    })),
  ]

  const allNodes = [...driverNodes, hubNode, ...outcomeNodes]

  const isDim = (ids: string[]) => hover !== null && !ids.some((id) => id === hover)
  const nodeDim = (id: string) => {
    if (hover === null) return false
    if (id === hover) return false
    // connected if an edge links hover and id
    return !edges.some((e) => (e.connects.includes(hover) && e.connects.includes(id)))
  }

  const curve = (e: GEdge) => {
    const mx = (e.from.x + e.to.x) / 2
    const my = (e.from.y + e.to.y) / 2
    // pull control point toward vertical centre for an organic bend
    const cx = mx
    const cy = my + (e.from.x < HUB.x ? -28 : 28)
    return `M ${e.from.x} ${e.from.y} Q ${cx} ${cy} ${e.to.x} ${e.to.y}`
  }

  return (
    <div
      style={{
        position: 'relative',
        borderRadius: 16,
        overflow: 'hidden',
        background: 'radial-gradient(circle at 42% 45%, #16233b 0%, #0b1220 70%)',
        border: '1px solid #1e293b',
        boxShadow: 'inset 0 0 80px rgba(0,0,0,0.4)',
      }}
    >
      <style>{`
        @keyframes fahFlow { to { stroke-dashoffset: -60; } }
        @keyframes fahPulse { 0%,100% { opacity: .25; } 50% { opacity: .7; } }
        @keyframes fahFloat { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
        .fah-flow { stroke-dasharray: 1.5 9; animation: fahFlow linear infinite; }
        .fah-float { animation: fahFloat ease-in-out infinite; }
      `}</style>

      {/* legend */}
      <div style={{ position: 'absolute', top: 12, left: 14, display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: '0.68rem', color: '#94a3b8', zIndex: 2 }}>
        <span><span style={{ color: '#ef4444' }}>●</span> Temperature</span>
        <span><span style={{ color: '#f59e0b' }}>●</span> Nutrients</span>
        <span><span style={{ color: '#eab308' }}>●</span> Solar</span>
        <span><span style={{ color: '#3b82f6' }}>●</span> Stratification</span>
      </div>
      <div style={{ position: 'absolute', top: 12, right: 16, fontSize: '0.68rem', color: '#64748b', zIndex: 2 }}>
        ring = driver identity · fill = health · flow = influence
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }} preserveAspectRatio="xMidYMid meet">
        <defs>
          <filter id="fah-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="6" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* edges */}
        {edges.map((e) => {
          const dim = isDim(e.connects)
          const d = curve(e)
          return (
            <g key={e.id} style={{ opacity: dim ? 0.08 : 1, transition: 'opacity 0.25s' }}>
              <path d={d} fill="none" stroke={e.color} strokeWidth={e.width} strokeOpacity={e.opacity * 0.35} />
              <path
                className="fah-flow"
                d={d}
                fill="none"
                stroke={e.color}
                strokeWidth={e.width}
                strokeOpacity={e.opacity}
                strokeLinecap="round"
                style={{ animationDuration: `${e.speed}s` }}
              />
            </g>
          )
        })}

        {/* nodes */}
        {allNodes.map((n, i) => {
          const dim = nodeDim(n.id)
          return (
            <g
              key={n.id}
              className="fah-float"
              style={{ animationDuration: `${5 + (i % 4)}s`, animationDelay: `${i * 0.4}s`, opacity: dim ? 0.2 : 1, transition: 'opacity 0.25s', cursor: 'pointer' }}
              onMouseEnter={() => setHover(n.id)}
              onMouseLeave={() => setHover(null)}
            >
              {/* glow halo */}
              <circle cx={n.x} cy={n.y} r={n.r + 6} fill={n.fill} opacity={0.35} filter="url(#fah-glow)" />
              {n.pulse && (
                <circle cx={n.x} cy={n.y} r={n.r + 6} fill="none" stroke={n.fill} strokeWidth={2} style={{ animation: 'fahPulse 1.6s ease-in-out infinite' }} />
              )}
              {/* identity ring */}
              <circle cx={n.x} cy={n.y} r={n.r} fill="#0b1220" stroke={n.ring} strokeWidth={n.id === 'hub' ? 3 : 3.5} />
              {/* health fill */}
              <circle cx={n.x} cy={n.y} r={n.r - 5} fill={n.fill} fillOpacity={0.9} />
              {/* labels */}
              <text x={n.x} y={n.y + n.r + 16} textAnchor="middle" fill="#e2e8f0" fontSize={n.id === 'hub' ? 14 : 12} fontWeight={700} style={{ pointerEvents: 'none' }}>
                {n.label}
              </text>
              {n.sub && (
                <text x={n.x} y={n.y + n.r + 32} textAnchor="middle" fill="#94a3b8" fontSize={10.5} style={{ pointerEvents: 'none' }}>
                  {n.sub}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
