// Frontend mirror of the backend atomic-permission catalogue (core/authz.py).
// The BACKEND is the authorization source of truth — this drives UI *usability*
// only (hiding controls a role cannot use). Keep the bundles below in sync with
// core/authz.py::ROLE_BUNDLES. Explicit bundles, never tier >= N ordering: a GM
// (auditor) has broad read but fewer write permissions than a Project Manager.

import type { Role } from './roles'

export type Permission =
  | 'sites.read' | 'sites.create' | 'sites.update' | 'sites.delete'
  | 'readings.read' | 'readings.create' | 'readings.overwrite'
  | 'reports.read' | 'reports.generate_draft' | 'reports.approve_final'
  | 'sludge.read' | 'sludge.write' | 'sludge.delete'
  | 'requests.read' | 'requests.create' | 'requests.fulfil'
  | 'actions.read' | 'actions.create' | 'actions.update' | 'actions.close'
  | 'inventory.read' | 'inventory.consume' | 'inventory.receive'
  | 'inventory.transfer' | 'inventory.adjust' | 'inventory.configure'
  | 'inventory.valuation.read'
  | 'assets.read' | 'assets.configure'
  | 'science.read' | 'science.simulate'
  | 'analytics.site.read' | 'analytics.project.read'
  | 'analytics.portfolio.read' | 'analytics.executive.read'
  | 'users.read' | 'users.invite' | 'users.role.assign'
  | 'users.executive.assign' | 'users.sites.assign' | 'users.remove'
  | 'billing.read' | 'billing.manage'
  | 'entitlements.manage'
  | 'organization.configure' | 'audit.read' | 'permissions.configure'
  | 'demo.activate'

const OPERATOR: Permission[] = [
  'sites.read', 'readings.read', 'readings.create', 'readings.overwrite',
  'reports.read', 'reports.generate_draft',
  'sludge.read', 'sludge.write', 'sludge.delete',
  'requests.read', 'requests.create', 'requests.fulfil',
  'actions.read', 'actions.create', 'actions.update',
  'inventory.read', 'inventory.consume',
  'assets.read', 'science.read', 'science.simulate',
  'analytics.site.read',
]

const ADMIN: Permission[] = [
  ...OPERATOR,
  'sites.create', 'sites.update', 'sites.delete',
  'reports.approve_final', 'actions.close',
  'inventory.receive', 'inventory.transfer', 'inventory.adjust', 'inventory.configure',
  'assets.configure', 'analytics.project.read',
  'users.read', 'users.invite', 'users.role.assign', 'users.remove',
  'billing.read', 'billing.manage', 'audit.read',
]

const AUDITOR: Permission[] = [
  'sites.read', 'readings.read', 'reports.read', 'reports.approve_final',
  'sludge.read', 'requests.read', 'actions.read',
  'inventory.read', 'inventory.valuation.read',
  'assets.read', 'science.read', 'science.simulate',
  'analytics.site.read', 'analytics.project.read', 'analytics.portfolio.read',
  'organization.configure', 'audit.read',
]

const SUPER_ADMIN: Permission[] = [
  ...ADMIN, ...AUDITOR,
  'users.executive.assign', 'users.sites.assign', 'inventory.valuation.read',
  'analytics.portfolio.read', 'analytics.executive.read',
  'organization.configure', 'permissions.configure',
  'demo.activate',
  // Ticking and un-ticking guideline modules — Executive Management only,
  // mirroring core/authz.py::_SUPER_ADMIN. Un-ticking is the dangerous
  // direction: it stops monitoring (§7.5), so it is not offered to the role
  // most likely to want an overdue duty to stop being tracked.
  'entitlements.manage',
]

const BUNDLES: Record<Role, Set<Permission>> = {
  operator: new Set(OPERATOR),
  admin: new Set(ADMIN),
  auditor: new Set(AUDITOR),
  super_admin: new Set(SUPER_ADMIN),
}

/** Whether a role holds a permission. Unknown/empty role => denied. */
export function hasPermission(role: string | null | undefined, permission: Permission): boolean {
  if (!role || !(role in BUNDLES)) return false
  return BUNDLES[role as Role].has(permission)
}
