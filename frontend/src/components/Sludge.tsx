import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { PageHeader } from './PageHeader'
import { Plus, Trash2, AlertTriangle } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell,
} from 'recharts'

type ZoneStatus = 'OK' | 'WARNING' | 'CRITICAL'

interface Zone {
  zone_name: string
  total_depth_m: number
  sludge_depth_m: number
  effective_depth_m: number
  capacity_loss_pct: number
  status: ZoneStatus
  survey_date: string
}

const STATUS_STYLES: Record<ZoneStatus, React.CSSProperties> = {
  OK:       { background: '#C6EFCE', color: '#006100', border: '1px solid #86efac' },
  WARNING:  { background: '#FFEB9C', color: '#856404', border: '1px solid #fcd34d' },
  CRITICAL: { background: '#FFC7CE', color: '#9C0006', border: '1px solid #f87171' },
}

// ── Static reference content (domain science — not site-specific) ─────────────
const PIE_DATA = [
  { name: 'Dead algae + bacteria', value: 40, color: '#e74c3c' },
  { name: 'Organic detritus',      value: 26, color: '#f59e0b' },
  { name: 'Sand / silt',           value: 17, color: '#94a3b8' },
  { name: 'Minerals',              value: 17, color: '#64748b' },
]

const COMPOSITION_TABLE = [
  { component: 'Dead algae + bacteria', pct: '~40%', digestible: 'YES', treatment: 'Cellulase + protease + lipase' },
  { component: 'Organic detritus',      pct: '~26%', digestible: 'YES', treatment: 'Enzyme cocktail + bacteria' },
  { component: 'Sand / silt',           pct: '~17%', digestible: 'NO',  treatment: 'Physical removal only' },
  { component: 'Minerals',              pct: '~17%', digestible: 'NO',  treatment: 'Physical removal only' },
]

const NUTRIENT_LOADING_TABLE = [
  { condition: 'Bottom DO < 2 mg/L', mechanism: 'Fe³⁺ → Fe²⁺ releases bound PO₄', contribution: '30–60% of total P', prevention: 'Bottom aeration to keep DO > 2' },
  { condition: 'Water Temp > 30°C', mechanism: 'Accelerated sediment P release', contribution: 'Proportional to temp', prevention: 'Manage via aeration' },
  { condition: 'Sludge Depth > 0.9 m', mechanism: 'Large nutrient reservoir in water contact', contribution: 'Can feed blooms for years', prevention: 'Enzyme bio-dredging + physical removal' },
  { condition: 'Sediment DOM release', mechanism: 'Dissolved organic matter stimulates algae', contribution: 'Difficult to quantify', prevention: 'Sludge reduction programme' },
]

const tableHeaderStyle: React.CSSProperties = {
  padding: '10px 14px', textAlign: 'left', fontSize: '0.75rem', fontWeight: 700,
  color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em',
  borderBottom: '2px solid #e2e8f0', background: '#f8fafc', whiteSpace: 'nowrap',
}
const tableCellStyle: React.CSSProperties = {
  padding: '10px 14px', fontSize: '0.85rem', color: '#374151', borderBottom: '1px solid #f1f5f9',
}
const inputStyle: React.CSSProperties = {
  padding: '0.45rem 0.7rem', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: '0.875rem', fontFamily: 'inherit',
}

