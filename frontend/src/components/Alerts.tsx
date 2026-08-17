import React, { useEffect, useState } from 'react'
import { ALERT_COLORS, ALERT_LABELS, ALERT_THRESHOLDS, ALERT_FG, TREATMENT_ACTIONS } from '../constants'
import { PageHeader } from './PageHeader'
import { AlertCard, RequestIdChip } from './ui'
import { useAuth } from '../context/AuthContext'
import { lastRequestId, readRequestId } from '../lib/requestId'

interface AlertsProps {
  activeSite: string
}

const levels = [1, 2, 3, 4] as const

const TH: React.CSSProperties = {
  padding: '10px 14px',
  textAlign: 'left',
  fontSize: '0.78rem',
  fontWeight: 700,
  color: '#64748b',
  background: '#f8fafc',
  borderBottom: '2px solid #e2e8f0',
  whiteSpace: 'nowrap',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
}

const TD: React.CSSProperties = {
  padding: '10px 14px',
  fontSize: '0.875rem',
  color: '#374151',
  borderBottom: '1px solid #f1f5f9',
  verticalAlign: 'top',
}


interface LiveState {
  level: 1 | 2 | 3 | 4
  label: string
  month: string
  failing: string[]
  compliancePct: number
}

/** Fetch outcome for this site's live status, kept distinct on purpose:
 *  'empty' (genuinely no readings yet — a fine, calm state) must never be
 *  reached by a failure path. A non-OK response, an unusable body, or a
 *  thrown error all land in 'unavailable' instead. */
type Status = 'idle' | 'loading' | 'ok' | 'empty' | 'unavailable'

