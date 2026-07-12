import React, { useEffect, useState } from 'react'
import { PageHeader } from './PageHeader'
import { useAuth } from '../context/AuthContext'
import { COMPLIANCE_LIMITS, ALERT_THRESHOLDS, ALERT_COLORS, ALERT_LABELS } from '../constants'
import { LIGHT_STYLE, type TrafficLight } from '../lib/status'
import { useMonthlySeries, NoData, SampleBanner, fmt, type ParamKey } from '../lib/sampleData'

interface DashboardProps {
  activeSite: string
}

/** COMPLIANCE_LIMITS calls it total_coliforms; the monthly series calls it coliforms. */
const seriesKey = (limitKey: string): ParamKey =>
  (limitKey === 'total_coliforms' ? 'coliforms' : limitKey) as ParamKey

function isPass(key: string, value: number): boolean {
  const limit = COMPLIANCE_LIMITS[key]
  if (!limit) return true
  if (limit.min !== null && value < limit.min) return false
  if (limit.max !== null && value > limit.max) return false
  return true
}

function marginPct(key: string, value: number): number {
  const limit = COMPLIANCE_LIMITS[key]
  if (!limit) return 100
  if (limit.max !== null) return ((limit.max - value) / limit.max) * 100
  if (limit.min !== null) return ((value - limit.min) / limit.min) * 100
  return 100
}

function riskLabel(pct: number, pass: boolean): string {
  if (!pass) return 'EXCEED'
  if (pct < 20) return 'WATCH'
  if (pct < 50) return 'MODERATE'
  return 'LOW'
}

function riskStyle(pct: number, pass: boolean): React.CSSProperties {
  if (!pass)  return { color: '#9C0006', fontWeight: 700 }
  if (pct < 20) return { color: '#856404', fontWeight: 600 }
  if (pct < 50) return { color: '#374151', fontWeight: 500 }
  return { color: '#006100', fontWeight: 500 }
}

const TH: React.CSSProperties = {
  padding: '9px 12px',
  textAlign: 'left',
  fontSize: '0.75rem',
  fontWeight: 700,
  color: '#64748b',
  background: '#f8fafc',
  borderBottom: '2px solid #e2e8f0',
  whiteSpace: 'nowrap',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
}

const TD: React.CSSProperties = {
  padding: '9px 12px',
  fontSize: '0.85rem',
  color: '#374151',
  borderBottom: '1px solid #f1f5f9',
}

