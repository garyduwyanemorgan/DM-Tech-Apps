import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { hasPermission } from '../lib/permissions'
import { PageHeader } from './PageHeader'
import { COLORS, tableHeaderStyle, tableCellStyle, inputStyle, labelStyle, fieldStyle } from '../lib/ui'
import { Button } from './ui'
import { Plus, Wrench } from 'lucide-react'

interface Asset {
  id: string
  name: string
  asset_type: string | null
  asset_class?: string | null
  scope?: string | null
  config: Record<string, unknown> | null
}

// Mirrors core/assets.py. Two different kinds of thing used to share one flat
// list: equipment is *maintained* and never sampled; sampled assets are what a
// laboratory certificate is about, and only those carry a specification scope.
type AssetClass = 'equipment' | 'sampled'

const ASSET_CLASSES: { key: AssetClass; label: string; hint: string }[] = [
  { key: 'equipment', label: 'Equipment', hint: 'Maintained — never sampled' },
  { key: 'sampled', label: 'Sampled', hint: 'A lab certificate is about it' },
]

// Fallback only. The authoritative list comes from /api/asset-types (Settings →
// Asset Register), which merges these built-ins with the organisation's own. Kept
// here so the form still works if that call fails.
const FALLBACK_TYPES: { key: string; label: string; assetClass: AssetClass }[] = [
  { key: 'pump', label: 'Pump', assetClass: 'equipment' },
  { key: 'filter', label: 'Filter', assetClass: 'equipment' },
  { key: 'dosing', label: 'Dosing unit', assetClass: 'equipment' },
  { key: 'aerator', label: 'Aerator', assetClass: 'equipment' },
  { key: 'water_body', label: 'Water body / lagoon', assetClass: 'sampled' },
  { key: 'water_tank', label: 'Water tank', assetClass: 'sampled' },
  { key: 'fountain', label: 'Fountain', assetClass: 'sampled' },
  { key: 'washroom_outlet', label: 'Washroom outlet', assetClass: 'sampled' },
  { key: 'misting_line', label: 'Misting line', assetClass: 'sampled' },
]

const SCOPES: { key: string; label: string }[] = [
  { key: 'lagoon', label: 'Lagoon — man-made / closed lagoon limits' },
  { key: 'facilities', label: 'Facilities management — DM technical guidelines' },
]

const typeLabelFrom = (
  list: { key: string; label: string }[], key: string | null | undefined,
) => list.find(t => t.key === key)?.label || key || '—'
const classLabel = (key: string | null | undefined) =>
  ASSET_CLASSES.find(c => c.key === key)?.label || key || '—'
const scopeShortLabel = (key: string | null | undefined) =>
  SCOPES.find(s => s.key === key)?.label.split('—')[0].trim() || key || '—'