export const Alerts: React.FC<AlertsProps> = ({ activeSite }) => {
  const { organizationId, token } = useAuth()
  const [live, setLive] = useState<LiveState | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<{ message: string; requestId: string | null } | null>(null)

  useEffect(() => {
    // Clear immediately on any site change — including switching between two
    // non-empty sites — so a previous site's alert level never renders under
    // the new site's name while the fetch for it is in flight.
    setLive(null)
    setError(null)
    if (!activeSite) {
      setStatus('idle')
      return
    }
    let cancelled = false
    setStatus('loading')
    const run = async () => {
      try {
        const headers: HeadersInit = {}
        if (organizationId) headers['X-Organization-ID'] = organizationId
        if (token) headers['Authorization'] = `Bearer ${token}`
        const res = await fetch(`/api/status/${encodeURIComponent(activeSite)}`, { headers })
        const requestId = readRequestId(res)
        if (!res.ok) {
          if (!cancelled) {
            setStatus('unavailable')
            setError({ message: `Status endpoint returned ${res.status}. The live alert level for ${activeSite} could not be confirmed.`, requestId })
          }
          return
        }
        const data = await res.json()
        if (cancelled) return
        if (!data || !Array.isArray(data.readings)) {
          setStatus('unavailable')
          setError({ message: 'Status endpoint returned an unexpected shape. Refusing to guess at the alert level.', requestId })
          return
        }
        if (data.readings.length > 0) {
          const latest = data.readings[data.readings.length - 1]
          const lvl = (latest.alert_level ?? 1) as 1 | 2 | 3 | 4
          setLive({
            level: lvl,
            label: latest.alert_label ?? ALERT_LABELS[lvl],
            month: latest.month ?? '',
            failing: latest.failing_params ?? [],
            compliancePct: latest.compliance_pct ?? 0,
          })
          setStatus('ok')
        } else {
          setStatus('empty')
        }
      } catch {
        if (!cancelled) {
          setStatus('unavailable')
          setError({ message: 'Network error reaching the status endpoint. The live alert level is unknown, not clear.', requestId: lastRequestId() })
        }
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [activeSite, organizationId, token])

  const liveLevel = status === 'ok' ? (live?.level ?? null) : null
  const loading = status === 'loading'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <PageHeader
        title="Alert & Response Protocol"
        subtitle="Operations Guide — Decision Matrix & Treatment Actions"
        icon="🚨"
      />

      {/* ── Alert-level colour legend (always shown) ────────────────────────── */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 8,
          padding: '0.85rem 1rem',
          borderRadius: 12,
          background: 'linear-gradient(135deg, #C6EFCE 0%, #FFEB9C 34%, #FFD5A8 67%, #FFC7CE 100%)',
          border: '1px solid #e2e8f0',
        }}
      >
        {levels.map(level => {
          const active = level === liveLevel
          return (
            <div
              key={level}
              style={{
                flex: '1 1 150px',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                background: '#ffffff',
                borderRadius: 8,
                padding: '0.5rem 0.75rem',
                border: `2px solid ${active ? ALERT_COLORS[level] : 'transparent'}`,
                boxShadow: active ? `0 0 0 3px ${ALERT_COLORS[level]}33` : 'none',
                transform: active ? 'translateY(-1px)' : 'none',
                transition: 'all 0.2s',
              }}
            >
              <span style={{ width: 12, height: 12, borderRadius: '50%', background: ALERT_COLORS[level], flexShrink: 0 }} />
              <span style={{ fontSize: '0.8rem', fontWeight: 700, color: ALERT_FG[level] }}>{ALERT_LABELS[level]}</span>
              {active && <span style={{ marginLeft: 'auto', fontSize: '0.62rem', fontWeight: 800, color: ALERT_COLORS[level], letterSpacing: '0.05em' }}>LIVE</span>}
            </div>
          )
        })}
      </div>

      {/* ── LIVE status banner ──────────────────────────────────────────────── */}
      {loading && (
        <div style={{ padding: '1.25rem 1.5rem', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, color: '#64748b', fontSize: '0.9rem' }}>
          Checking current alert status for {activeSite || 'the selected site'}…
        </div>
      )}

      {!loading && status === 'ok' && live && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'stretch',
            gap: '1rem',
            background: `linear-gradient(135deg, ${ALERT_COLORS[live.level]}26 0%, ${ALERT_COLORS[live.level]}0d 100%)`,
            border: `2px solid ${ALERT_COLORS[live.level]}`,
            borderRadius: 12,
            padding: '1.25rem 1.5rem',
          }}
        >
          <div style={{ minWidth: 220, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <div style={{ fontSize: '0.7rem', fontWeight: 700, color: ALERT_FG[live.level], letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: ALERT_COLORS[live.level], display: 'inline-block', boxShadow: `0 0 0 3px ${ALERT_COLORS[live.level]}33` }} />
              Live · {activeSite}
            </div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: ALERT_FG[live.level], lineHeight: 1.15 }}>{live.label}</div>
            <div style={{ fontSize: '0.8rem', color: ALERT_FG[live.level], opacity: 0.85, marginTop: 4 }}>
              Latest reading: {live.month || '—'} · {Math.round(live.compliancePct)}% compliant
            </div>
          </div>

          <div style={{ flex: 1, minWidth: 260, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 8 }}>
            <div style={{ fontSize: '0.7rem', fontWeight: 700, color: ALERT_FG[live.level], letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              Triggering factors
            </div>
            {live.failing.length > 0 ? (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {live.failing.map((f, i) => (
                  <span key={i} style={{ fontSize: '0.78rem', fontWeight: 700, color: '#9C0006', background: '#fff', border: '1px solid #fecaca', borderRadius: 6, padding: '3px 9px' }}>
                    {f}
                  </span>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: '0.85rem', color: ALERT_FG[live.level] }}>
                {live.level === 1 ? 'All parameters within limits — no active triggers.' : 'Bloom-indicator thresholds crossed (Chl-a / DO / phycocyanin).'}
              </div>
            )}
            <div style={{ fontSize: '0.82rem', color: ALERT_FG[live.level], fontWeight: 600, marginTop: 2 }}>
              ▶ Active protocol below: <strong>{ALERT_LABELS[live.level]}</strong>
            </div>
          </div>
        </div>
      )}

      {/* A failed read must never be presented as "no readings yet" — that reads
          as calm and all-clear, and could hide a live Level 3/4 emergency. */}
      {!loading && status === 'unavailable' && (
        <AlertCard
          tier="awaiting"
          title="Alert status unavailable — this is not a compliance verdict"
          description={
            <>
              {error?.message ?? 'The live alert level could not be loaded.'} The reference protocol below is shown for context only — it is not confirmation that {activeSite || 'this site'} has no active alert.
              <RequestIdChip
                requestId={error?.requestId ?? null}
                approximate={!error?.requestId && !!lastRequestId()}
              />
            </>
          }
        />
      )}

      {!loading && status === 'empty' && (
        <div style={{ padding: '1rem 1.25rem', background: '#EFF6FF', border: '1px solid #bfdbfe', borderRadius: 10, color: '#1e3a5c', fontSize: '0.9rem', lineHeight: 1.5 }}>
          No submitted readings for <strong>{activeSite}</strong> yet — showing the reference protocol below. Upload a lab report to activate a live alert level.
        </div>
      )}

      {!loading && status === 'idle' && !activeSite && (
        <div style={{ padding: '1rem 1.25rem', background: '#EFF6FF', border: '1px solid #bfdbfe', borderRadius: 10, color: '#1e3a5c', fontSize: '0.9rem', lineHeight: 1.5 }}>
          No site selected — showing the reference protocol below. Choose a site in the sidebar to see its live alert status.
        </div>
      )}

      {/* Alert Level Decision Matrix */}
      <div className="glass-card">
        <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 5, height: 20, borderRadius: 3, background: 'linear-gradient(#27ae60,#e74c3c)', display: 'inline-block' }} />
          Alert Level Decision Matrix
        </h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '700px', fontSize: '0.875rem' }}>
            <thead>
              <tr>
                {['', 'Alert Level', 'Bloom Prob.', 'Chl-a', 'DO', 'Phycocyanin', 'Temp'].map((col, i) => (
                  <th key={i} style={{ ...TH, ...(i === 0 ? { width: 34, padding: '10px 6px' } : {}) }}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {levels.map(level => {
                const t = ALERT_THRESHOLDS[level]
                const color = ALERT_COLORS[level]
                const isActive = level === liveLevel
                return (
                  <tr key={level} style={isActive ? { background: `${color}14` } : undefined}>
                    <td style={{ ...TD, padding: '8px 6px', textAlign: 'center' }}>
                      {isActive && <span title="Current level" style={{ color, fontWeight: 900 }}>▶</span>}
                    </td>
                    <td style={{ ...TD, padding: '8px 14px' }}>
                      <span style={{
                        display: 'inline-block',
                        background: color,
                        color: '#fff',
                        fontWeight: 700,
                        fontSize: '0.78rem',
                        borderRadius: '5px',
                        padding: '4px 10px',
                        whiteSpace: 'nowrap',
                        boxShadow: isActive ? `0 0 0 3px ${color}44` : undefined,
                      }}>
                        {ALERT_LABELS[level]}
                      </span>
                      {isActive && <span style={{ marginLeft: 8, fontSize: '0.7rem', fontWeight: 800, color, letterSpacing: '0.04em' }}>CURRENT</span>}
                    </td>
                    <td style={TD}>{t.bloomRange}</td>
                    <td style={TD}>{t.chla}</td>
                    <td style={TD}>{t.doVal}</td>
                    <td style={TD}>{t.phyco}</td>
                    <td style={TD}>{t.temp}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {liveLevel && (
          <div style={{ marginTop: '0.85rem', fontSize: '0.8rem', color: '#64748b' }}>
            ▶ marks <strong>{activeSite}</strong>’s current level from its latest submitted reading.
          </div>
        )}
      </div>

      {/* Treatment Actions by Alert Level */}
      <div>
        <h2 style={{ fontSize: '1.1rem', color: '#1B3A5C', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 5, height: 20, borderRadius: 3, background: liveLevel ? ALERT_COLORS[liveLevel] : '#6366f1', display: 'inline-block' }} />
          Treatment Actions by Alert Level
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {levels.map(level => {
            const actions = TREATMENT_ACTIONS[level]
            const color = ALERT_COLORS[level]
            const label = ALERT_LABELS[level]
            const isActive = level === liveLevel
            const rows = [
              { label: 'Enzymes',    value: actions.enzyme },
              { label: 'Aeration',   value: actions.aeration },
              { label: 'Ultrasound', value: actions.ultrasound },
              { label: 'Monitoring', value: actions.monitoring },
            ]
            return (
              <div
                key={level}
                className="glass-card"
                style={{
                  borderLeft: `4px solid ${color}`,
                  padding: '1.25rem 1.5rem',
                  position: 'relative',
                  boxShadow: isActive ? `0 0 0 2px ${color}, 0 8px 24px ${color}22` : undefined,
                  opacity: liveLevel && !isActive ? 0.72 : 1,
                  transition: 'opacity 0.2s, box-shadow 0.2s',
                }}
              >
                {isActive && (
                  <span style={{ position: 'absolute', top: 14, right: 16, background: color, color: '#fff', fontSize: '0.68rem', fontWeight: 800, letterSpacing: '0.05em', padding: '3px 10px', borderRadius: 6 }}>
                    ▶ ACTIVE NOW
                  </span>
                )}
                <h3 style={{ margin: '0 0 0.85rem 0', color, fontWeight: 700, fontSize: '1rem' }}>{label}</h3>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                  <tbody>
                    {rows.map(row => (
                      <tr key={row.label} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '7px 12px 7px 0', color: '#64748b', fontWeight: 600, whiteSpace: 'nowrap', width: '120px' }}>
                          {row.label}
                        </td>
                        <td style={{ padding: '7px 0', color: '#374151' }}>{row.value}</td>
                      </tr>
                    ))}
                    {actions.doNot !== '—' && (
                      <tr>
                        <td colSpan={2} style={{ padding: '10px 0 0' }}>
                          <div style={{
                            background: '#FFC7CE',
                            border: '1px solid #f87171',
                            borderRadius: '6px',
                            padding: '8px 12px',
                            color: '#9C0006',
                            fontWeight: 700,
                            fontSize: '0.875rem',
                          }}>
                            {String.fromCodePoint(0x26D4)} {actions.doNot}
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )
          })}
        </div>
      </div>

      {/* Escalation Rules */}
      <div>
        <h2 style={{ fontSize: '1.1rem', color: '#1B3A5C', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 5, height: 20, borderRadius: 3, background: 'linear-gradient(#ef4444,#16a34a)', display: 'inline-block' }} />
          Escalation Rules
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.25rem' }}>
          <div className="glass-card" style={{ flex: '1 1 280px', borderLeft: '4px solid #ef4444' }}>
            <h3 style={{ marginBottom: '0.85rem', color: '#9C0006' }}>Fast Escalation</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              {[
                'Chl-a doubles in 48h → Level 3 minimum (emergency protocol)',
                'DO < 2 mg/L at any time → Level 4 regardless of Chl-a',
                'Phycocyanin > 200 µg/L → Level 3 minimum (cyano emergency)',
              ].map((text, i) => (
                <AlertCard key={i} tier="critical" title={text} />
              ))}
            </div>
          </div>

          <div className="glass-card" style={{ flex: '1 1 280px', borderLeft: '4px solid #16a34a' }}>
            <h3 style={{ marginBottom: '0.85rem', color: '#006100' }}>De-escalation (Slow)</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              {[
                'Level 4 → 3: DO > 3 AND Chl-a declining for 7 days AND no toxin',
                'Level 3 → 2: All params below threshold for 14 consecutive days',
                'Level 2 → 1: Weekly samples compliant for 4 consecutive weeks',
              ].map((text, i) => (
                <AlertCard key={i} tier="positive" title={text} />
              ))}
            </div>
          </div>
        </div>

        <AlertCard
          tier="awaiting"
          title="Design Principle"
          description="De-escalation is always slower than escalation — prevents costly oscillating treatment cycles."
          style={{ marginTop: '1rem' }}
        />
      </div>
    </div>
  )
}
