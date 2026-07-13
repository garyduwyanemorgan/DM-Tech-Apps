// Shared inline-style tokens — legacy compatibility layer.
//
// Values are derived from lib/tokens.ts (the canonical design-system source)
// so there is exactly one hex per concept app-wide. New code should import
// from lib/tokens.ts and components/ui/ directly; these exports remain for
// the existing feature screens (CorrectiveActions, Inventory, Assets,
// ManagementKPIs) and are kept byte-compatible.
import type React from 'react'
import { COLORS as T, STATUS, RADIUS } from './tokens'

export const COLORS = {
  navy: T.navy,
  slate: T.slate,
  slateLight: T.slateLight,
  blue: '#4472C4',
  greenBg: STATUS.compliant.bg, greenFg: STATUS.compliant.fg, greenBorder: '#86efac',
  amberBg: STATUS.actionRequired.bg, amberFg: STATUS.actionRequired.fg, amberBorder: '#fcd34d',
  redBg: STATUS.critical.bg, redFg: STATUS.critical.fg, redBorder: '#f87171',
  border: T.border, surface: T.surface,
}

export const tableHeaderStyle: React.CSSProperties = {
  padding: '10px 14px', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700,
  color: COLORS.slate, textTransform: 'uppercase', letterSpacing: '0.05em',
  borderBottom: `2px solid ${COLORS.border}`, background: COLORS.surface, whiteSpace: 'nowrap',
}

export const tableCellStyle: React.CSSProperties = {
  padding: '12px 14px', fontSize: '0.875rem', color: '#374151', borderBottom: '1px solid #f1f5f9',
}

export const inputStyle: React.CSSProperties = {
  padding: '0.45rem 0.7rem', border: '1px solid #cbd5e1', borderRadius: RADIUS.sm,
  fontSize: '0.875rem', fontFamily: 'inherit',
}

/** Error-state input — apply alongside inputStyle when a field fails validation. */
export const errorInputStyle: React.CSSProperties = {
  border: '1px solid #F87171', background: '#FFF5F5', color: '#9C0006',
}

export const labelStyle: React.CSSProperties = {
  fontSize: '0.72rem', fontWeight: 700, color: COLORS.slate, textTransform: 'uppercase',
}

export const fieldStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: '0.3rem',
}

/**
 * Pill/badge style for a status colour set.
 * @deprecated Use <StatusBadge> from components/ui instead.
 */
export function pill(kind: 'green' | 'amber' | 'red' | 'slate'): React.CSSProperties {
  const map = {
    green: { background: COLORS.greenBg, color: COLORS.greenFg },
    amber: { background: COLORS.amberBg, color: COLORS.amberFg },
    red: { background: COLORS.redBg, color: COLORS.redFg },
    slate: { background: '#f1f5f9', color: COLORS.slate },
  }[kind]
  return { ...map, padding: '3px 12px', borderRadius: 9999, fontSize: '0.78rem', fontWeight: 700, display: 'inline-block' }
}
