import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { hasPermission } from '../lib/permissions'
import { PageHeader } from './PageHeader'
import { COLORS, tableHeaderStyle, tableCellStyle, inputStyle, labelStyle, fieldStyle } from '../lib/ui'
import { MetricCard, StatusBadge, Button, type BadgeTone } from './ui'
import { Plus, ChevronDown, ChevronRight } from 'lucide-react'

type Status = 'open' | 'in_progress' | 'pending_approval' | 'closed' | 'cancelled'

interface Action {
  id: string
  title: string
  description: string | null
  severity: string | null
  status: Status
  owner_clerk_id: string | null
  due_date: string | null
  created_at: string
}
interface ActionEvent {
  id: number
  event_type: string
  from_status: string | null
  to_status: string | null
  actor_clerk_id: string | null
  note: string | null
  created_at: string
}

const STATUS_TONE: Record<Status, BadgeTone> = {
  open: 'slate', in_progress: 'amber', pending_approval: 'amber', closed: 'green', cancelled: 'red',
}
const STATUS_LABEL: Record<Status, string> = {
  open: 'Open', in_progress: 'In Progress', pending_approval: 'Pending Approval', closed: 'Closed', cancelled: 'Cancelled',
}
// Transitions offered per status: [target, button label, required permission]
const TRANSITIONS: Record<Status, [Status, string, 'actions.update' | 'actions.close'][]> = {
  open: [['in_progress', 'Start', 'actions.update'], ['cancelled', 'Cancel', 'actions.update']],
  in_progress: [['pending_approval', 'Submit for approval', 'actions.update'], ['cancelled', 'Cancel', 'actions.update']],
  pending_approval: [['closed', 'Approve & close', 'actions.close'], ['in_progress', 'Send back', 'actions.update']],
  closed: [], cancelled: [],
}

