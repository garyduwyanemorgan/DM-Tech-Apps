// Design-system alert card (GDM Lagoons Design System — Alerts).
// Full-background pastel card: dot + bold title + description.
// The `positive` tier is a pragmatic extension for de-escalation/success
// messaging (same pastel formula, not in the source design file).
import React from 'react'
import { ALERT_CARD, type AlertCardTier } from '../../lib/tokens'

export interface AlertCardProps {
  tier: AlertCardTier
  title: React.ReactNode
  description?: React.ReactNode
  style?: React.CSSProperties
}

export const AlertCard: React.FC<AlertCardProps> = ({ tier, title, description, style }) => {
  const t = ALERT_CARD[tier]
  return (
    <div
      style={{
        display: 'flex',
        gap: 12,
        alignItems: 'flex-start',
        background: t.bg,
        border: `1px solid ${t.border}`,
        borderRadius: 10,
        padding: '14px 16px',
        ...style,
      }}
    >
      <span style={{ width: 10, height: 10, borderRadius: '50%', background: t.dot, marginTop: 5, flexShrink: 0 }} />
      <div>
        <div style={{ fontSize: '14px', fontWeight: 700, color: t.title }}>{title}</div>
        {description && (
          <div style={{ fontSize: '13px', color: t.desc, marginTop: 2, lineHeight: 1.5 }}>{description}</div>
        )}
      </div>
    </div>
  )
}
