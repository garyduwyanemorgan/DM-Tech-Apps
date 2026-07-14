import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { hasPermission, type Permission } from '../lib/permissions'
import { PageHeader } from './PageHeader'
import { COLORS, tableHeaderStyle, tableCellStyle, inputStyle, labelStyle, fieldStyle } from '../lib/ui'
import { MetricCard, StatusBadge } from './ui'
import { Plus } from 'lucide-react'

interface Item { id: string; name: string; sku: string | null; unit: string | null; reorder_threshold: number | null; unit_cost?: number | null }
interface Location { id: string; name: string; kind: string | null }
interface StockRow { item_id: string; location_id: string; balance: number }

type MoveType = 'receive' | 'consume' | 'transfer' | 'adjust'
const MOVE_PERM: Record<MoveType, Permission> = {
  receive: 'inventory.receive', consume: 'inventory.consume', transfer: 'inventory.transfer', adjust: 'inventory.adjust',
}

export const Inventory: React.FC = () => {
  const { organizationId, token, role } = useAuth()
  const canConfigure = hasPermission(role, 'inventory.configure')
  const canValuation = hasPermission(role, 'inventory.valuation.read')
  const moveTypes = (Object.keys(MOVE_PERM) as MoveType[]).filter(t => hasPermission(role, MOVE_PERM[t]))

  const [items, setItems] = useState<Item[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [stock, setStock] = useState<StockRow[]>([])
  const [valuation, setValuation] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // stock-move form
  const [moveType, setMoveType] = useState<MoveType>(moveTypes[0] || 'receive')
  const [mItem, setMItem] = useState(''); const [mLoc, setMLoc] = useState(''); const [mTo, setMTo] = useState('')
  const [mQty, setMQty] = useState(''); const [mReason, setMReason] = useState(''); const [moving, setMoving] = useState(false)

  // config forms
  const [showItemForm, setShowItemForm] = useState(false)
  const [iName, setIName] = useState(''); const [iSku, setISku] = useState(''); const [iUnit, setIUnit] = useState('')
  const [iCost, setICost] = useState(''); const [iThreshold, setIThreshold] = useState('')
  const [showLocForm, setShowLocForm] = useState(false)
  const [lName, setLName] = useState(''); const [lKind, setLKind] = useState('warehouse')

  const makeHeaders = useCallback((): HeadersInit => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [token, organizationId])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [ri, rl, rs] = await Promise.all([
        fetch('/api/inventory/items', { headers: makeHeaders() }),
        fetch('/api/inventory/locations', { headers: makeHeaders() }),
        fetch('/api/inventory/stock', { headers: makeHeaders() }),
      ])
      const [di, dl, ds] = await Promise.all([ri.json(), rl.json(), rs.json()])
      if (!ri.ok) { setError(di.detail || 'Failed to load inventory.'); return }
      setItems(di.items || []); setLocations(dl.locations || []); setStock(ds.stock || [])
      if (canValuation) {
        const rv = await fetch('/api/inventory/valuation', { headers: makeHeaders() })
        if (rv.ok) setValuation((await rv.json()).total_value)
      }
    } catch { setError('Network error loading inventory.') }
    finally { setLoading(false) }
  }, [makeHeaders, canValuation])

  useEffect(() => { load() }, [load])

  const itemBalance = (id: string) => stock.filter(s => s.item_id === id).reduce((t, s) => t + s.balance, 0)
  const isLow = (it: Item) => it.reorder_threshold != null && itemBalance(it.id) <= it.reorder_threshold
  const lowCount = items.filter(isLow).length
  const showCost = items.some(it => 'unit_cost' in it)

  const submitMove = async (e: React.FormEvent) => {
    e.preventDefault(); setMoving(true); setError(null); setSuccess(null)
    const qty = parseFloat(mQty)
    try {
      let url = '', body: Record<string, unknown> = {}
      if (moveType === 'transfer') {
        url = '/api/inventory/transfer'; body = { item_id: mItem, from_location_id: mLoc, to_location_id: mTo, qty, reason: mReason || null }
      } else if (moveType === 'adjust') {
        url = '/api/inventory/adjust'; body = { item_id: mItem, location_id: mLoc, qty_delta: qty, reason: mReason }
      } else {
        url = `/api/inventory/${moveType}`; body = { item_id: mItem, location_id: mLoc, qty, reason: mReason || null }
      }
      const res = await fetch(url, { method: 'POST', headers: makeHeaders(), body: JSON.stringify(body) })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Stock movement failed.'); return }
      setSuccess(data.message || 'Done.'); setMQty(''); setMReason('')
      await load()
    } catch { setError('Network error recording movement.') }
    finally { setMoving(false) }
  }

  const submitItem = async (e: React.FormEvent) => {
    e.preventDefault(); setError(null); setSuccess(null)
    try {
      const res = await fetch('/api/inventory/items', {
        method: 'POST', headers: makeHeaders(),
        body: JSON.stringify({ name: iName.trim(), sku: iSku || null, unit: iUnit || null, unit_cost: iCost ? parseFloat(iCost) : null, reorder_threshold: iThreshold ? parseFloat(iThreshold) : null }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to create item.'); return }
      setSuccess(`Item "${iName}" added.`); setIName(''); setISku(''); setIUnit(''); setICost(''); setIThreshold(''); setShowItemForm(false)
      await load()
    } catch { setError('Network error creating item.') }
  }

  const submitLoc = async (e: React.FormEvent) => {
    e.preventDefault(); setError(null); setSuccess(null)
    try {
      const res = await fetch('/api/inventory/locations', {
        method: 'POST', headers: makeHeaders(), body: JSON.stringify({ name: lName.trim(), kind: lKind }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to create location.'); return }
      setSuccess(`Location "${lName}" added.`); setLName(''); setShowLocForm(false)
      await load()
    } catch { setError('Network error creating location.') }
  }

  const kpis = [
    { label: 'Stock Items', value: String(items.length), color: COLORS.navy },
    { label: 'Low Stock', value: String(lowCount), color: lowCount ? COLORS.redFg : COLORS.greenFg },
    ...(canValuation ? [{ label: 'Inventory Value', value: valuation != null ? `$${valuation.toLocaleString()}` : '—', color: COLORS.navy }] : []),
  ]

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader title="Inventory & Chemical Control" subtitle="Live stock via an append-only ledger — usage, transfers, and (for managers) valuation" />

      {error && <div style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #fecaca' }}>{error}</div>}
      {success && <div style={{ background: COLORS.greenBg, color: COLORS.greenFg, padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #86efac' }}>{success}</div>}

      <div className={kpis.length === 3 ? 'grid-cols-3' : 'grid-cols-2'} style={{ marginBottom: 24 }}>
        {kpis.map(c => (
          <MetricCard key={c.label} label={c.label} value={c.value} valueColor={c.color} />
        ))}
      </div>

      {/* Stock movement */}
      {moveTypes.length > 0 && (
        <div className="glass-card" style={{ marginBottom: 28 }}>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: 16 }}>Record Stock Movement</h2>
          <form onSubmit={submitMove} style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ ...fieldStyle, flex: '1 1 130px' }}>
              <label style={labelStyle}>Type</label>
              <select value={moveType} onChange={e => setMoveType(e.target.value as MoveType)} style={inputStyle}>
                {moveTypes.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div style={{ ...fieldStyle, flex: '2 1 180px' }}>
              <label style={labelStyle}>Item</label>
              <select required value={mItem} onChange={e => setMItem(e.target.value)} style={inputStyle}>
                <option value="">Select…</option>{items.map(it => <option key={it.id} value={it.id}>{it.name}</option>)}
              </select>
            </div>
            <div style={{ ...fieldStyle, flex: '1 1 150px' }}>
              <label style={labelStyle}>{moveType === 'transfer' ? 'From location' : 'Location'}</label>
              <select required value={mLoc} onChange={e => setMLoc(e.target.value)} style={inputStyle}>
                <option value="">Select…</option>{locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </div>
            {moveType === 'transfer' && (
              <div style={{ ...fieldStyle, flex: '1 1 150px' }}>
                <label style={labelStyle}>To location</label>
                <select required value={mTo} onChange={e => setMTo(e.target.value)} style={inputStyle}>
                  <option value="">Select…</option>{locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              </div>
            )}
            <div style={{ ...fieldStyle, flex: '1 1 110px' }}>
              <label style={labelStyle}>{moveType === 'adjust' ? 'Δ Qty (±)' : 'Quantity'}</label>
              <input required type="number" step="any" value={mQty} onChange={e => setMQty(e.target.value)} style={inputStyle} />
            </div>
            <div style={{ ...fieldStyle, flex: '2 1 160px' }}>
              <label style={labelStyle}>Reason{moveType === 'adjust' ? ' *' : ''}</label>
              <input required={moveType === 'adjust'} value={mReason} onChange={e => setMReason(e.target.value)} style={inputStyle} placeholder={moveType === 'adjust' ? 'e.g. stock-take correction' : 'optional'} />
            </div>
            <button type="submit" disabled={moving || !mItem || !mLoc || !mQty} style={{ padding: '0.45rem 1.1rem', fontSize: '0.875rem' }}>{moving ? 'Recording…' : 'Record'}</button>
          </form>
        </div>
      )}

      {/* Items + balances */}
      <div className="glass-card" style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: 16 }}>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Stock on Hand</h2>
          {canConfigure && (
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button onClick={() => setShowItemForm(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}><Plus size={14} />Item</button>
              <button className="secondary" onClick={() => setShowLocForm(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}><Plus size={14} />Location</button>
            </div>
          )}
        </div>

        {canConfigure && showItemForm && (
          <form onSubmit={submitItem} style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '1rem', marginBottom: '1rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ ...fieldStyle, flex: '2 1 160px' }}><label style={labelStyle}>Name *</label><input required value={iName} onChange={e => setIName(e.target.value)} style={inputStyle} /></div>
            <div style={{ ...fieldStyle, flex: '1 1 110px' }}><label style={labelStyle}>SKU</label><input value={iSku} onChange={e => setISku(e.target.value)} style={inputStyle} /></div>
            <div style={{ ...fieldStyle, flex: '1 1 90px' }}><label style={labelStyle}>Unit</label><input value={iUnit} onChange={e => setIUnit(e.target.value)} style={inputStyle} placeholder="kg / L" /></div>
            <div style={{ ...fieldStyle, flex: '1 1 100px' }}><label style={labelStyle}>Unit cost</label><input type="number" step="any" value={iCost} onChange={e => setICost(e.target.value)} style={inputStyle} /></div>
            <div style={{ ...fieldStyle, flex: '1 1 110px' }}><label style={labelStyle}>Reorder at</label><input type="number" step="any" value={iThreshold} onChange={e => setIThreshold(e.target.value)} style={inputStyle} /></div>
            <button type="submit" disabled={!iName.trim()} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem' }}>Add Item</button>
          </form>
        )}
        {canConfigure && showLocForm && (
          <form onSubmit={submitLoc} style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '1rem', marginBottom: '1rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ ...fieldStyle, flex: '2 1 180px' }}><label style={labelStyle}>Location name *</label><input required value={lName} onChange={e => setLName(e.target.value)} style={inputStyle} /></div>
            <div style={{ ...fieldStyle, flex: '1 1 140px' }}><label style={labelStyle}>Kind</label><select value={lKind} onChange={e => setLKind(e.target.value)} style={inputStyle}>{['warehouse', 'vehicle', 'site_store'].map(k => <option key={k} value={k}>{k}</option>)}</select></div>
            <button type="submit" disabled={!lName.trim()} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem' }}>Add Location</button>
          </form>
        )}

        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: COLORS.slate, fontSize: '0.9rem' }}>Loading inventory…</div>
        ) : items.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: COLORS.slateLight, fontSize: '0.9rem' }}>No stock items yet.{canConfigure ? ' Add an item to begin.' : ''}</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 640 }}>
              <thead><tr>{['Item', 'SKU', 'On hand', 'Reorder at', ...(showCost ? ['Unit cost'] : []), 'Status'].map(h => <th key={h} style={tableHeaderStyle}>{h}</th>)}</tr></thead>
              <tbody>
                {items.map(it => {
                  const bal = itemBalance(it.id); const low = isLow(it)
                  return (
                    <tr key={it.id}>
                      <td style={{ ...tableCellStyle, fontWeight: 600, color: COLORS.navy }}>{it.name}</td>
                      <td style={{ ...tableCellStyle, color: COLORS.slate }}>{it.sku || '—'}</td>
                      <td style={{ ...tableCellStyle, textAlign: 'center', fontWeight: 600 }}>{bal}{it.unit ? ` ${it.unit}` : ''}</td>
                      <td style={{ ...tableCellStyle, textAlign: 'center', color: COLORS.slate }}>{it.reorder_threshold ?? '—'}</td>
                      {showCost && <td style={{ ...tableCellStyle, textAlign: 'center' }}>{it.unit_cost != null ? `$${it.unit_cost}` : '—'}</td>}
                      <td style={tableCellStyle}><StatusBadge tone={low ? 'red' : 'green'} variant="count">{low ? 'Low' : 'OK'}</StatusBadge></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
