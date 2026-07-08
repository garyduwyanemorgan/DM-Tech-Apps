import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { PageHeader } from './PageHeader'
import { FlaskConical, Microscope, ClipboardList, Check, Plus } from 'lucide-react'

interface Forecast {
  dominant_group: string
  group_probabilities: Record<string, number>
  succession_stage: string
  cyano_advantage: number
  trophic_state: string
  n_p_ratio: number | null
  phyco_chla_ratio: number | null
  observed_signal: string
  confidence_pct: number
  lab_test_recommended: boolean
  lab_test_reason: string
  missing_inputs: string[]
  enhancing_inputs: string[]
  recommended_tests: string[]
  reasoning: string[]
}
interface CommunityResp {
  site: string; available: boolean; message?: string; period?: string; forecast?: Forecast
}
interface DataRequest {
  id: string; items: string[]; reason: string; status: string; created_at: string
}

const GROUP_LABEL: Record<string, string> = {
  cyanobacteria: 'Cyanobacteria', green_algae: 'Green algae', diatoms: 'Diatoms', dinoflagellates: 'Dinoflagellates',
}
const GROUP_COLOR: Record<string, string> = {
  cyanobacteria: '#e74c3c', green_algae: '#10b981', diatoms: '#4472C4', dinoflagellates: '#9b59b6',
}
const GROUP_ORDER = ['cyanobacteria', 'green_algae', 'diatoms', 'dinoflagellates']
const STAGES = ['stable_diatoms', 'green_algae_phase', 'cyanobacteria_risk', 'active_bloom', 'post_bloom_collapse']
const STAGE_LABEL: Record<string, string> = {
  stable_diatoms: 'Stable diatoms', green_algae_phase: 'Green algae phase', cyanobacteria_risk: 'Cyanobacteria risk',
  active_bloom: 'Active bloom', post_bloom_collapse: 'Post-bloom collapse',
}
const STAGE_COLOR = ['#10b981', '#84cc16', '#f59e0b', '#ef4444', '#9C0006']
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