export const Assets: React.FC = () => {
  const { organizationId, token, role } = useAuth()
  const canConfigure = hasPermission(role, 'assets.configure')

  const [assets, setAssets] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState(''); const [type, setType] = useState('pump'); const [saving, setSaving] = useState(false)
  const [assetClass, setAssetClass] = useState<AssetClass>('equipment')
  const [types, setTypes] = useState(FALLBACK_TYPES)
  const [scope, setScope] = useState('')
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
      const [aRes, tRes] = await Promise.all([
        fetch('/api/assets', { headers: makeHeaders() }),
        fetch('/api/asset-types', { headers: makeHeaders() }),
      ])
      const data = await aRes.json()
      if (!aRes.ok) { setError(data.detail || 'Failed to load assets.'); return }
      setAssets(data.assets || [])
      if (tRes.ok) {
        const t = await tRes.json()
        if (Array.isArray(t?.types) && t.types.length) {
          setTypes(t.types.map((x: any) => ({ key: x.key, label: x.label, assetClass: x.asset_class })))
        }
      }
    } catch { setError('Network error loading assets.') }
    finally { setLoading(false) }
  }, [makeHeaders])

  useEffect(() => { load() }, [load])

  const typeLabel = (key: string | null | undefined) => typeLabelFrom(types, key)

  // Changing class re-points the type list, and clears scope on the way to
  // equipment: equipment has no specification scope at all.
  const changeClass = (next: AssetClass) => {
    setAssetClass(next)
    const first = types.find(t => t.assetClass === next)
    setType(first ? first.key : '')
    if (next === 'equipment') setScope('')
  }

  const createAsset = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true); setError(null); setSuccess(null)
    try {
      const res = await fetch('/api/assets', {
        method: 'POST', headers: makeHeaders(),
        body: JSON.stringify({
          name: name.trim(),
          asset_type: type,
          asset_class: assetClass,
          scope: assetClass === 'sampled' ? (scope || null) : null,
        }),
      })
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
            <div style={{ ...fieldStyle, flex: '2 1 220px' }}><label htmlFor="asset-name" style={labelStyle}>Name *</label><input id="asset-name" required value={name} onChange={e => setName(e.target.value)} style={inputStyle} placeholder="e.g. Dosing Pump 1" /></div>

            <div style={{ ...fieldStyle, flex: '1 1 180px' }}>
              <label htmlFor="asset-class" style={labelStyle}>Asset class</label>
              <select id="asset-class" value={assetClass} onChange={e => changeClass(e.target.value as AssetClass)} style={inputStyle}>
                {ASSET_CLASSES.map(c => <option key={c.key} value={c.key}>{c.label} — {c.hint}</option>)}
              </select>
            </div>

            <div style={{ ...fieldStyle, flex: '1 1 190px' }}>
              <label htmlFor="asset-type" style={labelStyle}>Type</label>
              <select id="asset-type" value={type} onChange={e => setType(e.target.value)} style={inputStyle}>
                {types.filter(t => t.assetClass === assetClass).map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
            </div>

            {assetClass === 'sampled' && (
              <div style={{ ...fieldStyle, flex: '1 1 100%' }}>
                <label htmlFor="asset-scope" style={labelStyle}>Specification scope</label>
                <select id="asset-scope" aria-describedby="asset-scope-help" value={scope} onChange={e => setScope(e.target.value)} style={{ ...inputStyle, maxWidth: 420 }}>
                  <option value="">Not set — results stay unassessed</option>
                  {SCOPES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                </select>
                <div id="asset-scope-help" style={{ fontSize: '0.78rem', color: '#64748b', lineHeight: 1.5, maxWidth: 560 }}>
                  Scope decides which specification a result is judged against. The two scopes
                  share parameter names — pH and turbidity appear in both — so the wrong scope
                  would compare a reading against limits that do not apply to it. Equipment is
                  maintained, not sampled, so it carries no scope.
                </div>
              </div>
            )}

            <button type="submit" disabled={saving || !name.trim() || !type} style={{ padding: '0.45rem 1.1rem', fontSize: '0.875rem' }}>{saving ? 'Saving…' : 'Create Asset'}</button>
          </form>
        )}

        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: COLORS.slate, fontSize: '0.9rem' }}>Loading assets…</div>
        ) : assets.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: COLORS.slateLight, fontSize: '0.9rem' }}>No assets configured yet.{canConfigure ? ' Add one to begin.' : ''}</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 820 }}>
              <thead><tr>{['Asset', 'Class', 'Type', 'Scope', 'Config', ...(canConfigure ? ['Maintenance'] : [])].map(h => <th key={h} style={tableHeaderStyle}>{h}</th>)}</tr></thead>
              <tbody>
                {assets.map(a => (
                  <React.Fragment key={a.id}>
                    <tr>
                      <td style={{ ...tableCellStyle, fontWeight: 600, color: COLORS.navy }}>{a.name}</td>
                      <td style={tableCellStyle}>{classLabel(a.asset_class)}</td>
                      <td style={tableCellStyle}>{typeLabel(a.asset_type)}</td>
                      <td style={{ ...tableCellStyle, color: a.scope ? '#374151' : COLORS.slateLight }}>
                        {a.asset_class === 'equipment'
                          ? <span title="Equipment is maintained, not sampled — no specification scope applies.">—</span>
                          : a.scope
                            ? scopeShortLabel(a.scope)
                            : <span title="Not set — results for this asset stay unassessed.">—</span>}
                      </td>
                      <td style={{ ...tableCellStyle, color: COLORS.slate, fontSize: '0.8rem' }}>{a.config ? Object.keys(a.config).join(', ') : '—'}</td>
                      {canConfigure && (
                        <td style={{ ...tableCellStyle }}>
                          {/* Maintenance follows from the class. Equipment is what
                              you service; a sampled asset is evidenced by lab
                              certificates, so a backwash schedule on a water body
                              would be a category error. */}
                          {a.asset_class === 'sampled' ? (
                            <span style={{ color: COLORS.slateLight, fontSize: '0.78rem' }}
                                  title="Sampled assets are evidenced by lab certificates, not maintenance schedules.">
                              Certificates
                            </span>
                          ) : (
                            <Button variant="secondary" size="sm" onClick={() => setMaintFor(maintFor === a.id ? null : a.id)} style={{ padding: '3px 10px', fontSize: '0.78rem' }}>
                              <Wrench size={12} /> Schedule
                            </Button>
                          )}
                        </td>
                      )}
                    </tr>
                    {canConfigure && maintFor === a.id && (
                      <tr>
                        <td colSpan={6} style={{ background: COLORS.surface, padding: '12px 20px' }}>
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
