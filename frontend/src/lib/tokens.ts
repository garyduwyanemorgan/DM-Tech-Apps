// GDM Lagoons Design System — canonical token source of truth.
//
// Imported from the "GDM Lagoons Design System.dc.html" reference file
// (Claude Design project). Every color used for compliance status, alert
// levels, or chrome should trace back to exactly one entry here — lib/ui.ts,
// lib/status.ts, and constants.ts derive their exports from these values so
// a palette change propagates everywhere from a single edit.
//
// Two color systems coexist deliberately and must not be conflated:
//   STATUS — the 4-state compliance traffic light (green/yellow/red/blue)
//   ALERT  — the 4-level bloom/escalation scale (GREEN/WATCH/WARNING/CRITICAL),
//            which has an orange level 3 with no traffic-light equivalent.

export const COLORS = {
  /** Ink Navy — headings and high-contrast text. */
  ink: '#0B1240',
  /** Brand Navy — chrome only (sidebar background, gradients). */
  navy: '#1B3A5C',
  /** Steel Blue — gradient partner and hover states on navy chrome. */
  steel: '#2E5D8A',
  /** Accent indigo — primary actions, links, active borders, focus rings. */
  accent: '#4F5AE8',
  mist: '#D6E4F0',
  surface: '#F8FAFC',
  slate: '#64748B',
  slateLight: '#94A3B8',
  border: '#E2E8F0',
  compliant: '#27AE60',
  warning: '#F39C12',
  critical: '#E74C3C',
  awaiting: '#3B82F6',
} as const

/** 4-state compliance traffic-light pill: pastel bg/fg + saturated dot. */
export const STATUS = {
  compliant:      { bg: '#C6EFCE', fg: '#006100', dot: COLORS.compliant, label: 'Compliant' },
  actionRequired: { bg: '#FFEB9C', fg: '#856404', dot: COLORS.warning,   label: 'Action Required' },
  critical:       { bg: '#FFC7CE', fg: '#9C0006', dot: COLORS.critical,  label: 'Critical' },
  awaitingLab:    { bg: '#D6E4F0', fg: '#1B3A5C', dot: COLORS.awaiting,  label: 'Awaiting Lab' },
} as const

export type StatusKey = keyof typeof STATUS

/** 4-level bloom/escalation alert scale — separate system from STATUS. */
export const ALERT: Record<number, { color: string; bg: string; fg: string; label: string }> = {
  1: { color: '#27AE60', bg: '#C6EFCE', fg: '#006100', label: 'Level 1 — GREEN' },
  2: { color: '#F39C12', bg: '#FFEB9C', fg: '#856404', label: 'Level 2 — WATCH' },
  3: { color: '#E67E22', bg: '#FFD5A8', fg: '#7A3B00', label: 'Level 3 — WARNING' },
  4: { color: '#E74C3C', bg: '#FFC7CE', fg: '#9C0006', label: 'Level 4 — CRITICAL' },
}

/**
 * Full-background alert-card tiers (AlertCard component). The `positive` tier
 * is a pragmatic extension beyond the source design file (same pastel-card
 * formula), used for de-escalation / success messaging.
 */
export const ALERT_CARD = {
  critical:       { bg: '#FFF5F5', border: '#FECACA', dot: '#E74C3C', title: '#9C0006', desc: '#7F1D1D' },
  actionRequired: { bg: '#FFFBEB', border: '#FDE68A', dot: '#F39C12', title: '#856404', desc: '#78350F' },
  awaiting:       { bg: '#EFF6FF', border: '#BFDBFE', dot: '#3B82F6', title: '#1B3A5C', desc: '#1E40AF' },
  positive:       { bg: '#F0FDF4', border: '#BBF7D0', dot: '#16A34A', title: '#166534', desc: '#14532D' },
} as const

export type AlertCardTier = keyof typeof ALERT_CARD

/** Type scale (Inter). */
export const TYPE = {
  display:  { size: '44px', weight: 800 },
  heading1: { size: '34px', weight: 800 },
  heading2: { size: '22px', weight: 700 },
  body:     { size: '15px', weight: 400 },
  caption:  { size: '12px', weight: 700 },
} as const

/** 4px spacing grid. */
export const SPACE = [4, 8, 12, 16, 24, 32, 48] as const

/** Corner radii: sm inputs/buttons, md cards, lg elevated surfaces. */
export const RADIUS = { sm: 8, md: 10, lg: 14 } as const

export const SHADOW = {
  sm: '0 1px 3px rgba(15,23,42,0.08)',
  lg: '0 8px 24px rgba(15,23,42,0.14)',
} as const
