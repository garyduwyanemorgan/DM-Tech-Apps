import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { hasPermission } from '../lib/permissions'
import { PageHeader } from './PageHeader'
import { COLORS, tableHeaderStyle, tableCellStyle, inputStyle, labelStyle, fieldStyle } from '../lib/ui'
import { Button } from './ui'
import { Plus, Wrench } from 'lucide-react'

interface Asset { id: string; name: string; asset_type: string | null; config: Record<string, unknown> | null }

export const Assets: React.FC = () => {
  const { organizationId, token, role } = useAuth()
  const canConfigure = hasPermission(role, 'assets.configure')

  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState(''); const [type, setType] = useState('pump'); const [saving, setSaving] = useState(false)
  const [maintFor, setMaintFor] = useState<string | null>(null)
  const [interval, setInterval] = useState(''); const [nextDue, setNextDue] = useState('')

  const makeHeaders = useCallback((): HeadersInit => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [token, organizationId])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await fetch('/api/assets', { headers: makeHeaders() })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to load assets.'); return }
      setAssets(data.assets || [])
    } catch { setError('Network error loading assets.') }
    finally { setLoading(false) }
  }, [makeHeaders])

  useEffect(() => { load() }, [load])

  const createAsset = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true); setError(null); setSuccess(null)
    try {
      const res = await fetch('/api/assets', { method: 'POST', headers: makeHeaders(), body: JSON.stringify({ name: name.trim(), asset_type: type }) })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to create asset.'); return }
      setSuccess(`Asset "${name}" configured.`); setName(''); setShowForm(false); await load()
    } catch { setError('Network error creating asset.') }
    finally { setSaving(false) }
  }

  const createSchedule = async (assetId: string) => {
    setError(null); setSuccess(null)
    try {
      const res = await fetch(`/api/assets/${assetId}/maintenance`, {
        method: 'POST', headers: makeHeaders(),
        body: JSON.stringify({ interval_days: interval ? parseInt(interval) : null, next_due: nextDue || null }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to add schedule.'); return }
      setSuccess('Maintenance schedule added.'); setMaintFor(null); setInterval(''); setNextDue('')
    } catch { setError('Network error adding schedule.') }
  }

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader title="Assets & Maintenance" subtitle="Equipment, inspection checklists, and maintenance schedules" />

      {error && <div style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #fecaca' }}>{error}</div>}
      {success && <div style={{ background: COLORS.greenBg, color: COLORS.greenFg, padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #86efac' }}>{success}</div>}

      <div className="glass-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: 16 }}>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Asset Register</h2>
          {canConfigure && (
            <button onClick={() => setShowForm(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 0.85rem', fontSize: '0.875rem' }}>
              <Plus size={15} />{showForm ? 'Cancel' : 'New Asset'}
            </button>
          )}
        </div>

        {canConfigure && showForm && (
          <form onSubmit={createAsset} style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '1rem', marginBottom: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ ...fieldStyle, flex: '2 1 220px' }}><label style={labelStyle}>Name *</label><input required value={name} onChange={e => setName(e.target.value)} style={inputStyle} placeholder="e.g. Dosing Pump 1" /></div>
            <div style={{ ...fieldStyle, flex: '1 1 160px' }}><label style={labelStyle}>Type</label><select value={type} onChange={e => setType(e.target.value)} style={inputStyle}>{['pump', 'filter', 'dosing', 'aerator', 'water_body'].map(t => <option key={t} value={t}>{t}</option>)}</select></div>
            <button type="submit" disabled={saving || !name.trim()} style={{ padding: '0.45rem 1.1rem', fontSize: '0.875rem' }}>{saving ? 'Saving…' : 'Create Asset'}</button>
          </form>
        )}

        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: COLORS.slate, fontSize: '0.9rem' }}>Loading assets…</div>
        ) : assets.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: COLORS.slateLight, fontSize: '0.9rem' }}>No assets configured yet.{canConfigure ? ' Add one to begin.' : ''}</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 560 }}>
              <thead><tr>{['Asset', 'Type', 'Config', ...(canConfigure ? ['Maintenance'] : [])].map(h => <th key={h} style={tableHeaderStyle}>{h}</th>)}</tr></thead>
              <tbody>
                {assets.map(a => (
                  <React.Fragment key={a.id}>
                    <tr>
                      <td style={{ ...tableCellStyle, fontWeight: 600, color: COLORS.navy }}>{a.name}</td>
                      <td style={{ ...tableCellStyle, textTransform: 'capitalize' }}>{a.asset_type || '—'}</td>
                      <td style={{ ...tableCellStyle, color: COLORS.slate, fontSize: '0.8rem' }}>{a.config ? Object.keys(a.config).join(', ') : '—'}</td>
                      {canConfigure && (
                        <td style={{ ...tableCellStyle }}>
                          <Button variant="secondary" size="sm" onClick={() => setMaintFor(maintFor === a.id ? null : a.id)} style={{ padding: '3px 10px', fontSize: '0.78rem' }}>
                            <Wrench size={12} /> Schedule
                          </Button>
                        </td>
                      )}
                    </tr>
                    {canConfigure && maintFor === a.id && (
                      <tr>
                        <td colSpan={4} style={{ background: COLORS.surface, padding: '12px 20px' }}>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
                            <div style={{ ...fieldStyle, flex: '1 1 140px' }}><label style={labelStyle}>Interval (days)</label><input type="number" value={interval} onChange={e => setInterval(e.target.value)} style={inputStyle} /></div>
                            <div style={{ ...fieldStyle, flex: '1 1 150px' }}><label style={labelStyle}>Next due</label><input type="date" value={nextDue} onChange={e => setNextDue(e.target.value)} style={inputStyle} /></div>
                            <button onClick={() => createSchedule(a.id)} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem' }}>Add Schedule</button>
                          </div>
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
