import React, { useCallback, useEffect, useState } from 'react'
import { PageHeader } from './PageHeader'
import { useAuth } from '../context/AuthContext'
import { COLORS, tableHeaderStyle, tableCellStyle, inputStyle, labelStyle, fieldStyle } from '../lib/ui'
import { Button, StatusBadge } from './ui'
import { Trash2, Plus, MapPin, AlertTriangle, Boxes } from 'lucide-react'

interface SiteInfo {
  id?: string
  name: string
  reading_count: number
  address?: string | null
}

// Mirrors core/assets.py. `equipment` is what you maintain (pumps, filters);
// `sampled` is what a laboratory certificate is about (tanks, water bodies,
// fountains) — and only those carry a specification scope.
type AssetClass = 'equipment' | 'sampled'

interface AssetType {
  key: string
  label: string
  asset_class: AssetClass
  scope?: string | null
  builtin?: boolean
}

interface SiteAsset {
  id: string
  name: string
  asset_type?: string | null
  asset_class?: string | null
  scope?: string | null
}

const SCOPE_LABEL: Record<string, string> = {
  lagoon: 'Lagoon — man-made / closed lagoon limits',
  facilities: 'Facilities management — DM technical guidelines',
}
const scopeShort = (key?: string | null) =>
  key ? (SCOPE_LABEL[key]?.split(' — ')[0] ?? key) : null

// FastAPI hands back either a plain string detail or a validation-error array.
// Both must reach the user verbatim — the /api/assets 422 explains exactly which
// corner of the type/class/scope triangle disagrees, and swallowing it would
// leave the operator staring at a generic failure.
const readDetail = (data: any, fallback: string): string => {
  const d = data?.detail
  if (typeof d === 'string' && d.trim()) return d
  if (Array.isArray(d) && d.length) return d.map((e: any) => e?.msg || String(e)).join('; ')
  return fallback
}

// Keyless Google Maps embed — the classic WordPress-contact-page map. The
// embed geocodes and pins the query itself (address or place name); no Maps
// API key or billing account required. Swap for the JS API only if multi-pin
// becomes a need.
const mapEmbedSrc = (query: string) =>
  `https://maps.google.com/maps?q=${encodeURIComponent(query)}&z=14&output=embed`

// Square map panel whose display always persists. Two stacked iframes are
// double-buffered: the current map stays visible while the next query loads
// invisibly behind it, and they swap only when Google Maps has resolved the
// new pin — so changing site/address just moves the pin, never blanks the
// panel. An empty query keeps whatever map was last shown.
const PersistentMap: React.FC<{ query: string }> = ({ query }) => {
  // Two fixed slots; `front` says which one is visible. The next query loads
  // into the hidden slot and visibility flips only after its onLoad fires, so
  // the panel never shows a half-loaded or blank map. Slots keep their
  // position in the tree — only opacity changes on swap, never a remount.
  const [slots, setSlots] = useState<[string, string]>([query, ''])
  const [front, setFront] = useState<0 | 1>(0)
  const back = (1 - front) as 0 | 1

  useEffect(() => {
    if (!query || query === slots[front] || query === slots[back]) return
    setSlots(s => { const n = [...s] as [string, string]; n[back] = query; return n })
  }, [query, slots, front, back])

  const promote = () => {
    const old = front
    setFront(back)
    setSlots(s => { const n = [...s] as [string, string]; n[old] = ''; return n })
  }

  const loading = slots[back] !== ''
  const empty = slots[0] === '' && slots[1] === ''

  const frame = (slot: 0 | 1) => slots[slot] ? (
    <iframe
      key={slots[slot]}
      title={`Map — ${slots[slot]}`}
      src={mapEmbedSrc(slots[slot])}
      onLoad={slot === back ? promote : undefined}
      referrerPolicy="no-referrer-when-downgrade"
      style={{
        position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0,
        opacity: slot === front ? 1 : 0, pointerEvents: slot === front ? 'auto' : 'none',
        transition: 'opacity 0.25s',
      }}
    />
  ) : null

  return (
    <div style={{
      position: 'relative', width: '100%', maxWidth: 520, aspectRatio: '1 / 1',
      borderRadius: 8, overflow: 'hidden', border: '1px solid #e2e8f0', background: '#f8fafc',
    }}>
      {empty && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', fontSize: '0.85rem' }}>
          Map appears here once a site is pinned.
        </div>
      )}
      {frame(0)}
      {frame(1)}
      {loading && (
        <span style={{ position: 'absolute', top: 8, right: 8, background: 'rgba(255,255,255,0.92)', border: '1px solid #e2e8f0', borderRadius: 6, padding: '2px 8px', fontSize: '0.72rem', color: '#64748b', zIndex: 1 }}>
          Updating map…
        </span>
      )}
    </div>
  )
}

