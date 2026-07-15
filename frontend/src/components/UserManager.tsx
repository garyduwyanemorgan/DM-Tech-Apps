import React, { useCallback, useEffect, useRef, useState } from 'react'
import { PageHeader } from './PageHeader'
import { useAuth } from '../context/AuthContext'
import { Trash2, UserPlus, AlertTriangle, Mail, ChevronDown, MapPin } from 'lucide-react'
import { RoleBadge } from './RoleBadge'
import { ROLE_META, ASSIGNABLE_ROLES, type Role } from '../lib/roles'
import { hasPermission } from '../lib/permissions'

interface OrgUser {
  id: string
  clerk_id: string | null
  email: string
  role: string
  created_at: string
  last_sign_in: string
  provider: string
  site_ids: string[]
}

interface SiteOption {
  id: string
  name: string
}

interface UserManagerProps {
  activeSite: string
  setActiveSite: (s: string) => void
  embedded?: boolean
}

// Business-facing role names/colours are sourced from the shared role config so
// the User Manager, sidebar badge, and dashboards all agree.
const ROLE_LABELS: Record<string, string> = Object.fromEntries(
  Object.entries(ROLE_META).map(([k, m]) => [k, m.label]),
)

const ROLE_COLORS: Record<string, { bg: string; color: string }> = Object.fromEntries(
  Object.entries(ROLE_META).map(([k, m]) => [k, m.badge]),
)

const TH: React.CSSProperties = {
  padding: '9px 14px',
  textAlign: 'left',
  fontSize: '0.72rem',
  fontWeight: 700,
  color: '#64748b',
  background: '#f8fafc',
  borderBottom: '2px solid #e2e8f0',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  whiteSpace: 'nowrap',
}

const TD: React.CSSProperties = {
  padding: '10px 14px',
  fontSize: '0.875rem',
  color: '#374151',
  borderBottom: '1px solid #f1f5f9',
  verticalAlign: 'middle',
}

