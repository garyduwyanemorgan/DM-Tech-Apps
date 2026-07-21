import React, { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { COLORS, tableHeaderStyle, tableCellStyle, inputStyle, labelStyle, fieldStyle } from '../lib/ui'
import { Button, StatusBadge } from './ui'

/**
 * Settings → Asset Register: the asset *taxonomy*.
 *
 * This defines the types available when adding an asset under Assets &
 * Maintenance. Asset instances live there; only the vocabulary lives here.
 *
 * Two things a type must declare, and why:
 *
 *  class  equipment is what you maintain (pumps, filters); sampled is what a
 *         laboratory certificate is about (tanks, water bodies, fountains).
 *         Nobody takes a sample from a dosing pump.
 *  scope  which specification set governs it — required for sampled types,
 *         forbidden for equipment. The two scopes share parameter names such as
 *         pH and turbidity, so a sampled type that cannot say which set applies
 *         produces certificates nothing can judge.
 *
 * Assets copy class and scope from the type when created, so editing a type here
 * never silently re-judges certificates already filed against existing assets.
 */

type AssetClass = 'equipment' | 'sampled'

interface AssetType {
  key: string
  label: string
  asset_class: AssetClass
  scope?: string | null
  builtin?: boolean
}

const SCOPE_LABEL: Record<string, string> = {
  lagoon: 'Lagoon — man-made / closed lagoon limits',
  facilities: 'Facilities management — DM technical guidelines',
}

export const AssetRegisterPanel: React.FC<{
  organizationId: string | null
  token: string | null
}> = ({ organizationId, token }) => {
  const [types, setTypes] = useState<AssetType[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [showForm, setShowForm] = useState(false)
  const [label, setLabel] = useState('')
  const [assetClass, setAssetClass] = useState<AssetClass>('sampled')
  const [scope, setScope] = useState('facilities')
  const [saving, setSaving] = useState(false)

  const headers = useCallback((): HeadersInit => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [token, organizationId])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await fetch('/api/asset-types', { headers: headers() })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to load the asset register.'); return }
      setTypes(data.types || [])
    } catch { setError('Network error loading the asset register.') }
    finally { setLoading(false) }
  }, [headers])

  useEffect(() => { load() }, [load])

  // Equipment carries no scope at all, so clear it on the way there rather than
  // sending a value the API would reject.
  const changeClass = (next: AssetClass) => {
    setAssetClass(next)
    if (next === 'equipment') setScope('')
    else if (!scope) setScope('facilities')
  }

  const create = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true); setError(null); setSuccess(null)
    try {
      const res = await fetch('/api/asset-types', {
        method: 'POST', headers: headers(),
        body: JSON.stringify({
          label: label.trim(),
          asset_class: assetClass,
          scope: assetClass === 'sampled' ? scope : null,
        }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to add the asset type.'); return }
      setSuccess(`Asset type "${data.label}" added.`)
      setLabel(''); setShowForm(false); await load()
    } catch { setError('Network error adding the asset type.') }
    finally { setSaving(false) }
  }

  const remove = async (t: AssetType) => {
    setError(null); setSuccess(null)
    try {
      const res = await fetch(`/api/asset-types/${encodeURIComponent(t.key)}`, {
        method: 'DELETE', headers: headers(),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to remove the asset type.'); return }
      setSuccess(`Asset type "${t.label}" removed. Existing assets are unaffected.`)
      await load()
    } catch { setError('Network error removing the asset type.') }
  }

  const sampled = types.filter(t => t.asset_class === 'sampled')

  return (
    <div className="glass-card">
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 className="section-heading" style={{ marginTop: 0, marginBottom: 0 }}>Asset Register</h3>
        <Button variant="secondary" size="sm" onClick={() => setShowForm(v => !v)}>
          <Plus size={14} /> {showForm ? 'Cancel' : 'Add asset type'}
        </Button>
      </div>

      <p style={{ fontSize: '0.85rem', color: COLORS.slate, lineHeight: 1.6, margin: '0.75rem 0 1.1rem' }}>
        The types available when adding an asset under <strong>Assets &amp; Maintenance</strong>.
        Sampled types are the ones a laboratory certificate can be about — the{' '}
        {sampled.length} listed here are what the Upload Report asset dropdown is built from.
      </p>

      {error && <div role="alert" style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.65rem 0.95rem', borderRadius: 6, marginBottom: '0.9rem', fontSize: '0.85rem' }}>{error}</div>}
      {success && <div style={{ background: COLORS.greenBg, color: COLORS.greenFg, padding: '0.65rem 0.95rem', borderRadius: 6, marginBottom: '0.9rem', fontSize: '0.85rem' }}>{success}</div>}

      {showForm && (
        <form onSubmit={create} style={{ background: COLORS.surface, borderRadius: 8, padding: '1rem', marginBottom: '1.1rem' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ ...fieldStyle, flex: '2 1 200px' }}>
              <label htmlFor="at-label" style={labelStyle}>Name</label>
              <input id="at-label" value={label} onChange={e => setLabel(e.target.value)}
                     placeholder="e.g. GRP Tank" style={inputStyle} required />
            </div>
            <div style={{ ...fieldStyle, flex: '1 1 160px' }}>
              <label htmlFor="at-class" style={labelStyle}>Class</label>
              <select id="at-class" value={assetClass}
                      onChange={e => changeClass(e.target.value as AssetClass)} style={inputStyle}>
                <option value="sampled">Sampled — a certificate is about it</option>
                <option value="equipment">Equipment — maintained, never sampled</option>
              </select>
            </div>
            {assetClass === 'sampled' && (
              <div style={{ ...fieldStyle, flex: '2 1 240px' }}>
                <label htmlFor="at-scope" style={labelStyle}>Specification scope</label>
                <select id="at-scope" value={scope} onChange={e => setScope(e.target.value)} style={inputStyle}>
                  <option value="facilities">{SCOPE_LABEL.facilities}</option>
                  <option value="lagoon">{SCOPE_LABEL.lagoon}</option>
                </select>
              </div>
            )}
            <Button type="submit" size="sm" disabled={saving || !label.trim()}>
              {saving ? 'Adding…' : 'Add type'}
            </Button>
          </div>
          <p style={{ fontSize: '0.78rem', color: COLORS.slate, margin: '0.75rem 0 0', lineHeight: 1.55 }}>
            {assetClass === 'sampled'
              ? 'Scope decides which specification a result is judged against. The two scopes share parameter names such as pH and turbidity, so a type without one produces certificates nothing can judge.'
              : 'Equipment is maintained, never judged against limits, so it carries no scope.'}
          </p>
        </form>
      )}

      {loading ? (
        <div style={{ padding: '1.5rem', textAlign: 'center', color: COLORS.slateLight, fontSize: '0.9rem' }}>Loading…</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 620 }}>
            <thead><tr>{['Type', 'Class', 'Scope', 'Source', ''].map((h, i) =>
              <th key={i} style={tableHeaderStyle}>{h}</th>)}</tr></thead>
            <tbody>
              {types.map(t => (
                <tr key={t.key}>
                  <th scope="row" style={{ ...tableCellStyle, textAlign: 'left', fontWeight: 600, color: COLORS.navy }}>
                    {t.label}
                  </th>
                  <td style={tableCellStyle}>
                    <StatusBadge tone={t.asset_class === 'sampled' ? 'blue' : 'slate'} variant="count">
                      {t.asset_class === 'sampled' ? 'Sampled' : 'Equipment'}
                    </StatusBadge>
                  </td>
                  <td style={{ ...tableCellStyle, color: t.scope ? '#374151' : COLORS.slateLight }}>
                    {t.asset_class === 'equipment'
                      ? <span title="Equipment is maintained, not judged against limits.">—</span>
                      : t.scope
                        ? (SCOPE_LABEL[t.scope]?.split(' — ')[0] ?? t.scope)
                        : <span title="No scope — certificates against this type cannot be judged.">—</span>}
                  </td>
                  <td style={{ ...tableCellStyle, fontSize: '0.8rem', color: COLORS.slate }}>
                    {t.builtin === false ? 'Added here' : 'Built in'}
                  </td>
                  <td style={tableCellStyle}>
                    {t.builtin === false && (
                      <Button variant="secondary" size="sm" onClick={() => remove(t)}
                              style={{ padding: '3px 9px', fontSize: '0.76rem' }}>
                        <Trash2 size={12} /> Remove
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