export const Dashboard: React.FC<DashboardProps> = ({ activeSite }) => {
  const { organizationId, token } = useAuth()
  const { series, source, loading, liveMonths } = useMonthlySeries(activeSite)
  const [alertLevel, setAlertLevel] = useState<1 | 2 | 3 | 4>(1)

  // /api/status is the alert-level source. It carries NO parameter values — those
  // come from the monthly series — so nothing here can back-fill a measurement.
  useEffect(() => {
    if (!activeSite) { setAlertLevel(1); return }
    let cancelled = false
    const load = async () => {
      try {
        const headers: HeadersInit = {}
        if (organizationId) headers['X-Organization-ID'] = organizationId
        if (token) headers['Authorization'] = `Bearer ${token}`
        const res = await fetch(`/api/status/${encodeURIComponent(activeSite)}`, { headers })
        const data = await res.json()
        const latest = data.readings?.[data.readings.length - 1]
        if (!cancelled) setAlertLevel((latest?.alert_level ?? 1) as 1 | 2 | 3 | 4)
      } catch {
        if (!cancelled) setAlertLevel(1)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [activeSite, organizationId, token])

  if (!series) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Dubai Lagoon Management Plan" subtitle="Dubai Municipality / Client View" icon="🏝️" />
        <NoData />
      </div>
    )
  }

  const isLive = source === 'live'
  const now = new Date()

  // "Current" = the most recent month that actually carries a reading. For the sample
  // baseline that is simply the calendar month.
  const currentMonth = isLive ? liveMonths[liveMonths.length - 1] : now.getMonth()
  const valueAt = (limitKey: string): number | null => series[seriesKey(limitKey)][currentMonth] ?? null

  const paramKeys = Object.keys(COMPLIANCE_LIMITS)
  // Only parameters that actually have a measurement are judged. A missing value is
  // never treated as a pass, and never substituted with a sample number.
  const measured = paramKeys.filter(k => valueAt(k) !== null)
  const passing = measured.filter(k => isPass(k, valueAt(k) as number))
  const allPass = measured.length > 0 && passing.length === measured.length

  const month = now.getMonth() + 1
  const currentPhase = month <= 3 ? 'Phase 1: Pre-load' : month <= 5 ? 'Phase 2: Ramp' : month <= 9 ? 'Phase 3: Peak' : 'Phase 4: Recovery'

  const alertColor = ALERT_COLORS[alertLevel]
  const alertLevelLabel = ALERT_LABELS[alertLevel]

  // Traffic-light signal (consistent with the higher-tier role dashboards).
  // Sample data is never green/red — it is 'blue' (awaiting real results).
  const light: TrafficLight = !isLive
    ? 'blue'
    : (!allPass || alertLevel >= 3 ? 'red' : alertLevel === 2 ? 'yellow' : 'green')
  const lightStyle = LIGHT_STYLE[light]

  const alertBg: Record<number, string> = { 1: '#C6EFCE', 2: '#FFEB9C', 3: '#FFD5A8', 4: '#FFC7CE' }
  const alertText: Record<number, string> = { 1: '#006100', 2: '#856404', 3: '#7A3B00', 4: '#9C0006' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <PageHeader
        title="Dubai Lagoon Management Plan"
        subtitle="Dubai Municipality / Client View"
        icon="🏝️"
      />

      {!isLive && <SampleBanner />}

      {loading && <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading data…</div>}

      {/* Traffic-light status chip */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: lightStyle.bg, color: lightStyle.color, fontWeight: 700, fontSize: '0.8rem', borderRadius: 999, padding: '5px 14px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: lightStyle.dot }} />
          {lightStyle.label}
        </span>
        {activeSite && <span style={{ fontSize: '0.85rem', color: '#64748b' }}>{activeSite}</span>}
      </div>

      {/* Alert level card + KPI metrics */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'stretch' }}>
        {/* Big alert badge */}
        <div style={{
          background: alertBg[alertLevel],
          border: `2px solid ${alertColor}`,
          borderRadius: 10,
          padding: '1.25rem 1.75rem',
          minWidth: '200px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
        }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 700, color: alertText[alertLevel], letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
            Current Alert Level
          </div>
          <div style={{ fontSize: '1.35rem', fontWeight: 800, color: alertText[alertLevel], lineHeight: 1.2 }}>
            {alertLevelLabel}
          </div>
        </div>

        {/* KPI cards */}
        <div style={{ flex: 1, display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
          <div className="glass-card" style={{ flex: '1 1 140px', textAlign: 'center', padding: '1rem' }}>
            <div style={{ fontSize: '0.7rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.5rem' }}>Compliance</div>
            <div style={{ fontSize: '1.05rem', fontWeight: 800 }}>
              {measured.length === 0 ? (
                <span style={{ background: '#e0f2fe', color: '#075985', padding: '4px 14px', borderRadius: 5, fontWeight: 700 }}>
                  NO READING
                </span>
              ) : (
                <span style={{ background: allPass ? '#C6EFCE' : '#FFC7CE', color: allPass ? '#006100' : '#9C0006', padding: '4px 14px', borderRadius: 5, fontWeight: 700 }}>
                  {allPass ? 'COMPLIANT' : 'NON-COMPLIANT'}
                </span>
              )}
            </div>
            <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.4rem' }}>
              {measured.length}/{paramKeys.length} parameters measured
            </div>
          </div>

          <div className="glass-card" style={{ flex: '1 1 140px', textAlign: 'center', padding: '1rem' }}>
            <div style={{ fontSize: '0.7rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.5rem' }}>Treatment</div>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, color: '#1B3A5C' }}>6 mo</div>
            <div style={{ fontSize: '0.78rem', color: '#006100', fontWeight: 600, marginTop: '0.2rem' }}>Active</div>
            <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.2rem' }}>Continuous enzyme + aeration</div>
          </div>

          <div className="glass-card" style={{ flex: '1 1 140px', textAlign: 'center', padding: '1rem' }}>
            <div style={{ fontSize: '0.7rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.5rem' }}>Current Phase</div>
            <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#2E5D8A' }}>{currentPhase.split(':')[0]}</div>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.2rem' }}>{currentPhase.split(': ')[1] ?? ''}</div>
          </div>
        </div>
      </div>

      {/* Dubai Municipality Water Quality Compliance Status table */}
      <div className="glass-card">
        <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Dubai Municipality Water Quality Compliance Status</h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', minWidth: '700px' }}>
            <thead>
              <tr>
                {['Parameter', 'Unit', 'Compliance Limit', 'Current', 'Status', 'Margin %', 'Risk'].map(h => (
                  <th key={h} style={TH}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paramKeys.map(key => {
                const limit = COMPLIANCE_LIMITS[key]
                const val = valueAt(key)

                // No reading for this parameter: say so. Do not score it.
                if (val === null) {
                  return (
                    <tr key={key}>
                      <td style={{ ...TD, fontWeight: 500 }}>{limit.parameter}</td>
                      <td style={{ ...TD, color: '#64748b' }}>{limit.unit}</td>
                      <td style={{ ...TD, color: '#2E5D8A', fontWeight: 600 }}>{limit.display}</td>
                      <td style={{ ...TD, color: '#94a3b8' }}>—</td>
                      <td style={{ ...TD }}>
                        <span style={{ display: 'inline-block', background: '#e0f2fe', color: '#075985', fontWeight: 700, fontSize: '0.75rem', borderRadius: 4, padding: '3px 10px' }}>
                          NO READING
                        </span>
                      </td>
                      <td style={{ ...TD, color: '#94a3b8' }}>—</td>
                      <td style={{ ...TD, color: '#94a3b8' }}>—</td>
                    </tr>
                  )
                }

                const pass = isPass(key, val)
                const mPct = marginPct(key, val)
                return (
                  <tr key={key} style={{ background: pass ? 'transparent' : '#FFF5F5' }}>
                    <td style={{ ...TD, fontWeight: 500 }}>{limit.parameter}</td>
                    <td style={{ ...TD, color: '#64748b' }}>{limit.unit}</td>
                    <td style={{ ...TD, color: '#2E5D8A', fontWeight: 600 }}>{limit.display}</td>
                    <td style={{ ...TD, fontWeight: 600 }}>{fmt(val, 3)}</td>
                    <td style={{ ...TD }}>
                      <span style={{
                        display: 'inline-block',
                        background: pass ? '#C6EFCE' : '#FFC7CE',
                        color: pass ? '#006100' : '#9C0006',
                        fontWeight: 700,
                        fontSize: '0.75rem',
                        borderRadius: 4,
                        padding: '3px 10px',
                      }}>
                        {pass ? 'PASS' : 'FAIL'}
                      </span>
                    </td>
                    <td style={{ ...TD, color: mPct < 20 ? '#856404' : '#006100', fontWeight: 600 }}>
                      {mPct >= 0 ? `+${mPct.toFixed(1)}%` : `${mPct.toFixed(1)}%`}
                    </td>
                    <td style={{ ...TD, ...riskStyle(mPct, pass) }}>{riskLabel(mPct, pass)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Compliance score bar — denominator is the measured parameters, not all 10. */}
        {(() => {
          if (measured.length === 0) {
            return (
              <div style={{ marginTop: '1rem', background: '#f8fafc', borderRadius: 8, padding: '0.75rem 1rem', border: '1px solid #e2e8f0' }}>
                <span style={{ fontWeight: 700, color: '#64748b', fontSize: '0.9rem' }}>
                  No parameters measured for this month.
                </span>
              </div>
            )
          }
          const pct = Math.round((passing.length / measured.length) * 100)
          return (
            <div style={{ marginTop: '1rem', background: '#f8fafc', borderRadius: 8, padding: '0.75rem 1rem', border: '1px solid #e2e8f0' }}>
              <span style={{ fontWeight: 700, color: pct === 100 ? '#006100' : '#856404', fontSize: '0.9rem' }}>
                {pct}% Compliant ({passing.length}/{measured.length} parameters measured)
              </span>
              {measured.length < paramKeys.length && (
                <span style={{ fontSize: '0.8rem', color: '#94a3b8', marginLeft: '0.6rem' }}>
                  {paramKeys.length - measured.length} parameter(s) not measured
                </span>
              )}
            </div>
          )
        })()}
      </div>

      {/* Alert Level Reference */}
      <div className="glass-card">
        <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Alert Level Reference</h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', minWidth: '700px' }}>
            <thead>
              <tr>
                {['Level', 'Bloom Prob.', 'Chl-a', 'DO', 'Phycocyanin', 'Temp', 'Monitoring', 'Reporting'].map(h => (
                  <th key={h} style={TH}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {([1, 2, 3, 4] as const).map(level => {
                const t = ALERT_THRESHOLDS[level]
                const color = ALERT_COLORS[level]
                return (
                  <tr key={level} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 12px' }}>
                      <span style={{ background: color, color: '#fff', fontWeight: 700, fontSize: '0.75rem', borderRadius: 4, padding: '3px 10px', whiteSpace: 'nowrap', display: 'inline-block' }}>
                        {ALERT_LABELS[level]}
                      </span>
                    </td>
                    <td style={TD}>{t.bloomRange}</td>
                    <td style={TD}>{t.chla}</td>
                    <td style={TD}>{t.doVal}</td>
                    <td style={TD}>{t.phyco}</td>
                    <td style={TD}>{t.temp}</td>
                    <td style={TD}>{t.monitoring}</td>
                    <td style={TD}>{t.reporting}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Current Conditions Summary — every figure comes from the same series as the
          table above, so this panel can no longer mix seasonal sample values into a
          live diagnosis. */}
      <div className="glass-card">
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.75rem' }}>Current Conditions Summary</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
          {([
            { label: 'pH', key: 'ph' as ParamKey, unit: 'pH units', ok: (v: number) => isPass('ph', v) },
            { label: 'Dissolved Oxygen', key: 'do' as ParamKey, unit: 'mg/L', ok: (v: number) => isPass('do', v) },
            { label: 'Chlorophyll-a', key: 'chla' as ParamKey, unit: 'µg/L', ok: (v: number) => v < 10 },
            { label: 'Phycocyanin', key: 'phycocyanin' as ParamKey, unit: 'µg/L', ok: (v: number) => v < 50 },
            { label: 'Water Temperature', key: 'water_temp' as ParamKey, unit: '°C', ok: () => true },
            { label: 'Salinity', key: 'salinity' as ParamKey, unit: 'PSU', ok: () => true },
          ]).map(item => {
            const v = series[item.key][currentMonth] ?? null
            const ok = v === null ? true : item.ok(v)
            return (
              <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.6rem 0.85rem', background: '#f8fafc', borderRadius: 6, border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: '0.85rem', color: '#374151' }}>{item.label}</span>
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: v === null ? '#94a3b8' : ok ? '#006100' : '#9C0006' }}>
                  {v === null ? '—' : `${fmt(v)} ${item.unit}`}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