// Multi-select dropdown of the organisation's sites. Each option is a checkbox;
// every checked site is one the user may work on. Read-only unless the viewer
// holds users.sites.assign (Executive Management).
const SitesCell: React.FC<{
  sites: SiteOption[]
  selectedIds: string[]
  editable: boolean
  saving: boolean
  pendingSignIn: boolean
  onToggle: (siteId: string) => void
}> = ({ sites, selectedIds, editable, saving, pendingSignIn, onToggle }) => {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const selected = sites.filter(s => selectedIds.includes(s.id))
  const summary =
    selected.length === 0 ? 'No sites' :
    selected.length === 1 ? selected[0].name :
    `${selected.length} sites`

  if (!editable) {
    return (
      <span style={{ fontSize: '0.8rem', color: selected.length ? '#374151' : '#94a3b8' }} title={selected.map(s => s.name).join(', ')}>
        {summary}
      </span>
    )
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        disabled={saving || pendingSignIn}
        title={pendingSignIn ? 'User has not signed in yet — sites can be assigned after their first sign-in.' : 'Assign sites this user can work on'}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
          padding: '3px 10px', border: '1px solid #cbd5e1', borderRadius: 6,
          fontSize: '0.8rem', fontFamily: 'inherit', fontWeight: 600,
          background: '#fff', color: pendingSignIn ? '#94a3b8' : '#374151',
          cursor: pendingSignIn ? 'not-allowed' : 'pointer', opacity: saving ? 0.6 : 1,
        }}
      >
        <MapPin size={12} />
        {saving ? 'Saving…' : summary}
        <ChevronDown size={12} />
      </button>
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 50,
          background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8,
          boxShadow: '0 8px 24px rgba(0,0,0,0.12)', padding: '0.4rem',
          minWidth: 200, maxHeight: 240, overflowY: 'auto',
        }}>
          {sites.length === 0 ? (
            <div style={{ padding: '0.5rem', fontSize: '0.8rem', color: '#94a3b8' }}>No sites in this organisation yet.</div>
          ) : sites.map(s => (
            <label
              key={s.id}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.5rem',
                padding: '0.35rem 0.5rem', borderRadius: 6, cursor: 'pointer',
                fontSize: '0.82rem', color: '#374151', userSelect: 'none',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = '#f8fafc' }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent' }}
            >
              <input
                type="checkbox"
                checked={selectedIds.includes(s.id)}
                disabled={saving}
                onChange={() => onToggle(s.id)}
                style={{ cursor: 'pointer' }}
              />
              {s.name}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

export const UserManager: React.FC<UserManagerProps> = ({ embedded }) => {
  const { organizationId, token, role: myRole, user } = useAuth()
  const [users, setUsers] = useState<OrgUser[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Invite form
  const [showInvite, setShowInvite] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('operator')
  const [inviting, setInviting] = useState(false)

  // Role change
  const [updatingId, setUpdatingId] = useState<string | null>(null)

  // Site assignment
  const [sites, setSites] = useState<SiteOption[]>([])
  const [savingSitesId, setSavingSitesId] = useState<string | null>(null)

  // Remove confirmation
  const [pendingRemove, setPendingRemove] = useState<OrgUser | null>(null)
  const [removing, setRemoving] = useState(false)

  const isAdmin = myRole === 'admin' || myRole === 'super_admin'
  const isSuperAdmin = myRole === 'super_admin'
  const canAssignSites = hasPermission(myRole, 'users.sites.assign')

  const makeHeaders = useCallback((): HeadersInit => {
    const h: HeadersInit = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [token, organizationId])

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/users', { headers: makeHeaders() })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to load users.'); return }
      setUsers((data.users || []).map((u: OrgUser) => ({ ...u, site_ids: u.site_ids || [] })))
    } catch {
      setError('Network error loading users.')
    } finally {
      setLoading(false)
    }
  }, [makeHeaders])

  const fetchSites = useCallback(async () => {
    try {
      const res = await fetch('/api/sites', { headers: makeHeaders() })
      const data = await res.json()
      if (!res.ok) return
      setSites((data.sites || [])
        .filter((s: { id?: string }) => s.id)
        .map((s: { id: string; name: string }) => ({ id: s.id, name: s.name })))
    } catch {
      // Sites column degrades to "No sites"; the rest of the page still works.
    }
  }, [makeHeaders])

  useEffect(() => { if (isAdmin) { fetchUsers(); fetchSites() } }, [fetchUsers, fetchSites, isAdmin])

  const handleRoleChange = async (targetUser: OrgUser, newRole: string) => {
    setUpdatingId(targetUser.id)
    setError(null); setSuccess(null)
    try {
      const res = await fetch(`/api/users/${targetUser.id}`, {
        method: 'PATCH',
        headers: makeHeaders(),
        body: JSON.stringify({ role: newRole }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to update role.'); return }
      setSuccess(`${targetUser.email} is now ${ROLE_LABELS[newRole] || newRole}.`)
      setUsers(u => u.map(x => x.id === targetUser.id ? { ...x, role: newRole } : x))
    } catch {
      setError('Network error updating role.')
    } finally {
      setUpdatingId(null)
    }
  }

  const handleSiteToggle = async (targetUser: OrgUser, siteId: string) => {
    const next = targetUser.site_ids.includes(siteId)
      ? targetUser.site_ids.filter(id => id !== siteId)
      : [...targetUser.site_ids, siteId]
    setSavingSitesId(targetUser.id)
    setError(null); setSuccess(null)
    try {
      const res = await fetch(`/api/users/${targetUser.id}/sites`, {
        method: 'PUT',
        headers: makeHeaders(),
        body: JSON.stringify({ site_ids: next }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to update site assignments.'); return }
      setUsers(u => u.map(x => x.id === targetUser.id ? { ...x, site_ids: next } : x))
    } catch {
      setError('Network error updating site assignments.')
    } finally {
      setSavingSitesId(null)
    }
  }

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inviteEmail.trim()) return
    setInviting(true); setError(null); setSuccess(null)
    try {
      const res = await fetch('/api/users/invite', {
        method: 'POST',
        headers: makeHeaders(),
        body: JSON.stringify({ email: inviteEmail.trim(), role: inviteRole }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to send invitation.'); return }
      setSuccess(`Invitation email sent to ${data.email} as ${ROLE_LABELS[inviteRole]}. They'll set their own password from the link.`)
      setInviteEmail(''); setInviteRole('operator'); setShowInvite(false)
      await fetchUsers()
    } catch {
      setError('Network error sending invite.')
    } finally {
      setInviting(false)
    }
  }

  const handleRemove = async () => {
    if (!pendingRemove) return
    setRemoving(true); setError(null); setSuccess(null)
    try {
      const res = await fetch(`/api/users/${pendingRemove.id}`, {
        method: 'DELETE',
        headers: makeHeaders(),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to remove user.'); return }
      setSuccess(`${pendingRemove.email} removed from organisation.`)
      setUsers(u => u.filter(x => x.id !== pendingRemove.id))
      setPendingRemove(null)
    } catch {
      setError('Network error removing user.')
    } finally {
      setRemoving(false)
    }
  }

  // Super admins can assign every role; admins can assign everything except
  // Executive Management (super_admin).
  const availableRoles: Role[] = isSuperAdmin
    ? ASSIGNABLE_ROLES
    : ASSIGNABLE_ROLES.filter(r => r !== 'super_admin')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {!embedded && (
        <PageHeader
          title="User Management"
          subtitle="Manage organisation members, roles, and invitations"
        />
      )}

      {!isAdmin && (
        <div style={{ background: '#FFEB9C', color: '#856404', padding: '0.75rem 1rem', borderRadius: 6, fontSize: '0.875rem', border: '1px solid #fcd34d', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <AlertTriangle size={16} />
          User management requires Admin access.
        </div>
      )}

      {error   && <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.75rem 1rem', borderRadius: 6, fontSize: '0.875rem', border: '1px solid #fecaca' }}>{error}</div>}
      {success && <div style={{ background: '#C6EFCE', color: '#006100', padding: '0.75rem 1rem', borderRadius: 6, fontSize: '0.875rem', border: '1px solid #86efac' }}>{success}</div>}

      {isAdmin && (
        <div className="glass-card">
          {/* Header row */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
            <h2 style={{ fontSize: '1.05rem', margin: 0, color: '#1B3A5C' }}>
              Organisation Members
              {!loading && <span style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 400, marginLeft: '0.5rem' }}>({users.length})</span>}
            </h2>
            <button
              onClick={() => { setShowInvite(v => !v); setError(null); setSuccess(null) }}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 0.85rem', fontSize: '0.875rem' }}
            >
              <UserPlus size={15} />
              {showInvite ? 'Cancel' : 'Invite User'}
            </button>
          </div>

          {/* Invite form */}
          {showInvite && (
            <form onSubmit={handleInvite} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '1rem', marginBottom: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
              <div style={{ flex: '2 1 200px', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Email Address *</label>
                <input
                  type="email"
                  required
                  placeholder="user@example.com"
                  value={inviteEmail}
                  onChange={e => setInviteEmail(e.target.value)}
                  style={{ padding: '0.45rem 0.75rem', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: '0.875rem', fontFamily: 'inherit' }}
                />
              </div>
              <div style={{ flex: '1 1 140px', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Role</label>
                <select
                  value={inviteRole}
                  onChange={e => setInviteRole(e.target.value)}
                  style={{ padding: '0.45rem 0.75rem', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: '0.875rem', fontFamily: 'inherit', background: '#fff', color: '#374151' }}
                >
                  {availableRoles.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                </select>
              </div>
              <button type="submit" disabled={inviting || !inviteEmail.trim()} style={{ padding: '0.45rem 1.1rem', fontSize: '0.875rem', alignSelf: 'flex-end', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Mail size={14} />
                {inviting ? 'Creating…' : 'Create Account'}
              </button>
            </form>
          )}

          {/* Users table */}
          {loading ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b', fontSize: '0.875rem' }}>Loading users…</div>
          ) : users.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.875rem' }}>No users found.</div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '680px' }}>
                <thead>
                  <tr>
                    <th style={TH}>User</th>
                    <th style={TH}>Login Method</th>
                    <th style={TH}>Role</th>
                    <th style={TH}>Sites</th>
                    <th style={{ ...TH, textAlign: 'center' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => {
                    const isMe = u.clerk_id === user?.id
                    const rc = ROLE_COLORS[u.role] || ROLE_COLORS.operator
                    return (
                      <tr key={u.id}>
                        <td style={TD}>
                          <div style={{ fontWeight: isMe ? 700 : 400, color: isMe ? '#1B3A5C' : '#374151' }}>
                            {u.email}
                            {isMe && <span style={{ marginLeft: '0.5rem', fontSize: '0.72rem', background: '#D6E4F0', color: '#1B3A5C', borderRadius: 4, padding: '1px 6px', fontWeight: 600 }}>You</span>}
                          </div>
                        </td>
                        <td style={TD}>
                          <span style={{ fontSize: '0.78rem', color: '#64748b', textTransform: 'capitalize' }}>
                            {u.provider === 'email' ? '✉ Email / Password' : `⬡ ${u.provider}`}
                          </span>
                        </td>
                        <td style={TD}>
                          {isMe || (!isSuperAdmin && u.role === 'super_admin') ? (
                            <RoleBadge role={u.role} size="sm" />
                          ) : (
                            <select
                              value={u.role}
                              disabled={updatingId === u.id}
                              onChange={e => handleRoleChange(u, e.target.value)}
                              style={{ padding: '3px 8px', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: '0.8rem', fontFamily: 'inherit', background: rc.bg, color: rc.color, fontWeight: 600, cursor: 'pointer' }}
                            >
                              {availableRoles.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                            </select>
                          )}
                        </td>
                        <td style={TD}>
                          <SitesCell
                            sites={sites}
                            selectedIds={u.site_ids}
                            editable={canAssignSites}
                            saving={savingSitesId === u.id}
                            pendingSignIn={!u.clerk_id}
                            onToggle={siteId => handleSiteToggle(u, siteId)}
                          />
                        </td>
                        <td style={{ ...TD, textAlign: 'center' }}>
                          {!isMe && (isSuperAdmin || u.role !== 'super_admin') ? (
                            <button
                              onClick={() => { setPendingRemove(u); setError(null); setSuccess(null) }}
                              style={{ background: 'transparent', border: '1px solid #fecaca', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', color: '#9C0006', display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.78rem', fontFamily: 'inherit' }}
                            >
                              <Trash2 size={13} />
                              Remove
                            </button>
                          ) : (
                            <span style={{ color: '#cbd5e1', fontSize: '0.78rem' }}>—</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Role info card — the four business roles and the detail they see */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        {[
          { role: 'operator',    desc: 'Site Supervisor — full operational detail: every parameter, lab value, inspection, and corrective action.' },
          { role: 'admin',       desc: 'Project / Contract Manager — per-project compliance summary, outstanding actions, and key risks.' },
          { role: 'auditor',     desc: 'General Manager — portfolio view across all projects with status indicators and management KPIs.' },
          { role: 'super_admin', desc: 'Executive Management — organisation-wide compliance, regulatory risk, and trends, with drill-down.' },
        ].map(({ role: r, desc }) => (
          <div key={r} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: '1rem' }}>
            <div style={{ marginBottom: '0.5rem' }}>
              <RoleBadge role={r} size="sm" />
            </div>
            <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b', lineHeight: 1.5 }}>{desc}</p>
          </div>
        ))}
      </div>

      {/* Remove confirmation modal */}
      {pendingRemove && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
          <div style={{ background: '#fff', borderRadius: 12, padding: '2rem', maxWidth: 420, width: '100%', boxShadow: '0 20px 60px rgba(0,0,0,0.25)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
              <div style={{ background: '#FFF0F0', borderRadius: '50%', padding: '0.6rem', display: 'flex' }}>
                <AlertTriangle size={22} color="#9C0006" />
              </div>
              <h3 style={{ margin: 0, fontSize: '1.05rem', color: '#1B3A5C' }}>Remove User</h3>
            </div>
            <p style={{ color: '#374151', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
              Remove <strong>{pendingRemove.email}</strong> from the organisation? They will lose access immediately. Their account is not deleted — an admin can re-invite them later.
            </p>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button className="secondary" onClick={() => setPendingRemove(null)} disabled={removing}>Cancel</button>
              <button onClick={handleRemove} disabled={removing} style={{ background: '#9C0006', color: '#fff', border: 'none' }}>
                {removing ? 'Removing…' : 'Remove User'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