interface SiteManagerProps {
  activeSite: string
  setActiveSite: (site: string) => void
  onSitesChanged?: () => void
  embedded?: boolean
}

export const SiteManager: React.FC<SiteManagerProps> = ({ activeSite, setActiveSite, onSitesChanged, embedded }) => {
  const { organizationId, getToken, email, role } = useAuth()
  const [sites, setSites] = useState<SiteInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Add form state. Volume and salinity are deliberately absent: they are
  // lagoon-only attributes, meaningless for water tanks, fountains, washroom
  // outlets and misting lines. POST /api/sites defaults both server-side.
  const [newName, setNewName]               = useState('')
  const [newAddress, setNewAddress]         = useState('')
  const [adding, setAdding]                 = useState(false)
  const [showAddForm, setShowAddForm]       = useState(false)

  // ── Site infrastructure (assets) ───────────────────────────────────────────
  const [assetTypes, setAssetTypes]   = useState<AssetType[]>([])
  const [openSite, setOpenSite]       = useState<string | null>(null)   // site id
  const [siteAssets, setSiteAssets]   = useState<Record<string, SiteAsset[]>>({})
  const [assetsLoading, setAssetsLoading] = useState(false)
  const [aName, setAName]             = useState('')
  const [aType, setAType]             = useState('')
  const [aScope, setAScope]           = useState('')
  const [scopeFromRegister, setScopeFromRegister] = useState(false)
  const [savingAsset, setSavingAsset] = useState(false)

  // Debounced copy of the address being typed — drives the live pin preview
  // without reloading the map iframe on every keystroke.
  const [previewAddress, setPreviewAddress] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setPreviewAddress(newAddress.trim()), 600)
    return () => clearTimeout(t)
  }, [newAddress])

  // Delete confirmation
  const [pendingDelete, setPendingDelete]   = useState<SiteInfo | null>(null)
  const [deleting, setDeleting]             = useState(false)

  const isAdmin = role === 'admin' || role === 'super_admin'

  // Fetch a FRESH token per request — the cached one can be expired, which the
  // backend treats as an anonymous operator (→ 403 on admin-only writes).
  const makeHeaders = useCallback(async (): Promise<HeadersInit> => {
    const h: HeadersInit = { 'Content-Type': 'application/json' }
    const t = await getToken()
    if (t) h['Authorization'] = `Bearer ${t}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    if (email) h['X-User-Email'] = email
    return h
  }, [getToken, organizationId, email])

  const fetchSites = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/sites', { headers: await makeHeaders() })
      const data = await res.json()
      if (data.sites) {
        const normalised: SiteInfo[] = data.sites.map((s: any) =>
          typeof s === 'string' ? { name: s, reading_count: 0 } : s
        )
        setSites(normalised)
      }
    } catch (err) {
      setError('Failed to load sites.')
    } finally {
      setLoading(false)
    }
  }, [makeHeaders])

  useEffect(() => { fetchSites() }, [fetchSites])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newName.trim()) return
    setAdding(true)
    setError(null)
    setSuccess(null)
    try {
      const res = await fetch('/api/sites', {
        method: 'POST',
        headers: await makeHeaders(),
        body: JSON.stringify({
          name: newName.trim(),
          address: newAddress.trim() || null,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || `Server error ${res.status} — failed to create site.`)
      } else {
        setSuccess(`Site "${newName.trim()}" created. Open “Assets” on its row to add the infrastructure on it.`)
        setNewName(''); setNewAddress('')
        setShowAddForm(false)
        await fetchSites()
        onSitesChanged?.()
      }
    } catch (err) {
      setError('Network error — could not create site.')
    } finally {
      setAdding(false)
    }
  }

  // The type vocabulary is NEVER hardcoded here: /api/asset-types merges the
  // built-in taxonomy with the organisation's own types from Settings → Asset
  // Register, which is what keeps this page and that register in step.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/asset-types', { headers: await makeHeaders() })
        const data = await res.json()
        if (!cancelled && res.ok && Array.isArray(data?.types)) setAssetTypes(data.types)
      } catch { /* the panel says so when the list is empty */ }
    })()
    return () => { cancelled = true }
  }, [makeHeaders])

  const chosenType = assetTypes.find(t => t.key === aType) || null
  const derivedClass: AssetClass | null = chosenType ? chosenType.asset_class : null

  // Class is DERIVED from the type, never asked for, so the two cannot disagree.
  // Scope follows the same rule: equipment gets none at all, and a sampled type
  // that declares one in the register prefills it (copied by value — editing the
  // type later must not re-judge certificates already filed).
  const chooseType = (key: string) => {
    setAType(key)
    const t = assetTypes.find(x => x.key === key)
    if (!t || t.asset_class !== 'sampled') { setAScope(''); setScopeFromRegister(false); return }
    setAScope(t.scope || '')
    setScopeFromRegister(!!t.scope)
  }

  const loadSiteAssets = useCallback(async (siteId: string) => {
    setAssetsLoading(true)
    try {
      const res = await fetch(`/api/assets?site_id=${encodeURIComponent(siteId)}`, { headers: await makeHeaders() })
      const data = await res.json()
      if (!res.ok) { setError(readDetail(data, 'Failed to load assets for this site.')); return }
      setSiteAssets(prev => ({ ...prev, [siteId]: data.assets || [] }))
    } catch {
      setError('Network error — could not load this site’s assets.')
    } finally {
      setAssetsLoading(false)
    }
  }, [makeHeaders])

  const toggleSiteAssets = (site: SiteInfo) => {
    setError(null); setSuccess(null)
    if (!site.id) { setError(`Site "${site.name}" has no identifier yet — reload the page and try again.`); return }
    if (openSite === site.id) { setOpenSite(null); return }
    setOpenSite(site.id)
    setAName(''); setAType(''); setAScope(''); setScopeFromRegister(false)
    loadSiteAssets(site.id)
  }

  const handleAddAsset = async (siteId: string) => {
    if (!aName.trim() || !aType) return
    setSavingAsset(true); setError(null); setSuccess(null)
    try {
      const res = await fetch('/api/assets', {
        method: 'POST',
        headers: await makeHeaders(),
        body: JSON.stringify({
          name: aName.trim(),
          site_id: siteId,
          asset_type: aType,
          asset_class: derivedClass,
          scope: derivedClass === 'sampled' ? (aScope || null) : null,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        // 422 names the exact type/class/scope disagreement — show it as written.
        setError(readDetail(data, `Server error ${res.status} — failed to add the asset.`))
        return
      }
      setSuccess(`Asset "${aName.trim()}" added to this site.`)
      setAName(''); setAType(''); setAScope(''); setScopeFromRegister(false)
      await loadSiteAssets(siteId)
    } catch {
      setError('Network error — could not add the asset.')
    } finally {
      setSavingAsset(false)
    }
  }

  const handleDelete = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    setError(null)
    setSuccess(null)
    try {
      const res = await fetch(`/api/sites/${encodeURIComponent(pendingDelete.name)}`, {
        method: 'DELETE',
        headers: await makeHeaders(),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Failed to delete site.')
      } else {
        setSuccess(data.message || `Site "${pendingDelete.name}" deleted.`)
        if (activeSite === pendingDelete.name) setActiveSite('')
        setPendingDelete(null)
        await fetchSites()
        onSitesChanged?.()
      }
    } catch (err) {
      setError('Network error — could not delete site.')
    } finally {
      setDeleting(false)
    }
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {!embedded && (
        <PageHeader
          title="Site Manager"
          subtitle="Add, configure, and remove monitoring sites for your organisation"
        />
      )}

      {/* Role guard notice */}
      {!isAdmin && (
        <div style={{ background: '#FFEB9C', color: '#856404', padding: '0.75rem 1rem', borderRadius: 6, fontSize: '0.875rem', border: '1px solid #fcd34d', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <AlertTriangle size={16} />
          Site management requires Admin access. Contact your administrator to add or remove sites.
        </div>
      )}

      {/* Feedback banners */}
      {error   && <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.75rem 1rem', borderRadius: 6, fontSize: '0.875rem', border: '1px solid #fecaca' }}>{error}</div>}
      {success && <div style={{ background: '#C6EFCE', color: '#006100', padding: '0.75rem 1rem', borderRadius: 6, fontSize: '0.875rem', border: '1px solid #86efac' }}>{success}</div>}

      {/* Sites list */}
      <div className="glass-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <h2 style={{ fontSize: '1.05rem', margin: 0 }}>
            Configured Sites
            {!loading && <span style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 400, marginLeft: '0.5rem' }}>({sites.length})</span>}
          </h2>
          {isAdmin && (
            <button
              onClick={() => { setShowAddForm(v => !v); setError(null); setSuccess(null) }}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 0.85rem', fontSize: '0.875rem' }}
            >
              <Plus size={15} />
              {showAddForm ? 'Cancel' : 'Add Site'}
            </button>
          )}
        </div>

        {/* Add site form */}
        {showAddForm && isAdmin && (
          <form onSubmit={handleAdd} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '1rem', marginBottom: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ flex: '2 1 180px', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              <label htmlFor="site-name" style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Site Name *</label>
              <input
                id="site-name"
                type="text"
                required
                placeholder="e.g. Dubai Safari Park"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                maxLength={80}
                style={{ padding: '0.45rem 0.75rem', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: '0.875rem', fontFamily: 'inherit' }}
              />
            </div>
            <div style={{ flex: '1 1 100%', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              <label htmlFor="site-address" style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Address</label>
              <input
                id="site-address"
                type="text"
                placeholder="e.g. Mohammed Bin Rashid City, District One, Dubai"
                value={newAddress}
                onChange={e => setNewAddress(e.target.value)}
                maxLength={300}
                style={{ padding: '0.45rem 0.75rem', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: '0.875rem', fontFamily: 'inherit' }}
              />
              <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                Pinned live on the Site Map below as you type — check the pin lands on the right spot before creating.
              </span>
            </div>

            <button type="submit" disabled={adding || !newName.trim()} style={{ padding: '0.45rem 1.1rem', fontSize: '0.875rem', alignSelf: 'flex-end' }}>
              {adding ? 'Creating…' : 'Create Site'}
            </button>
          </form>
        )}

        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b', fontSize: '0.875rem' }}>Loading sites…</div>
        ) : sites.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.875rem' }}>
            <MapPin size={32} style={{ marginBottom: '0.5rem', color: '#cbd5e1' }} />
            <div>No sites configured yet.</div>
            {isAdmin && <div style={{ marginTop: '0.25rem', fontSize: '0.78rem' }}>Click "Add Site" to create the first site for your organisation.</div>}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '640px' }}>
              <thead>
                <tr>
                  <th style={TH}>Site Name</th>
                  <th style={TH}>Address</th>
                  <th style={{ ...TH, textAlign: 'right' }}>Readings</th>
                  <th style={{ ...TH, textAlign: 'center' }}>Status</th>
                  <th style={{ ...TH, textAlign: 'center' }}>Infrastructure</th>
                  {isAdmin && <th style={{ ...TH, textAlign: 'center' }}>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {sites.map(site => {
                  const isActive = site.name === activeSite
                  const isOpen = !!site.id && openSite === site.id
                  const rowAssets = site.id ? siteAssets[site.id] : undefined
                  return (
                    <React.Fragment key={site.name}>
                    <tr>
                      <td style={TD}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <MapPin size={14} color={isActive ? '#27ae60' : '#94a3b8'} />
                          <span style={{ fontWeight: isActive ? 700 : 400, color: isActive ? '#1B3A5C' : '#374151' }}>
                            {site.name}
                          </span>
                        </div>
                      </td>
                      <td style={{ ...TD, maxWidth: 260 }}>
                        <span
                          title={site.address || undefined}
                          style={{
                            display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            fontSize: '0.8rem', color: site.address ? '#64748b' : '#cbd5e1',
                          }}
                        >
                          {site.address || '—'}
                        </span>
                      </td>
                      <td style={{ ...TD, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                        <span style={{ color: site.reading_count > 0 ? '#006100' : '#94a3b8', fontWeight: site.reading_count > 0 ? 600 : 400 }}>
                          {site.reading_count}
                        </span>
                      </td>
                      <td style={{ ...TD, textAlign: 'center' }}>
                        {isActive ? (
                          <span style={{ background: '#C6EFCE', color: '#006100', fontSize: '0.72rem', fontWeight: 700, borderRadius: 4, padding: '2px 8px' }}>ACTIVE</span>
                        ) : (
                          <button
                            className="secondary"
                            onClick={() => setActiveSite(site.name)}
                            style={{ fontSize: '0.75rem', padding: '3px 10px' }}
                          >
                            Select
                          </button>
                        )}
                      </td>
                      <td style={{ ...TD, textAlign: 'center' }}>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => toggleSiteAssets(site)}
                          aria-expanded={isOpen}
                          style={{ fontSize: '0.78rem', padding: '3px 10px' }}
                        >
                          <Boxes size={13} />
                          {isOpen ? 'Hide assets' : 'Assets'}
                          {rowAssets ? ` (${rowAssets.length})` : ''}
                        </Button>
                      </td>
                      {isAdmin && (
                        <td style={{ ...TD, textAlign: 'center' }}>
                          <button
                            onClick={() => { setPendingDelete(site); setError(null); setSuccess(null) }}
                            style={{
                              background: 'transparent',
                              border: '1px solid #fecaca',
                              borderRadius: 6,
                              padding: '4px 10px',
                              cursor: 'pointer',
                              color: '#9C0006',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.35rem',
                              fontSize: '0.78rem',
                              fontFamily: 'inherit',
                            }}
                          >
                            <Trash2 size={13} />
                            Delete
                          </button>
                        </td>
                      )}
                    </tr>

                    {isOpen && site.id && (
                      <tr>
                        <td colSpan={isAdmin ? 6 : 5} style={{ background: COLORS.surface, padding: '14px 18px', borderBottom: '1px solid #f1f5f9' }}>
                          <h3 className="section-heading" style={{ margin: '0 0 0.5rem', fontSize: '0.92rem' }}>
                            Site infrastructure — {site.name}
                          </h3>
                          <p style={{ fontSize: '0.8rem', color: COLORS.slate, lineHeight: 1.6, margin: '0 0 0.9rem', maxWidth: 720 }}>
                            The assets on this site: tanks, water bodies, fountains, washroom outlets,
                            misting lines, and the equipment that serves them. Types come from{' '}
                            <strong>Settings → Asset Register</strong>, so anything added there is offered here.
                          </p>

                          {isAdmin && (
                            <form
                              onSubmit={e => { e.preventDefault(); handleAddAsset(site.id!) }}
                              style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end', marginBottom: '1rem' }}
                            >
                              <div style={{ ...fieldStyle, flex: '2 1 240px' }}>
                                <label htmlFor={`asset-name-${site.id}`} style={labelStyle}>Asset name *</label>
                                <input
                                  id={`asset-name-${site.id}`}
                                  value={aName}
                                  onChange={e => setAName(e.target.value)}
                                  placeholder="e.g. Gate Number 2 - GRP Water Tank"
                                  maxLength={200}
                                  style={inputStyle}
                                  required
                                />
                              </div>

                              <div style={{ ...fieldStyle, flex: '1 1 220px' }}>
                                <label htmlFor={`asset-type-${site.id}`} style={labelStyle}>Type *</label>
                                <select
                                  id={`asset-type-${site.id}`}
                                  value={aType}
                                  onChange={e => chooseType(e.target.value)}
                                  style={inputStyle}
                                  aria-describedby={`asset-class-${site.id}`}
                                  required
                                >
                                  <option value="">Choose a type…</option>
                                  <optgroup label="Sampled — a lab certificate is about it">
                                    {assetTypes.filter(t => t.asset_class === 'sampled').map(t => (
                                      <option key={t.key} value={t.key}>{t.label}</option>
                                    ))}
                                  </optgroup>
                                  <optgroup label="Equipment — maintained, never sampled">
                                    {assetTypes.filter(t => t.asset_class === 'equipment').map(t => (
                                      <option key={t.key} value={t.key}>{t.label}</option>
                                    ))}
                                  </optgroup>
                                </select>
                                {/* Class is shown, never asked for — it is read off the
                                    chosen type so the pair cannot disagree. */}
                                <span id={`asset-class-${site.id}`} style={{ fontSize: '0.75rem', color: COLORS.slate }}>
                                  {derivedClass
                                    ? `Class: ${derivedClass === 'sampled' ? 'Sampled — a lab certificate is about it' : 'Equipment — maintained, never sampled'}`
                                    : 'Class is set by the type you choose.'}
                                </span>
                              </div>

                              {/* Scope decides which specification set a lab result is
                                  judged against. Lagoon and facilities share parameter
                                  names such as pH and turbidity, so a sampled asset with
                                  no scope produces certificates nothing can judge — and a
                                  wrong default would silently judge it against the other
                                  set. Never defaulted; equipment is never offered it. */}
                              {derivedClass === 'sampled' && (
                                <div style={{ ...fieldStyle, flex: '1 1 100%' }}>
                                  <label htmlFor={`asset-scope-${site.id}`} style={labelStyle}>Specification scope</label>
                                  <select
                                    id={`asset-scope-${site.id}`}
                                    value={aScope}
                                    onChange={e => { setAScope(e.target.value); setScopeFromRegister(false) }}
                                    aria-describedby={`asset-scope-help-${site.id}`}
                                    style={{ ...inputStyle, maxWidth: 440 }}
                                  >
                                    <option value="">Not set — results stay unassessed</option>
                                    <option value="facilities">{SCOPE_LABEL.facilities}</option>
                                    <option value="lagoon">{SCOPE_LABEL.lagoon}</option>
                                  </select>
                                  <div id={`asset-scope-help-${site.id}`} style={{ fontSize: '0.78rem', color: COLORS.slate, lineHeight: 1.55, maxWidth: 620 }}>
                                    {scopeFromRegister && (
                                      <strong style={{ color: COLORS.navy }}>
                                        Prefilled from the Asset Register — “{chosenType?.label}” declares this scope. Change it if this asset differs.{' '}
                                      </strong>
                                    )}
                                    Scope decides which specification a result is judged against. The lagoon and
                                    facilities sets share parameter names — pH and turbidity appear in both — so a
                                    sampled asset left without a scope produces certificates nothing can judge.
                                  </div>
                                </div>
                              )}

                              <Button type="submit" size="sm" disabled={savingAsset || !aName.trim() || !aType}>
                                <Plus size={13} /> {savingAsset ? 'Adding…' : 'Add asset'}
                              </Button>
                            </form>
                          )}

                          {assetsLoading && !rowAssets ? (
                            <div style={{ fontSize: '0.85rem', color: COLORS.slate }}>Loading assets…</div>
                          ) : !rowAssets || rowAssets.length === 0 ? (
                            <div style={{ fontSize: '0.85rem', color: COLORS.slateLight }}>
                              No assets on this site yet.{isAdmin ? ' Add the first one above.' : ''}
                            </div>
                          ) : (
                            <div style={{ overflowX: 'auto' }}>
                              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 560 }}>
                                <thead><tr>{['Asset', 'Type', 'Class', 'Scope'].map(h => (
                                  <th key={h} style={tableHeaderStyle}>{h}</th>))}</tr></thead>
                                <tbody>
                                  {rowAssets.map(a => (
                                    <tr key={a.id}>
                                      <th scope="row" style={{ ...tableCellStyle, textAlign: 'left', fontWeight: 600, color: COLORS.navy }}>{a.name}</th>
                                      <td style={tableCellStyle}>
                                        {assetTypes.find(t => t.key === a.asset_type)?.label || a.asset_type || '—'}
                                      </td>
                                      <td style={tableCellStyle}>
                                        <StatusBadge tone={a.asset_class === 'sampled' ? 'blue' : 'slate'} variant="count">
                                          {a.asset_class === 'sampled' ? 'Sampled' : 'Equipment'}
                                        </StatusBadge>
                                      </td>
                                      <td style={{ ...tableCellStyle, color: a.scope ? '#374151' : COLORS.slateLight }}>
                                        {a.asset_class === 'equipment'
                                          ? <span title="Equipment is maintained, not judged against limits.">Not applicable</span>
                                          : a.scope
                                            ? scopeShort(a.scope)
                                            : <span title="No scope — results for this asset stay unassessed.">Not set</span>}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Site Map — the ONE map, always present, display persisted. While the
          Add form has an address typed it previews that pin; otherwise it pins
          the ACTIVE site, re-pinning immediately on Select. A site without a
          stored address falls back to a Google Maps lookup of its NAME, with a
          small "no address configured" note. */}
      {(() => {
        const active = sites.find(s => s.name === activeSite)
        const previewing = showAddForm && previewAddress !== ''
        const query = previewing ? previewAddress : active ? (active.address || active.name) : ''
        return (
          <div className="glass-card">
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.6rem', marginBottom: '0.85rem', flexWrap: 'wrap' }}>
              <h2 style={{ fontSize: '1.05rem', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <MapPin size={16} color={previewing ? '#f39c12' : '#27ae60'} />
                Site Map
              </h2>
              <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                {previewing
                  ? `Previewing new site address — ${previewAddress}`
                  : active ? `${active.name}${active.address ? ` — ${active.address}` : ''}` : 'Select a site above to pin it on the map.'}
              </span>
              {!previewing && active && !active.address && (
                <span style={{ fontSize: '0.75rem', color: '#856404', background: '#FFEB9C', border: '1px solid #fcd34d', borderRadius: 4, padding: '1px 8px' }}>
                  No address configured — pinned by site name
                </span>
              )}
            </div>
            <PersistentMap query={query} />
          </div>
        )
      })()}

      {/* Info box */}
      <div style={{ background: '#D6E4F0', border: '1px solid #93c5fd', borderRadius: 8, padding: '0.85rem 1rem', fontSize: '0.82rem', color: '#1B3A5C', lineHeight: 1.6 }}>
        <strong>About sites:</strong> A site is a location you monitor; the things on it — water bodies, tanks,
        fountains, washroom outlets, misting lines and the equipment serving them — are its assets, added from the
        <strong> Infrastructure</strong> button on each row. Lab readings are stored per site per month. Only
        administrators can add or delete sites and assets. Deleting a site permanently removes all associated
        readings and cannot be undone.
      </div>

      {/* Delete confirmation modal */}
      {pendingDelete && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem',
        }}>
          <div style={{ background: '#fff', borderRadius: 12, padding: '2rem', maxWidth: 440, width: '100%', boxShadow: '0 20px 60px rgba(0,0,0,0.25)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
              <div style={{ background: '#FFF0F0', borderRadius: '50%', padding: '0.6rem', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <AlertTriangle size={22} color="#9C0006" />
              </div>
              <h3 style={{ margin: 0, fontSize: '1.05rem', color: '#1B3A5C' }}>Delete Site</h3>
            </div>

            <p style={{ color: '#374151', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '0.5rem' }}>
              You are about to permanently delete <strong>"{pendingDelete.name}"</strong>.
            </p>

            {pendingDelete.reading_count > 0 ? (
              <div style={{ background: '#FFC7CE', color: '#9C0006', borderRadius: 6, padding: '0.65rem 0.85rem', fontSize: '0.875rem', marginBottom: '1.25rem', border: '1px solid #fecaca' }}>
                <strong>Warning:</strong> This will also delete{' '}
                <strong>{pendingDelete.reading_count} reading{pendingDelete.reading_count !== 1 ? 's' : ''}</strong>{' '}
                stored for this site. This action cannot be undone.
              </div>
            ) : (
              <div style={{ background: '#FFEB9C', color: '#856404', borderRadius: 6, padding: '0.65rem 0.85rem', fontSize: '0.875rem', marginBottom: '1.25rem', border: '1px solid #fcd34d' }}>
                This site has no readings. Deletion is safe and permanent.
              </div>
            )}

            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                className="secondary"
                onClick={() => setPendingDelete(null)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                style={{ background: '#9C0006', color: '#fff', border: 'none' }}
              >
                {deleting ? 'Deleting…' : `Delete "${pendingDelete.name}"`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
