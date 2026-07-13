// Shared inline-style tokens matching the app's existing palette (see Sludge.tsx,
// SiteManager.tsx). Extracted so the newer feature screens stay visually
// consistent without copy-pasting the same style objects into each file.
import type React from 'react'

export const COLORS = {
  navy: '#1B3A5C',
  slate: '#64748b',
  slateLight: '#94a3b8',
  blue: '#4472C4',
  greenBg: '#C6EFCE', greenFg: '#006100', greenBorder: '#86efac',
  amberBg: '#FFEB9C', amberFg: '#856404', amberBorder: '#fcd34d',
  redBg: '#FFC7CE', redFg: '#9C0006', redBorder: '#f87171',
  border: '#e2e8f0', surface: '#f8fafc',
}

export const tableHeaderStyle: React.CSSProperties = {
  padding: '10px 14px', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700,
  color: COLORS.slate, textTransform: 'uppercase', letterSpacing: '0.05em',
  borderBottom: `2px solid ${COLORS.border}`, background: COLORS.surface, whiteSpace: 'nowrap',
}

export const tableCellStyle: React.CSSProperties = {
  padding: '10px 14px', fontSize: '0.85rem', color: '#374151', borderBottom: '1px solid #f1f5f9',
}

export const inputStyle: React.CSSProperties = {
  padding: '0.45rem 0.7rem', border: '1px solid #cbd5e1', borderRadius: 6,
  fontSize: '0.875rem', fontFamily: 'inherit',
}

export const labelStyle: React.CSSProperties = {
  fontSize: '0.72rem', fontWeight: 700, color: COLORS.slate, textTransform: 'uppercase',
}

export const fieldStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: '0.3rem',
}

/** Pill/badge style for a status colour set. */
export function pill(kind: 'green' | 'amber' | 'red' | 'slate'): React.CSSProperties {
  const map = {
    green: { background: COLORS.greenBg, color: COLORS.greenFg },
    amber: { background: COLORS.amberBg, color: COLORS.amberFg },
    red: { background: COLORS.redBg, color: COLORS.redFg },
    slate: { background: '#f1f5f9', color: COLORS.slate },
  }[kind]
  return { ...map, padding: '3px 12px', borderRadius: 9999, fontSize: '0.78rem', fontWeight: 700, display: 'inline-block' }
}
