import React from 'react'
import { roleMeta } from '../lib/roles'

interface RoleBadgeProps {
  role: string
  /** 'sm' for inline table cells, 'md' (default) for the sidebar footer. */
  size?: 'sm' | 'md'
  /** Render on a dark background (e.g. the navy sidebar) with a translucent pill. */
  onDark?: boolean
}

/** Pill showing a user's role as icon + business label, coloured from ROLE_META. */
export const RoleBadge: React.FC<RoleBadgeProps> = ({ role, size = 'md', onDark = false }) => {
  const meta = roleMeta(role)
  const Icon = meta.icon
  const iconSize = size === 'sm' ? 13 : 15

  const style: React.CSSProperties = onDark
    ? {
        background: 'rgba(255,255,255,0.12)',
        color: '#ffffff',
        border: '1px solid rgba(255,255,255,0.18)',
      }
    : {
        background: meta.badge.bg,
        color: meta.badge.color,
        border: '1px solid transparent',
      }

  return (
    <span
      title={`Role: ${meta.label}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: size === 'sm' ? '5px' : '7px',
        padding: size === 'sm' ? '2px 8px' : '4px 11px',
        borderRadius: 999,
        fontSize: size === 'sm' ? '0.72rem' : '0.8rem',
        fontWeight: 600,
        lineHeight: 1.4,
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      <Icon size={iconSize} style={{ flexShrink: 0 }} />
      {meta.label}
    </span>
  )
}
