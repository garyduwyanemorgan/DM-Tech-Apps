import React, { useCallback, useEffect, useState } from 'react'
import { PageHeader } from './PageHeader'
import { useAuth } from '../context/AuthContext'
import { Trash2, UserPlus, Shield, AlertTriangle, Mail } from 'lucide-react'

interface OrgUser {
  id: string
  email: string
  role: string
  created_at: string
  last_sign_in: string
  provider: string
}

interface UserManagerProps {
  activeSite: string
  setActiveSite: (s: string) => void
  embedded?: boolean
}

const ROLE_LABELS: Record<string, string> = {
  operator: 'Operator',
  admin: 'Admin',
  super_admin: 'Super Admin',
}

const ROLE_COLORS: Record<string, { bg: string; color: string }> = {
  operator:    { bg: '#f1f5f9',  color: '#475569' },
  admin:       { bg: '#D6E4F0',  color: '#1B3A5C' },
  super_admin: { bg: '#C6EFCE',  color: '#006100' },
}

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

  // Remove confirmation
  const [pendingRemove, setPendingRemove] = useState<OrgUser | null>(null)
  const [removing, setRemoving] = useState(false)

  const isAdmin = myRole === 'admin' || myRole === 'super_admin'
  const isSuperAdmin = myRole === 'super_admin'

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
      setUsers(data.users || [])
    } catch {
      setError('Network error loading users.')
    } finally {
      setLoading(false)
    }
  }, [makeHeaders])

  useEffect(() => { if (isAdmin) fetchUsers() }, [fetchUsers, isAdmin])

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
      if (!res.ok) { setError(data.detail || 'Failed to send invite.'); return }
      setSuccess(`Invite sent to ${inviteEmail.trim()} as ${ROLE_LABELS[inviteRole]}.`)
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

  const availableRoles = isSuperAdmin
    ? ['operator', 'admin', 'super_admin']
    : ['operator', 'admin']

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
                {inviting ? 'Sending…' : 'Send Invite'}
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
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '560px' }}>
                <thead>
                  <tr>
                    <th style={TH}>User</th>
                    <th style={TH}>Login Method</th>
                    <th style={TH}>Role</th>
                    <th style={{ ...TH, textAlign: 'center' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => {
                    const isMe = u.id === user?.id
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
                            <span style={{ background: rc.bg, color: rc.color, fontSize: '0.72rem', fontWeight: 700, borderRadius: 4, padding: '2px 8px' }}>
                              {ROLE_LABELS[u.role] || u.role}
                            </span>
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

      {/* Role info card */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
        {[
          { role: 'operator', icon: '👤', desc: 'View dashboards, upload lab reports, read all data.' },
          { role: 'admin',    icon: '🔧', desc: 'All operator rights + manage sites, invite users, change roles.' },
          { role: 'super_admin', icon: <Shield size={16} />, desc: 'Full control including granting super_admin and removing admins.' },
        ].map(({ role: r, icon, desc }) => {
          const rc = ROLE_COLORS[r]
          return (
            <div key={r} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
                <span>{icon}</span>
                <span style={{ fontWeight: 700, fontSize: '0.875rem', color: rc.color, background: rc.bg, borderRadius: 4, padding: '1px 8px' }}>{ROLE_LABELS[r]}</span>
              </div>
              <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b', lineHeight: 1.5 }}>{desc}</p>
            </div>
          )
        })}
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
