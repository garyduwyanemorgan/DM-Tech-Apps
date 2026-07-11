// Single source of truth for how the four technical roles map onto the platform's
// business roles (see Downloads/wip/1.png design spec). The DB role strings are kept
// as-is; only the *displayed* label, icon, dashboard tier, and badge colour change.
//
//   operator     → Site Supervisor          (tier 1, most granular)
//   admin        → Project / Contract Manager (tier 2)
//   auditor      → General Manager           (tier 3, portfolio)
//   super_admin  → Executive Management      (tier 4, org-wide)
//
// Consolidates the role logic that used to be scattered as isAdmin/isSuperAdmin
// checks across components.

import type { LucideIcon } from 'lucide-react'
import { HardHat, ClipboardList, Briefcase, Crown } from 'lucide-react'

export type Role = 'operator' | 'admin' | 'auditor' | 'super_admin'

export type RoleTier = 1 | 2 | 3 | 4

export interface RoleMeta {
  /** DB role string. */
  key: Role
  /** Business-facing name shown in the UI. */
  label: string
  /** Detail altitude: 1 = most granular, 4 = highest-level. */
  tier: RoleTier
  /** lucide-react icon for the role badge. */
  icon: LucideIcon
  /** Badge pill colours (reusing the app's navy/slate/Excel palette). */
  badge: { bg: string; color: string }
  /** Which dashboard component the role lands on (rendered on the `dashboard` tab). */
  dashboardTier: RoleTier
}

export const ROLE_META: Record<Role, RoleMeta> = {
  operator: {
    key: 'operator',
    label: 'Site Supervisor',
    tier: 1,
    icon: HardHat,
    badge: { bg: '#D6E4F0', color: '#1B3A5C' },
    dashboardTier: 1,
  },
  admin: {
    key: 'admin',
    label: 'Project / Contract Manager',
    tier: 2,
    icon: ClipboardList,
    badge: { bg: '#DBEAFE', color: '#1E40AF' },
    dashboardTier: 2,
  },
  auditor: {
    key: 'auditor',
    label: 'General Manager',
    tier: 3,
    icon: Briefcase,
    badge: { bg: '#EDE9FE', color: '#5B21B6' },
    dashboardTier: 3,
  },
  super_admin: {
    key: 'super_admin',
    label: 'Executive Management',
    tier: 4,
    icon: Crown,
    badge: { bg: '#C6EFCE', color: '#006100' },
    dashboardTier: 4,
  },
}

const DEFAULT_ROLE: Role = 'operator'

/** Safe lookup — any unknown/empty role string falls back to Site Supervisor. */
export function roleMeta(role: string | null | undefined): RoleMeta {
  if (role && role in ROLE_META) return ROLE_META[role as Role]
  return ROLE_META[DEFAULT_ROLE]
}

/** Roles assignable in the User Manager, ordered low → high tier. */
export const ASSIGNABLE_ROLES: Role[] = ['operator', 'admin', 'auditor', 'super_admin']
