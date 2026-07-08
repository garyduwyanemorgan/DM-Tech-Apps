import React, { useState } from 'react'
import { stressColor, CHEM_LOOP_COLOR } from '../lib/chemistryIntelligence'
import type { ChemistryIntelligence } from '../lib/chemistryIntelligence'

// ─────────────────────────────────────────────────────────────────────────────
// Chemistry Loop — Obsidian-style systems graph (amber loop identity).
//
// Chemistry hub (centre) ↔ eight process nodes (ring) → event nodes that appear
// only when triggered. Dark canvas so colours pop. Fill = health (stress),
// outer ring = amber Chemistry-loop identity, edges carry flowing particles.
// SVG + CSS only — deterministic radial layout, no physics library.
// ─────────────────────────────────────────────────────────────────────────────

const W = 860
const H = 580
const HUB = { x: 430, y: 285 }
const R = 158 // process ring radius
const EVENT_R = 250 // event ring radius

interface GNode {
  id: string
  x: number
  y: number
  r: number
  fill: string
  ring: string
  label: string
  sub?: string
  pulse?: boolean
  modelled?: boolean
}

export const ChemistryGraph: React.FC<{ intel: ChemistryIntelligence }> = ({ intel }) => {
  const [hover, setHover] = useState<string | null>(null)

  // ── process ring positions ──────────────────────────────────────────────────
  const n = intel.processes.length
  const pos: Record<string, { x: number; y: number }> = {}
  const processNodes: GNode[] = intel.processes.map((p, i) => {
    const ang = (-90 + (360 / n) * i) * (Math.PI / 180)
    const x = HUB.x + R * Math.cos(ang)
    const y = HUB.y + R * Math.sin(ang)
    pos[p.key] = { x, y }
    return {
      id: p.key,
      x,
      y,
      r: 16 + (p.stress / 100) * 16,
      fill: stressColor(p.stress),
      ring: CHEM_LOOP_COLOR,
      label: p.label,
      sub: `${Math.round(p.stress)} · ${p.value}`,
      modelled: p.modelled,
    }
  })

  // ── hub ─────────────────────────────────────────────────────────────────────
  const hubNode: GNode = {
    id: 'hub',
    x: HUB.x,
    y: HUB.y,
    r: 34 + (intel.csi / 100) * 24,
    fill: intel.state.color,
    ring: CHEM_LOOP_COLOR,
    label: 'Chemistry',
    sub: `CSI ${intel.csi} · ${intel.state.level}`,
    pulse: intel.csi >= 60,
  }

  // ── event nodes (only when triggered), placed beyond their driving process ──
  const eventNodes: GNode[] = intel.events.map((e) => {
    const i = intel.processes.findIndex((p) => p.key === e.from)
    const ang = (-90 + (360 / n) * i) * (Math.PI / 180)
    return {
      id: `ev-${e.id}`,
      x: HUB.x + EVENT_R * Math.cos(ang),
      y: HUB.y + EVENT_R * Math.sin(ang),
      r: 15,
      fill: e.color,
      ring: e.color,
      label: e.label,
      pulse: e.pulse,
    }
  })

  // ── edges ─────────────────────────────────────────────────────────────────
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
  const edges: GEdge[] = [
    ...intel.processes.map((p) => ({
      id: `e-${p.key}`,
      from: pos[p.key],
      to: { x: hubNode.x, y: hubNode.y },
      color: stressColor(p.stress),
      width: 1.5 + p.contribution / 1.6,
      opacity: Math.max(0.28, p.stress / 100),
      speed: 2.4 - p.stress / 100,
      connects: [p.key, 'hub'] as [string, string],
    })),
    ...intel.events.map((e) => ({
      id: `e-ev-${e.id}`,
      from: pos[e.from],
      to: eventNodes.find((x) => x.id === `ev-${e.id}`)!,
      color: e.color,
      width: 2.5,
      opacity: 0.85,
      speed: 1.5,
      connects: [e.from, `ev-${e.id}`] as [string, string],
    })),
  ]

  const allNodes = [...processNodes, hubNode, ...eventNodes]
  const isDim = (ids: string[]) => hover !== null && !ids.some((id) => id === hover)
  const nodeDim = (id: string) => {
    if (hover === null || id === hover) return false
    if (hover === 'hub' && processNodes.some((p) => p.id === id)) return false
    return !edges.some((e) => e.connects.includes(hover) && e.connects.includes(id))
  }

  const line = (e: GEdge) => `M ${e.from.x} ${e.from.y} L ${e.to.x} ${e.to.y}`

  return (
    <div
      style={{
        position: 'relative',
        borderRadius: 16,
        overflow: 'hidden',
        background: 'radial-gradient(circle at 50% 50%, #241c10 0%, #0b1220 72%)',
        border: '1px solid #1e293b',
        boxShadow: 'inset 0 0 80px rgba(0,0,0,0.45)',
      }}
    >
      <style>{`
        @keyframes chemFlow { to { stroke-dashoffset: -60; } }
        @keyframes chemPulse { 0%,100% { opacity: .22; } 50% { opacity: .7; } }
        @keyframes chemFloat { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
        .chem-flow { stroke-dasharray: 1.5 9; animation: chemFlow linear infinite; }
        .chem-float { animation: chemFloat ease-in-out infinite; }
      `}</style>

      <div style={{ position: 'absolute', top: 12, left: 14, fontSize: '0.7rem', color: '#94a3b8', zIndex: 2, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: CHEM_LOOP_COLOR, fontSize: '0.85rem' }}>●</span>
        <span style={{ fontWeight: 700, color: '#e2e8f0' }}>Chemistry Loop</span>
        <span style={{ color: '#64748b' }}>ring = loop identity · fill = stress · flow = influence</span>
      </div>
      <div style={{ position: 'absolute', bottom: 12, left: 14, fontSize: '0.66rem', color: '#64748b', zIndex: 2 }}>
        Nodes with a dashed ring are modelled from redox (no direct lab value).
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }} preserveAspectRatio="xMidYMid meet">
        <defs>
          <filter id="chem-glow" x="-60%" y="-60%" width="220%" height="220%">
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
          const d = line(e)
          return (
            <g key={e.id} style={{ opacity: dim ? 0.07 : 1, transition: 'opacity 0.25s' }}>
              <path d={d} fill="none" stroke={e.color} strokeWidth={e.width} strokeOpacity={e.opacity * 0.32} />
              <path
                className="chem-flow"
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
        {allNodes.map((node, i) => {
          const dim = nodeDim(node.id)
          const isEvent = node.id.startsWith('ev-')
          return (
            <g
              key={node.id}
              className="chem-float"
              style={{ animationDuration: `${5 + (i % 4)}s`, animationDelay: `${i * 0.3}s`, opacity: dim ? 0.18 : 1, transition: 'opacity 0.25s', cursor: 'pointer' }}
              onMouseEnter={() => setHover(node.id)}
              onMouseLeave={() => setHover(null)}
            >
              <circle cx={node.x} cy={node.y} r={node.r + 6} fill={node.fill} opacity={0.32} filter="url(#chem-glow)" />
              {node.pulse && (
                <circle cx={node.x} cy={node.y} r={node.r + 6} fill="none" stroke={node.fill} strokeWidth={2} style={{ animation: 'chemPulse 1.6s ease-in-out infinite' }} />
              )}
              <circle
                cx={node.x}
                cy={node.y}
                r={node.r}
                fill="#0b1220"
                stroke={node.ring}
                strokeWidth={node.id === 'hub' ? 3 : 3}
                strokeDasharray={node.modelled ? '4 3' : undefined}
              />
              <circle cx={node.x} cy={node.y} r={node.r - 5} fill={node.fill} fillOpacity={0.9} />
              <text
                x={node.x}
                y={node.y + node.r + 15}
                textAnchor="middle"
                fill={isEvent ? node.fill : '#e2e8f0'}
                fontSize={node.id === 'hub' ? 15 : isEvent ? 11 : 12}
                fontWeight={700}
                style={{ pointerEvents: 'none' }}
              >
                {node.label}
              </text>
              {node.sub && (
                <text x={node.x} y={node.y + node.r + 30} textAnchor="middle" fill="#94a3b8" fontSize={10} style={{ pointerEvents: 'none' }}>
                  {node.sub}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