export const CorrectiveActions: React.FC = () => {
  const { organizationId, token, role } = useAuth()
  const canCreate = hasPermission(role, 'actions.create')

  const [actions, setActions] = useState<Action[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [showForm, setShowForm] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [severity, setSeverity] = useState('medium')
  const [dueDate, setDueDate] = useState('')
  const [saving, setSaving] = useState(false)

  const [expanded, setExpanded] = useState<string | null>(null)
  const [events, setEvents] = useState<Record<string, ActionEvent[]>>({})
  const [busyId, setBusyId] = useState<string | null>(null)

  const makeHeaders = useCallback((): HeadersInit => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [token, organizationId])

  const fetchActions = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await fetch('/api/actions', { headers: makeHeaders() })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to load corrective actions.'); return }
      setActions(data.actions || [])
    } catch { setError('Network error loading corrective actions.') }
    finally { setLoading(false) }
  }, [makeHeaders])

  useEffect(() => { fetchActions() }, [fetchActions])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true); setError(null); setSuccess(null)
    try {
      const res = await fetch('/api/actions', {
        method: 'POST', headers: makeHeaders(),
        body: JSON.stringify({
          title: title.trim(), description: description.trim() || null,
          severity, due_date: dueDate || null,
        }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to create action.'); return }
      setSuccess(`Action "${title.trim()}" created.`)
      setTitle(''); setDescription(''); setSeverity('medium'); setDueDate(''); setShowForm(false)
      await fetchActions()
    } catch { setError('Network error creating action.') }
    finally { setSaving(false) }
  }

  const transition = async (a: Action, to: Status) => {
    setBusyId(a.id); setError(null); setSuccess(null)
    try {
      const res = await fetch(`/api/actions/${a.id}/transition`, {
        method: 'POST', headers: makeHeaders(), body: JSON.stringify({ to_status: to }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Transition failed.'); return }
      setSuccess(`"${a.title}" → ${STATUS_LABEL[to]}.`)
      await fetchActions()
      if (expanded === a.id) await loadEvents(a.id)
    } catch { setError('Network error updating action.') }
    finally { setBusyId(null) }
  }

  const loadEvents = async (id: string) => {
    try {
      const res = await fetch(`/api/actions/${id}`, { headers: makeHeaders() })
      const data = await res.json()
      if (res.ok) setEvents(prev => ({ ...prev, [id]: data.events || [] }))
    } catch { /* ignore */ }
  }

  const toggleExpand = (id: string) => {
    if (expanded === id) { setExpanded(null); return }
    setExpanded(id); if (!events[id]) loadEvents(id)
  }

  const counts = actions.reduce((acc, a) => { acc[a.status] = (acc[a.status] || 0) + 1; return acc }, {} as Record<string, number>)
  const openCount = (counts.open || 0) + (counts.in_progress || 0)

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader title="Corrective Actions" subtitle="Assign, track, and approve corrective actions with an immutable audit trail" />

      {error && <div style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #fecaca' }}>{error}</div>}
      {success && <div style={{ background: COLORS.greenBg, color: COLORS.greenFg, padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #86efac' }}>{success}</div>}

      <div className="grid-cols-3" style={{ marginBottom: 24 }}>
        <MetricCard label="Open / In Progress" value={openCount} valueColor={openCount ? COLORS.amberFg : COLORS.greenFg} />
        <MetricCard label="Pending Approval" value={counts.pending_approval || 0} valueColor={(counts.pending_approval || 0) ? COLORS.navy : COLORS.slate} />
        <MetricCard label="Closed" value={counts.closed || 0} valueColor={COLORS.greenFg} />
      </div>

      <div className="glass-card" style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: 16 }}>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Action Register</h2>
          {canCreate && (
            <button onClick={() => setShowForm(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 0.85rem', fontSize: '0.875rem' }}>
              <Plus size={15} />{showForm ? 'Cancel' : 'New Action'}
            </button>
          )}
        </div>

        {canCreate && showForm && (
          <form onSubmit={handleCreate} style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '1rem', marginBottom: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ ...fieldStyle, flex: '2 1 240px' }}>
              <label style={labelStyle}>Title *</label>
              <input required placeholder="e.g. Replace failing aerator, Lagoon 3" value={title} onChange={e => setTitle(e.target.value)} style={inputStyle} />
            </div>
            <div style={{ ...fieldStyle, flex: '1 1 130px' }}>
              <label style={labelStyle}>Severity</label>
              <select value={severity} onChange={e => setSeverity(e.target.value)} style={inputStyle}>
                {['info', 'low', 'medium', 'high', 'critical'].map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div style={{ ...fieldStyle, flex: '1 1 150px' }}>
              <label style={labelStyle}>Due date</label>
              <input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} style={inputStyle} />
            </div>
            <div style={{ ...fieldStyle, flex: '3 1 100%' }}>
              <label style={labelStyle}>Description</label>
              <input placeholder="What needs doing and why" value={description} onChange={e => setDescription(e.target.value)} style={inputStyle} />
            </div>
            <button type="submit" disabled={saving || !title.trim()} style={{ padding: '0.45rem 1.1rem', fontSize: '0.875rem' }}>{saving ? 'Creating…' : 'Create Action'}</button>
          </form>
        )}

        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: COLORS.slate, fontSize: '0.9rem' }}>Loading actions…</div>
        ) : actions.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: COLORS.slateLight, fontSize: '0.9rem' }}>
            No corrective actions yet.{canCreate ? ' Use “New Action” to create the first one.' : ''}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
              <thead><tr>{['', 'Title', 'Severity', 'Status', 'Due', 'Actions'].map(h => <th key={h} style={tableHeaderStyle}>{h}</th>)}</tr></thead>
              <tbody>
                {actions.map(a => (
                  <React.Fragment key={a.id}>
                    <tr>
                      <td style={{ ...tableCellStyle, cursor: 'pointer', width: 28 }} onClick={() => toggleExpand(a.id)}>
                        {expanded === a.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                      </td>
                      <td style={{ ...tableCellStyle, fontWeight: 600, color: COLORS.navy }}>{a.title}</td>
                      <td style={{ ...tableCellStyle, textTransform: 'capitalize' }}>{a.severity || '—'}</td>
                      <td style={tableCellStyle}><StatusBadge tone={STATUS_TONE[a.status]} variant="count">{STATUS_LABEL[a.status]}</StatusBadge></td>
                      <td style={{ ...tableCellStyle, whiteSpace: 'nowrap', color: COLORS.slate }}>{a.due_date || '—'}</td>
                      <td style={{ ...tableCellStyle, whiteSpace: 'nowrap' }}>
                        <span style={{ display: 'inline-flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                          {TRANSITIONS[a.status].filter(([, , perm]) => hasPermission(role, perm)).map(([to, label]) => (
                            <Button key={to} size="sm" disabled={busyId === a.id} onClick={() => transition(a, to)}
                              variant={to === 'closed' ? 'primary' : to === 'cancelled' ? 'destructive' : 'navy'}
                              style={{ padding: '3px 10px', fontSize: '0.78rem' }}>
                              {label}
                            </Button>
                          ))}
                          {TRANSITIONS[a.status].length === 0 && <span style={{ color: COLORS.slateLight, fontSize: '0.8rem' }}>—</span>}
                        </span>
                      </td>
                    </tr>
                    {expanded === a.id && (
                      <tr>
                        <td colSpan={6} style={{ background: COLORS.surface, padding: '12px 20px', borderBottom: '1px solid #f1f5f9' }}>
                          {a.description && <p style={{ margin: '0 0 10px', fontSize: '0.85rem', color: '#374151' }}>{a.description}</p>}
                          <p style={{ ...labelStyle, marginBottom: 6 }}>History</p>
                          {(events[a.id] || []).length === 0 ? (
                            <p style={{ fontSize: '0.8rem', color: COLORS.slateLight, margin: 0 }}>Loading…</p>
                          ) : (
                            <ul style={{ margin: 0, paddingLeft: 18, fontSize: '0.82rem', color: '#374151', lineHeight: 1.7 }}>
                              {(events[a.id] || []).map(ev => (
                                <li key={ev.id}>
                                  <strong>{ev.event_type}</strong>
                                  {ev.from_status && ev.to_status && <> · {ev.from_status} → {ev.to_status}</>}
                                  {ev.note && <> · {ev.note}</>}
                                  <span style={{ color: COLORS.slateLight }}> · {new Date(ev.created_at).toLocaleString()}</span>
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
