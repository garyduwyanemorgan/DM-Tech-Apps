// Design-system metric/KPI card (GDM Lagoons Design System — Metric cards).
//
// Covers both existing shapes with one component:
//   - plain centered KPI tile (label / big value / sub) — no `icon`
//   - icon variant (44x44 tinted swatch + left-aligned text) — pass `icon`
// Typography follows the spec: uppercase 12px/700 slate label, 800-weight ink
// value, 13px sub/delta.
import React, { useState } from 'react'
import { COLORS, SHADOW } from '../../lib/tokens'

export interface MetricCardProps {
  label: string
  value: React.ReactNode
  /** Secondary line under the value (free-form). */
  sub?: React.ReactNode
  /** Trend line, colored by direction (up=green, down=red, neutral=slate). */
  delta?: { value: string; direction: 'up' | 'down' | 'neutral' }
  /** Presence switches to the icon-swatch layout (left-aligned). */
  icon?: React.ReactNode
  /** Tint for the icon swatch (10% alpha bg + full-strength icon). */
  accent?: string
  /** Override for the value text color (status-colored KPIs). */
  valueColor?: string
  align?: 'center' | 'left'
  style?: React.CSSProperties
}

const DELTA_COLOR = { up: '#006100', down: '#9C0006', neutral: COLORS.slate } as const

export const MetricCard: React.FC<MetricCardProps> = ({
  label, value, sub, delta, icon, accent = COLORS.navy, valueColor, align, style,
}) => {
  const [hovered, setHovered] = useState(false)
  const alignment = align ?? (icon ? 'left' : 'center')

  const text = (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: '12px', fontWeight: 700, color: COLORS.slate, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      <div style={{ fontSize: icon ? '1.55rem' : '2rem', fontWeight: 800, color: valueColor ?? COLORS.ink, letterSpacing: '-0.02em', lineHeight: 1.15, marginTop: 2 }}>
        {value}
      </div>
      {delta && (
        <div style={{ fontSize: '13px', fontWeight: 600, color: DELTA_COLOR[delta.direction], marginTop: 4 }}>
          {delta.value}
        </div>
      )}
      {sub && (
        <div style={{ fontSize: '13px', color: COLORS.slateLight, marginTop: delta ? 2 : 4 }}>{sub}</div>
      )}
    </div>
  )

  return (
    <div
      className="glass-card"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: icon ? '1.1rem 1.25rem' : '1.1rem 1rem',
        textAlign: alignment,
        display: icon ? 'flex' : undefined,
        alignItems: icon ? 'center' : undefined,
        gap: icon ? '1rem' : undefined,
        boxShadow: hovered ? '0 4px 12px rgba(15,23,42,0.08)' : SHADOW.sm,
        transition: 'box-shadow 0.15s',
        ...style,
      }}
    >
      {icon && (
        <div style={{ width: 44, height: 44, borderRadius: 10, background: `${accent}1A`, color: accent, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          {icon}
        </div>
      )}
      {text}
    </div>
  )
}