export const Community: React.FC<{ activeSite: string }> = ({ activeSite }) => {
  const { organizationId, token, role } = useAuth()
  const canRequest = role === 'operator' || role === 'admin' || role === 'super_admin'
  const [data, setData] = useState<CommunityResp | null>(null)
  const [requests, setRequests] = useState<DataRequest[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const headers = useCallback((): Record<string, string> => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [token, organizationId])

  const fetchAll = useCallback(async () => {
    if (!activeSite) { setData(null); setRequests([]); return }
    setLoading(true); setError(null)
    try {
      const s = encodeURIComponent(activeSite)
      const [fRes, rRes] = await Promise.all([
        fetch(`/api/community/${s}?year=${new Date().getFullYear()}`, { headers: headers() }),
        fetch(`/api/community/${s}/requests`, { headers: headers() }),
      ])
      const fJson = await fRes.json()
      if (!fRes.ok) { setError(fJson.detail || 'Failed to load forecast.'); return }
      setData(fJson)
      const rJson = await rRes.json().catch(() => ({ requests: [] }))
      setRequests(rRes.ok ? (rJson.requests || []) : [])
    } catch {
      setError('Network error loading forecast.')
    } finally {
      setLoading(false)
    }
  }, [activeSite, headers])

  useEffect(() => { fetchAll() }, [fetchAll])

  const f = data?.forecast
  const stageIdx = f ? STAGES.indexOf(f.succession_stage) : -1
  const requestItems = f ? [...f.missing_inputs, ...f.recommended_tests, ...f.enhancing_inputs] : []

  const createRequest = async () => {
    if (!f || requestItems.length === 0) return
    setBusy(true); setError(null); setNotice(null)
    try {
      const reason = f.lab_test_reason || 'Parameters recommended to strengthen the algae & bloom forecast.'
      const res = await fetch(`/api/community/${encodeURIComponent(activeSite)}/requests`, {
        method: 'POST', headers: headers(), body: JSON.stringify({ items: requestItems, reason }),
      })
      const json = await res.json()
      if (!res.ok) { setError(json.detail || 'Failed to create request.'); return }
      setNotice('Request created.')
      await fetchAll()
    } catch {
      setError('Network error creating request.')
    } finally {
      setBusy(false)
    }
  }

  const dismiss = async (id: string) => {
    setError(null); setNotice(null)
    try {
      const res = await fetch(`/api/community/${encodeURIComponent(activeSite)}/requests/${id}`, {
        method: 'DELETE', headers: headers(),
      })
      const json = await res.json()
      if (!res.ok) { setError(json.detail || 'Failed to update request.'); return }
      setRequests(rs => rs.filter(r => r.id !== id))
    } catch {
      setError('Network error updating request.')
    }
  }

  return (
    <div style={{ maxWidth: 1100 }}>
      <PageHeader title="Algae & Bloom Forecast" subtitle={`Predicted community, succession stage & bloom risk for ${activeSite || 'your lagoon'}`} icon="🦠" />

      {error  && <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #fecaca' }}>{error}</div>}
      {notice && <div style={{ background: '#C6EFCE', color: '#006100', padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #86efac' }}>{notice}</div>}

      {!activeSite && (
        <div className="glass-card" style={{ padding: '2.5rem', textAlign: 'center', color: '#94a3b8' }}>
          Select an Active Site (top-left) to see its algae & bloom forecast.
        </div>
      )}

      {activeSite && loading && (
        <div className="glass-card" style={{ padding: '2.5rem', textAlign: 'center', color: '#64748b' }}>Computing forecast…</div>
      )}

      {activeSite && !loading && data && !data.available && (
        <div className="glass-card" style={{ padding: '2.5rem', textAlign: 'center', color: '#94a3b8' }}>
          <Microscope size={40} style={{ marginBottom: '0.75rem', opacity: 0.6 }} />
          <div style={{ fontWeight: 600, color: '#64748b', marginBottom: '0.4rem' }}>No forecast yet</div>
          <div style={{ fontSize: '0.875rem' }}>{data.message || 'Log a lab report for this site to generate a forecast.'}</div>
        </div>
      )}

      {activeSite && !loading && f && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

          {/* Lab-test recommendation — the escalation action */}
          {f.lab_test_recommended && (
            <div style={{ background: '#FFF4E5', border: '1px solid #fdba74', borderRadius: 10, padding: '1rem 1.25rem', display: 'flex', gap: '0.9rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>
              <FlaskConical size={22} color="#9a3412" style={{ marginTop: 2, flexShrink: 0 }} />
              <div style={{ flex: '1 1 320px' }}>
                <div style={{ fontWeight: 700, color: '#9a3412', marginBottom: '0.25rem' }}>Recommended: request a confirmatory lab test</div>
                <div style={{ fontSize: '0.875rem', color: '#7c2d12', lineHeight: 1.5 }}>{f.lab_test_reason}</div>
              </div>
              {canRequest && (
                <button onClick={createRequest} disabled={busy} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 1rem', fontSize: '0.875rem', alignSelf: 'center' }}>
                  <Plus size={15} />{busy ? 'Creating…' : 'Create request'}
                </button>
              )}
            </div>
          )}

          {/* Dominant community hero */}
          <div className="glass-card" style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
                Likely dominant community {data?.period ? `· ${data.period}` : ''}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <span style={{ width: 14, height: 14, borderRadius: '50%', background: GROUP_COLOR[f.dominant_group] || '#64748b', display: 'inline-block' }} />
                <span style={{ fontSize: '1.7rem', fontWeight: 700, color: '#1B3A5C' }}>{GROUP_LABEL[f.dominant_group] || f.dominant_group}</span>
              </div>
              <div style={{ fontSize: '0.85rem', color: '#64748b', marginTop: 4 }}>{f.confidence_pct}% confidence · trophic state {f.trophic_state}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>Succession stage</div>
              <span style={{ background: STAGE_COLOR[stageIdx] || '#64748b', color: '#fff', fontWeight: 700, borderRadius: 8, padding: '5px 14px', fontSize: '0.95rem', display: 'inline-block' }}>
                {STAGE_LABEL[f.succession_stage] || f.succession_stage}
              </span>
            </div>
          </div>

          {/* Group probabilities */}
          <div className="glass-card">
            <h3 style={{ marginTop: 0, marginBottom: '1rem', fontSize: '1.05rem', fontWeight: 600, color: '#1B3A5C' }}>Community composition (predicted)</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.7rem' }}>
              {GROUP_ORDER.map(g => {
                const pct = Math.round((f.group_probabilities[g] || 0) * 100)
                return (
                  <div key={g} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <span style={{ width: 130, fontSize: '0.85rem', color: '#374151', fontWeight: g === f.dominant_group ? 700 : 400 }}>{GROUP_LABEL[g]}</span>
                    <div style={{ flex: 1, height: 14, background: '#f1f5f9', borderRadius: 7, overflow: 'hidden' }}>
                      <div style={{ width: `${pct}%`, height: '100%', background: GROUP_COLOR[g], borderRadius: 7, transition: 'width 0.3s' }} />
                    </div>
                    <span style={{ width: 44, textAlign: 'right', fontSize: '0.85rem', fontWeight: 600, color: '#1B3A5C' }}>{pct}%</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Succession trajectory */}
          <div className="glass-card">
            <h3 style={{ marginTop: 0, marginBottom: '1rem', fontSize: '1.05rem', fontWeight: 600, color: '#1B3A5C' }}>Ecological succession trajectory</h3>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {STAGES.map((s, i) => {
                const active = i === stageIdx
                return (
                  <div key={s} style={{ flex: '1 1 120px', textAlign: 'center', padding: '0.5rem 0.4rem', borderRadius: 8,
                    background: active ? STAGE_COLOR[i] : '#f8fafc', color: active ? '#fff' : '#94a3b8',
                    border: active ? 'none' : '1px solid #e2e8f0', fontWeight: active ? 700 : 500, fontSize: '0.78rem' }}>
                    {STAGE_LABEL[s]}
                  </div>
                )
              })}
            </div>
            <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: '0.75rem 0 0' }}>
              Communities progress left → right as a lagoon deteriorates. Your lagoon is currently at the highlighted stage.
            </p>
          </div>

          {/* Signals */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem' }}>
            {[
              { label: 'N : P ratio', value: f.n_p_ratio ?? '—', hint: 'ammonia : phosphate (low → cyano)' },
              { label: 'Phycocyanin : Chl-a', value: f.phyco_chla_ratio ?? '—', hint: 'measured cyano pigment marker' },
              { label: 'Cyano advantage', value: `${Math.round(f.cyano_advantage * 100)}%`, hint: 'competitive edge of cyanobacteria' },
              { label: 'Trophic state', value: cap(f.trophic_state), hint: 'from chlorophyll-a' },
            ].map(s => (
              <div key={s.label} className="glass-card" style={{ padding: '1rem' }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.label}</div>
                <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#1B3A5C', margin: '2px 0' }}>{s.value}</div>
                <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>{s.hint}</div>
              </div>
            ))}
          </div>

          {/* Data & lab requests */}
          <div className="glass-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <ClipboardList size={18} color="#1B3A5C" />
              <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: '#1B3A5C' }}>Data &amp; lab requests</h3>
            </div>

            {/* What the model recommends requesting */}
            {requestItems.length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.82rem', color: '#64748b', marginBottom: '0.5rem' }}>
                  To strengthen and confirm this forecast, the model recommends obtaining:
                </div>
                <ul style={{ margin: '0 0 0.75rem', paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  {f.missing_inputs.map((x, i) => <li key={`m${i}`} style={{ fontSize: '0.85rem', color: '#9C0006' }}><strong>Missing:</strong> {x}</li>)}
                  {f.recommended_tests.map((x, i) => <li key={`t${i}`} style={{ fontSize: '0.85rem', color: '#9a3412' }}><strong>Lab test:</strong> {x}</li>)}
                  {f.enhancing_inputs.map((x, i) => <li key={`e${i}`} style={{ fontSize: '0.85rem', color: '#374151' }}><strong>Would strengthen:</strong> {x}</li>)}
                </ul>
                {canRequest && !f.lab_test_recommended && (
                  <button onClick={createRequest} disabled={busy} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', fontSize: '0.875rem' }}>
                    <Plus size={15} />{busy ? 'Creating…' : 'Create request'}
                  </button>
                )}
              </div>
            )}

            {/* Open requests */}
            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem' }}>
              Open requests ({requests.length})
            </div>
            {requests.length === 0 ? (
              <div style={{ fontSize: '0.85rem', color: '#94a3b8' }}>No open requests.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                {requests.map(r => (
                  <div key={r.id} style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: '0.7rem 0.9rem', display: 'flex', gap: '0.75rem', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap' }}>
                    <div style={{ flex: '1 1 300px' }}>
                      <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginBottom: '0.35rem' }}>
                        Raised {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}{r.reason ? ` · ${r.reason}` : ''}
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                        {r.items.map((it, i) => (
                          <span key={i} style={{ background: '#f1f5f9', color: '#374151', borderRadius: 6, padding: '2px 8px', fontSize: '0.75rem' }}>{it}</span>
                        ))}
                      </div>
                    </div>
                    {canRequest && (
                      <button className="secondary" onClick={() => dismiss(r.id)} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>
                        <Check size={13} />Mark fulfilled
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Reasoning — the explainable why */}
          <div className="glass-card">
            <h3 style={{ marginTop: 0, marginBottom: '0.75rem', fontSize: '1.05rem', fontWeight: 600, color: '#1B3A5C' }}>Why this forecast</h3>
            <ul style={{ margin: 0, paddingLeft: '1.2rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {f.reasoning.map((r, i) => (
                <li key={i} style={{ fontSize: '0.85rem', color: '#374151', lineHeight: 1.5 }}>{r}</li>
              ))}
            </ul>
            <p style={{ fontSize: '0.75rem', color: '#94a3b8', margin: '0.9rem 0 0' }}>
              Predicted from the water-quality drivers; the phycocyanin:chlorophyll ratio is a measured pigment anchor, not a lab species ID.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