export const Sludge: React.FC<{ activeSite: string }> = ({ activeSite }) => {
  const { organizationId, token, role } = useAuth()
  const canEdit = role === 'operator' || role === 'admin' || role === 'super_admin'

  const [zones, setZones] = useState<Zone[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [showForm, setShowForm] = useState(false)
  const [zoneName, setZoneName] = useState('')
  const [totalDepth, setTotalDepth] = useState('')
  const [sludgeDepth, setSludgeDepth] = useState('')
  const [surveyDate, setSurveyDate] = useState(new Date().toISOString().slice(0, 10))
  const [saving, setSaving] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<Zone | null>(null)

  const makeHeaders = useCallback((): HeadersInit => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [token, organizationId])

  const fetchZones = useCallback(async () => {
    if (!activeSite) { setZones([]); return }
    setLoading(true); setError(null)
    try {
      const res = await fetch(`/api/sludge/${encodeURIComponent(activeSite)}`, { headers: makeHeaders() })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to load sludge data.'); return }
      setZones(data.zones || [])
    } catch {
      setError('Network error loading sludge data.')
    } finally {
      setLoading(false)
    }
  }, [activeSite, makeHeaders])

  useEffect(() => { fetchZones() }, [fetchZones])

  const resetForm = () => { setZoneName(''); setTotalDepth(''); setSludgeDepth(''); setSurveyDate(new Date().toISOString().slice(0, 10)) }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true); setError(null); setSuccess(null)
    try {
      const res = await fetch(`/api/sludge/${encodeURIComponent(activeSite)}`, {
        method: 'POST',
        headers: makeHeaders(),
        body: JSON.stringify({
          zone_name: zoneName.trim(),
          total_depth_m: parseFloat(totalDepth),
          sludge_depth_m: parseFloat(sludgeDepth),
          survey_date: surveyDate,
        }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to save zone.'); return }
      setSuccess(`Zone "${zoneName.trim()}" saved.`)
      resetForm(); setShowForm(false)
      await fetchZones()
    } catch {
      setError('Network error saving zone.')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!pendingDelete) return
    setError(null); setSuccess(null)
    try {
      const res = await fetch(`/api/sludge/${encodeURIComponent(activeSite)}/${encodeURIComponent(pendingDelete.zone_name)}`, {
        method: 'DELETE', headers: makeHeaders(),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to delete zone.'); return }
      setSuccess(data.message || 'Zone deleted.')
      setZones(z => z.filter(x => x.zone_name !== pendingDelete.zone_name))
      setPendingDelete(null)
    } catch {
      setError('Network error deleting zone.')
    }
  }

  const editZone = (z: Zone) => {
    setZoneName(z.zone_name); setTotalDepth(String(z.total_depth_m)); setSludgeDepth(String(z.sludge_depth_m))
    setSurveyDate(z.survey_date ? z.survey_date.slice(0, 10) : new Date().toISOString().slice(0, 10))
    setShowForm(true); setSuccess(null); setError(null)
  }

  const hasZones = zones.length > 0
  const avgCapacityLoss = hasZones ? zones.reduce((s, z) => s + z.capacity_loss_pct, 0) / zones.length : 0
  const criticalCount = zones.filter(z => z.status === 'CRITICAL').length
  const avgColor = avgCapacityLoss > 25 ? '#9C0006' : avgCapacityLoss > 15 ? '#856404' : '#006100'
  const barData = zones.map(z => ({
    name: z.zone_name.replace(/\s*—.*$/, ''),
    'Effective Depth': parseFloat(z.effective_depth_m.toFixed(2)),
    'Sludge Depth': parseFloat(z.sludge_depth_m.toFixed(2)),
  }))

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <PageHeader title="Sludge & Sediment Management" subtitle={`Capacity tracking for ${activeSite || 'your lagoon'} · composition & nutrient-loading reference`} />

      {error   && <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #fecaca' }}>{error}</div>}
      {success && <div style={{ background: '#C6EFCE', color: '#006100', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #86efac' }}>{success}</div>}

      {/* ── LIVE: CAPACITY TRACKER ── */}
      <div className="glass-card" style={{ marginBottom: '28px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, margin: 0 }}>Capacity Tracker</h2>
            <span style={{ fontSize: '0.72rem', fontWeight: 700, borderRadius: 4, padding: '2px 10px', ...(hasZones ? { background: '#C6EFCE', color: '#006100' } : { background: '#f1f5f9', color: '#64748b' }) }}>
              {hasZones ? `● Live — ${activeSite}` : '○ No zones yet'}
            </span>
          </div>
          {canEdit && activeSite && (
            <button onClick={() => { setShowForm(v => !v); if (showForm) resetForm() }} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 0.85rem', fontSize: '0.875rem' }}>
              <Plus size={15} />{showForm ? 'Cancel' : 'Add / Update Zone'}
            </button>
          )}
        </div>

        {!activeSite && (
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '2rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.9rem' }}>
            Select an Active Site (top-left) to record and view its sludge zones.
          </div>
        )}

        {/* Add/edit form */}
        {canEdit && activeSite && showForm && (
          <form onSubmit={handleSave} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '1rem', marginBottom: '1.25rem', display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ flex: '2 1 200px', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              <label style={{ fontSize: '0.72rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Zone Name *</label>
              <input required placeholder="e.g. Zone A — Inlet" value={zoneName} onChange={e => setZoneName(e.target.value)} style={inputStyle} />
            </div>
            <div style={{ flex: '1 1 120px', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              <label style={{ fontSize: '0.72rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Total Depth (m) *</label>
              <input required type="number" step="0.05" min="0.05" value={totalDepth} onChange={e => setTotalDepth(e.target.value)} style={inputStyle} />
            </div>
            <div style={{ flex: '1 1 120px', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              <label style={{ fontSize: '0.72rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Sludge Depth (m) *</label>
              <input required type="number" step="0.05" min="0" value={sludgeDepth} onChange={e => setSludgeDepth(e.target.value)} style={inputStyle} />
            </div>
            <div style={{ flex: '1 1 140px', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
              <label style={{ fontSize: '0.72rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Survey Date</label>
              <input type="date" value={surveyDate} onChange={e => setSurveyDate(e.target.value)} style={inputStyle} />
            </div>
            <button type="submit" disabled={saving || !zoneName.trim() || !totalDepth || !sludgeDepth} style={{ padding: '0.45rem 1.1rem', fontSize: '0.875rem' }}>
              {saving ? 'Saving…' : 'Save Zone'}
            </button>
          </form>
        )}

        {activeSite && (
          loading ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b', fontSize: '0.9rem' }}>Loading zones…</div>
          ) : !hasZones ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.9rem' }}>
              No sludge zones recorded for {activeSite} yet.{canEdit ? ' Use “Add / Update Zone” to record your first survey.' : ''}
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '680px' }}>
                <thead>
                  <tr>
                    {['Zone', 'Total (m)', 'Sludge (m)', 'Effective (m)', 'Capacity Loss %', 'Status', 'Surveyed', ''].map(h => (
                      <th key={h} style={tableHeaderStyle}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {zones.map(z => (
                    <tr key={z.zone_name}>
                      <td style={{ ...tableCellStyle, fontWeight: 600, color: '#1B3A5C' }}>{z.zone_name}</td>
                      <td style={{ ...tableCellStyle, textAlign: 'center' }}>{z.total_depth_m}</td>
                      <td style={{ ...tableCellStyle, textAlign: 'center' }}>{z.sludge_depth_m}</td>
                      <td style={{ ...tableCellStyle, textAlign: 'center' }}>{z.effective_depth_m.toFixed(2)}</td>
                      <td style={{ ...tableCellStyle, textAlign: 'center' }}>{z.capacity_loss_pct.toFixed(1)}%</td>
                      <td style={{ ...tableCellStyle, textAlign: 'center' }}>
                        <span style={{ ...STATUS_STYLES[z.status], padding: '3px 12px', borderRadius: '9999px', fontSize: '0.78rem', fontWeight: 700, display: 'inline-block' }}>{z.status}</span>
                      </td>
                      <td style={{ ...tableCellStyle, textAlign: 'center', color: '#64748b', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>{z.survey_date || '—'}</td>
                      <td style={{ ...tableCellStyle, textAlign: 'center', whiteSpace: 'nowrap' }}>
                        {canEdit && (
                          <span style={{ display: 'inline-flex', gap: '0.4rem' }}>
                            <button onClick={() => editZone(z)} style={{ background: 'transparent', border: '1px solid #cbd5e1', borderRadius: 6, padding: '3px 10px', cursor: 'pointer', fontSize: '0.78rem', color: '#1B3A5C', fontFamily: 'inherit' }}>Edit</button>
                            <button onClick={() => { setPendingDelete(z); setError(null); setSuccess(null) }} style={{ background: 'transparent', border: '1px solid #fecaca', borderRadius: 6, padding: '3px 8px', cursor: 'pointer', color: '#9C0006', display: 'inline-flex', alignItems: 'center', fontFamily: 'inherit' }} aria-label="Delete zone"><Trash2 size={13} /></button>
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>

      {/* ── LIVE: KPI CARDS + CHART (only when zones exist) ── */}
      {hasZones && (
        <>
          <div className="grid-cols-3" style={{ marginBottom: '28px' }}>
            <div className="glass-card" style={{ textAlign: 'center' }}>
              <p style={{ color: '#94a3b8', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '8px' }}>Avg Capacity Loss</p>
              <p style={{ fontSize: '2.4rem', fontWeight: 700, color: avgColor, margin: '0 0 6px' }}>{avgCapacityLoss.toFixed(1)}%</p>
              <p style={{ color: '#64748b', fontSize: '0.8rem' }}>Across {zones.length} monitored zone{zones.length === 1 ? '' : 's'}</p>
            </div>
            <div className="glass-card" style={{ textAlign: 'center' }}>
              <p style={{ color: '#94a3b8', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '8px' }}>Critical Zones</p>
              <p style={{ fontSize: '2.4rem', fontWeight: 700, color: criticalCount > 0 ? '#9C0006' : '#006100', margin: '0 0 6px' }}>{criticalCount}</p>
              <p style={{ color: '#64748b', fontSize: '0.8rem' }}>Capacity loss &gt; 30%</p>
            </div>
            <div className="glass-card" style={{ textAlign: 'center' }}>
              <p style={{ color: '#94a3b8', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '8px' }}>Bio-Digestible Fraction</p>
              <p style={{ fontSize: '2.4rem', fontWeight: 700, color: '#006100', margin: '0 0 6px' }}>~66%</p>
              <p style={{ color: '#64748b', fontSize: '0.8rem' }}>Treatable with enzyme cocktail</p>
            </div>
          </div>

          <div className="glass-card" style={{ marginBottom: '28px' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '4px' }}>Zone Depth Breakdown</h2>
            <p style={{ color: '#94a3b8', fontSize: '0.82rem', marginBottom: '16px' }}>
              Each bar's full height is the total depth (m): red = sludge on the bed, blue = effective (clear) water above it.
            </p>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={barData} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} unit=" m" />
                <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', color: '#374151' }} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                <Legend wrapperStyle={{ color: '#64748b', fontSize: '0.82rem' }} />
                <Bar dataKey="Sludge Depth" stackId="a" fill="#e74c3c" />
                <Bar dataKey="Effective Depth" stackId="a" fill="#4472C4" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {/* ── REFERENCE: composition + nutrient loading (domain science, not site-specific) ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', margin: '8px 0 16px', color: '#64748b' }}>
        <span style={{ height: 1, background: '#e2e8f0', flex: 1 }} />
        <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Reference — sediment science</span>
        <span style={{ height: 1, background: '#e2e8f0', flex: 1 }} />
      </div>

      <div className="glass-card" style={{ marginBottom: '28px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '20px' }}>Typical Sludge Composition</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '32px', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ flex: '1 1 300px', minWidth: 260, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <ResponsiveContainer width="100%" height={320}>
              <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                <Pie data={PIE_DATA} cx="50%" cy="45%" innerRadius={62} outerRadius={100} dataKey="value" paddingAngle={2}>
                  {PIE_DATA.map(entry => (<Cell key={entry.name} fill={entry.color} />))}
                </Pie>
                <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', color: '#374151' }} formatter={(value) => [`${value}%`, '']} />
                <Legend layout="horizontal" align="center" verticalAlign="bottom" iconType="circle" wrapperStyle={{ color: '#64748b', fontSize: '0.75rem', lineHeight: '1.7', paddingTop: 8 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div style={{ flex: '1 1 340px', minWidth: 300, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '340px' }}>
              <thead><tr>{['Component', 'Percentage', 'Digestible', 'Treatment'].map(h => (<th key={h} style={tableHeaderStyle}>{h}</th>))}</tr></thead>
              <tbody>
                {COMPOSITION_TABLE.map(row => (
                  <tr key={row.component}>
                    <td style={tableCellStyle}>{row.component}</td>
                    <td style={{ ...tableCellStyle, textAlign: 'center', fontWeight: 600 }}>{row.pct}</td>
                    <td style={{ ...tableCellStyle, textAlign: 'center' }}><span style={{ color: row.digestible === 'YES' ? '#006100' : '#9C0006', fontWeight: 700 }}>{row.digestible}</span></td>
                    <td style={tableCellStyle}>{row.treatment}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="glass-card" style={{ marginBottom: '28px', overflowX: 'auto' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '4px' }}>Internal Nutrient Loading</h2>
        <p style={{ color: '#94a3b8', fontSize: '0.82rem', marginBottom: '16px' }}>Risk Assessment</p>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '620px' }}>
          <thead><tr>{['Condition', 'Mechanism', 'P Contribution', 'Prevention'].map(h => (<th key={h} style={tableHeaderStyle}>{h}</th>))}</tr></thead>
          <tbody>
            {NUTRIENT_LOADING_TABLE.map(row => (
              <tr key={row.condition}>
                <td style={{ ...tableCellStyle, fontWeight: 600, color: '#856404', whiteSpace: 'nowrap' }}>{row.condition}</td>
                <td style={tableCellStyle}>{row.mechanism}</td>
                <td style={{ ...tableCellStyle, color: '#9C0006', fontWeight: 500 }}>{row.contribution}</td>
                <td style={tableCellStyle}>{row.prevention}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ background: '#FFF0F0', border: '1px solid #fecaca', borderRadius: '12px', padding: '20px 24px' }}>
        <p style={{ fontWeight: 700, color: '#9C0006', fontSize: '1rem', marginBottom: '8px' }}>The Internal Loading Trap</p>
        <p style={{ color: '#374151', fontSize: '0.88rem', lineHeight: '1.65', margin: 0 }}>
          Even with zero external nutrient inputs, sludge can feed blooms for years. At 33°C, sediment P
          release accelerates dramatically. Sludge management is not optional — it's a prerequisite for
          long-term control.
        </p>
      </div>

      {/* Delete confirmation */}
      {pendingDelete && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
          <div style={{ background: '#fff', borderRadius: 12, padding: '2rem', maxWidth: 420, width: '100%', boxShadow: '0 20px 60px rgba(0,0,0,0.25)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
              <div style={{ background: '#FFF0F0', borderRadius: '50%', padding: '0.6rem', display: 'flex' }}><AlertTriangle size={22} color="#9C0006" /></div>
              <h3 style={{ margin: 0, fontSize: '1.05rem', color: '#1B3A5C' }}>Delete Zone</h3>
            </div>
            <p style={{ color: '#374151', fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1.25rem' }}>
              Delete <strong>{pendingDelete.zone_name}</strong> from {activeSite}? This removes the survey record permanently.
            </p>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button className="secondary" onClick={() => setPendingDelete(null)}>Cancel</button>
              <button onClick={handleDelete} style={{ background: '#9C0006', color: '#fff', border: 'none' }}>Delete Zone</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
