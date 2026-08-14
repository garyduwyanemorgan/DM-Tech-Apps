// Design-system status pill (GDM Lagoons Design System — Status badges).
//
// The one canonical rendering path for the traffic-light pill. Two prop paths:
//   <StatusBadge status="green" />            — fixed compliance semantics
//                                                (label comes from the token set)
//   <StatusBadge tone="amber">Open</StatusBadge> — same visual, custom label,
//                                                for workflow statuses that
//                                                aren't compliance states.
// `variant="count"` renders the smaller dot-less pill ("To-do 13").
import React from 'react'
import { LIGHT_STYLE, type TrafficLight } from '../../lib/status'

export type BadgeTone = 'green' | 'amber' | 'red' | 'slate' | 'blue'

const TONE_STYLE: Record<BadgeTone, { bg: string; fg: string; dot: string }> = {
  green: { bg: LIGHT_STYLE.green.bg, fg: LIGHT_STYLE.green.color, dot: LIGHT_STYLE.green.dot },
  amber: { bg: LIGHT_STYLE.yellow.bg, fg: LIGHT_STYLE.yellow.color, dot: LIGHT_STYLE.yellow.dot },
  red: { bg: LIGHT_STYLE.red.bg, fg: LIGHT_STYLE.red.color, dot: LIGHT_STYLE.red.dot },
  blue: { bg: LIGHT_STYLE.blue.bg, fg: LIGHT_STYLE.blue.color, dot: LIGHT_STYLE.blue.dot },
  slate: { bg: LIGHT_STYLE.grey.bg, fg: LIGHT_STYLE.grey.color, dot: LIGHT_STYLE.grey.dot },
}

const STATUS_TONE: Record<TrafficLight, BadgeTone> = {
  green: 'green', yellow: 'amber', red: 'red', blue: 'blue', grey: 'slate',
}

interface BaseProps {
  /** 'pill' (default) — dot + label; 'count' — smaller, no dot. */
  variant?: 'pill' | 'count'
  style?: React.CSSProperties
}

interface StatusProps extends BaseProps {
  /** Compliance traffic-light state; label comes from the token set. */
  status: TrafficLight
  tone?: never
  children?: never
}

interface ToneProps extends BaseProps {
  status?: never
  /** Visual tone for a custom-labelled (non-compliance) badge. */
  tone: BadgeTone
  children: React.ReactNode
}

export type StatusBadgeProps = StatusProps | ToneProps

export const StatusBadge: React.FC<StatusBadgeProps> = (props) => {
  const { variant = 'pill', style } = props
  const tone: BadgeTone = props.status ? STATUS_TONE[props.status] : props.tone
  const colors = TONE_STYLE[tone]
  const label = props.status ? LIGHT_STYLE[props.status].label : props.children

  const shape: React.CSSProperties =
    variant === 'count'
      ? { fontSize: '12px', fontWeight: 600, padding: '4px 12px' }
      : { fontSize: '13px', fontWeight: 700, padding: '6px 16px' }

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        background: colors.bg,
        color: colors.fg,
        borderRadius: 999,
        whiteSpace: 'nowrap',
        ...shape,
        ...style,
      }}
    >
      {variant === 'pill' && (
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: colors.dot, flexShrink: 0 }} />
      )}
      {label}
    </span>
  )
}
