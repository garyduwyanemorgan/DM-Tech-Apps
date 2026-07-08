import React, { useEffect, useState } from 'react'
import { PageHeader } from './PageHeader'
import { useAuth } from '../context/AuthContext'
import { COMPLIANCE_LIMITS, MONTHLY_DATA, ALERT_THRESHOLDS, ALERT_COLORS, ALERT_LABELS } from '../constants'

interface DashboardProps {
  activeSite: string
  useSampleData?: boolean
}

const SAMPLE_CURRENT: Record<string, number> = {
  ph:              7.1,
  do:              5.7,
  tss:             12.0,
  turbidity:       22.0,
  cod:             24.0,
  ammonia:         2.8,
  phosphate:       3.2,
  oil_grease:      1.8,
  ecoli:           71.0,
  total_coliforms: 223.0,
}

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

export const Dashboard: React.FC<DashboardProps> = ({ activeSite, useSampleData = true }) => {
  const { organizationId, token } = useAuth()
  const [apiCurrentValues, setApiCurrentValues] = useState<Record<string, number> | null>(null)
  const [loading, setLoading] = useState(false)
  const [alertLevel, setAlertLevel] = useState<1 | 2 | 3 | 4>(1)

  useEffect(() => {
    if (activeSite) fetchStatus()
  }, [activeSite])

  const fetchStatus = async () => {
    setLoading(true)
    try {
      const headers: HeadersInit = {}
      if (organizationId) headers['X-Organization-ID'] = organizationId
      if (token) headers['Authorization'] = `Bearer ${token}`
      const res = await fetch(`/api/status/${activeSite}`, { headers })
      const data = await res.json()
      if (data.readings && data.readings.length > 0) {
        const latest = data.readings[data.readings.length - 1]
        setAlertLevel((latest.alert_level ?? 1) as 1 | 2 | 3 | 4)
        setApiCurrentValues({
          ph: latest.ph ?? SAMPLE_CURRENT.ph,
          do: latest.do ?? SAMPLE_CURRENT.do,
          tss: latest.tss ?? SAMPLE_CURRENT.tss,
          turbidity: latest.turbidity ?? SAMPLE_CURRENT.turbidity,
          cod: latest.cod ?? SAMPLE_CURRENT.cod,
          ammonia: latest.ammonia ?? SAMPLE_CURRENT.ammonia,
          phosphate: latest.phosphate ?? SAMPLE_CURRENT.phosphate,
          oil_grease: latest.oil_grease ?? SAMPLE_CURRENT.oil_grease,
          ecoli: latest.ecoli ?? SAMPLE_CURRENT.ecoli,
          total_coliforms: latest.total_coliforms ?? SAMPLE_CURRENT.total_coliforms,
        })
      } else {
        setApiCurrentValues(null)
        setAlertLevel(1)
      }
    } catch (err) {
      console.error(err)
      setApiCurrentValues(null)
    } finally {
      setLoading(false)
    }
  }

  const hasLiveData = apiCurrentValues !== null
  const currentValues = hasLiveData ? apiCurrentValues : (useSampleData ? SAMPLE_CURRENT : null)
  const isUsingApiData = hasLiveData

  if (!currentValues) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Dubai Lagoon Management Plan" subtitle="Dubai Municipality / Client View" icon="🏝️" />
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: '3rem', textAlign: 'center', color: '#94a3b8' }}>
          <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>📊</div>
          <div style={{ fontWeight: 600, color: '#64748b', marginBottom: '0.5rem' }}>No data to display</div>
          <div style={{ fontSize: '0.875rem' }}>Sample data is disabled. Select a live site or enable sample data in Settings.</div>
        </div>
      </div>
    )
  }

  const paramKeys = Object.keys(COMPLIANCE_LIMITS)
  const allPass = paramKeys.every(k => isPass(k, currentValues[k] ?? 0))

  // Current month for phase info
  const now = new Date()
  const month = now.getMonth() + 1
  const currentPhase = month <= 3 ? 'Phase 1: Pre-load' : month <= 5 ? 'Phase 2: Ramp' : month <= 9 ? 'Phase 3: Peak' : 'Phase 4: Recovery'

  const alertColor = ALERT_COLORS[alertLevel]
  const alertLevelLabel = ALERT_LABELS[alertLevel]

  const alertBg: Record<number, string> = { 1: '#C6EFCE', 2: '#FFEB9C', 3: '#FFD5A8', 4: '#FFC7CE' }
  const alertText: Record<number, string> = { 1: '#006100', 2: '#856404', 3: '#7A3B00', 4: '#9C0006' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <PageHeader
        title="Dubai Lagoon Management Plan"
        subtitle="Dubai Municipality / Client View"
        icon="🏝️"
      />

      {!isUsingApiData && (
        <div style={{ background: '#FFEB9C', color: '#856404', padding: '0.65rem 1rem', borderRadius: 6, fontSize: '0.875rem', border: '1px solid #fcd34d' }}>
          Using sample data — select a site with submitted readings in the sidebar for a live diagnosis.
        </div>
      )}

      {loading && <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading data…</div>}

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
              <span style={{ background: allPass ? '#C6EFCE' : '#FFC7CE', color: allPass ? '#006100' : '#9C0006', padding: '4px 14px', borderRadius: 5, fontWeight: 700 }}>
                {allPass ? 'COMPLIANT' : 'NON-COMPLIANT'}
              </span>
            </div>
            <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.4rem' }}>All 10 parameters</div>
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
                const val = currentValues[key] ?? 0
                const pass = isPass(key, val)
                const mPct = marginPct(key, val)
                return (
                  <tr key={key} style={{ background: pass ? 'transparent' : '#FFF5F5' }}>
                    <td style={{ ...TD, fontWeight: 500 }}>{limit.parameter}</td>
                    <td style={{ ...TD, color: '#64748b' }}>{limit.unit}</td>
                    <td style={{ ...TD, color: '#2E5D8A', fontWeight: 600 }}>{limit.display}</td>
                    <td style={{ ...TD, fontWeight: 600 }}>{val.toFixed(3)}</td>
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

        {/* Compliance score bar */}
        {(() => {
          const passing = paramKeys.filter(k => isPass(k, currentValues[k] ?? 0)).length
          const pct = Math.round((passing / paramKeys.length) * 100)
          return (
            <div style={{ marginTop: '1rem', background: '#f8fafc', borderRadius: 8, padding: '0.75rem 1rem', border: '1px solid #e2e8f0' }}>
              <span style={{ fontWeight: 700, color: pct === 100 ? '#006100' : '#856404', fontSize: '0.9rem' }}>
                {pct}% Compliant ({passing}/{paramKeys.length} parameters)
              </span>
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

      {/* Current Conditions Summary */}
      <div className="glass-card">
        <h2 style={{ fontSize: '1.1rem', marginBottom: '0.75rem' }}>Current Conditions Summary</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
          {[
            { label: 'pH', value: `${currentValues.ph?.toFixed(2)} pH units`, ok: isPass('ph', currentValues.ph ?? 0) },
            { label: 'Dissolved Oxygen', value: `${currentValues.do?.toFixed(2)} mg/L`, ok: isPass('do', currentValues.do ?? 0) },
            { label: 'Chlorophyll-a', value: `${MONTHLY_DATA.chla[now.getMonth()]} µg/L (seasonal)`, ok: MONTHLY_DATA.chla[now.getMonth()] < 10 },
            { label: 'Phycocyanin', value: `${MONTHLY_DATA.phycocyanin[now.getMonth()]} µg/L (seasonal)`, ok: MONTHLY_DATA.phycocyanin[now.getMonth()] < 50 },
            { label: 'Water Temperature', value: `${MONTHLY_DATA.water_temp[now.getMonth()]}°C (seasonal)`, ok: true },
            { label: 'Salinity', value: `${MONTHLY_DATA.salinity[now.getMonth()]} PSU (seasonal)`, ok: true },
          ].map(item => (
            <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.6rem 0.85rem', background: '#f8fafc', borderRadius: 6, border: '1px solid #e2e8f0' }}>
              <span style={{ fontSize: '0.85rem', color: '#374151' }}>{item.label}</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: item.ok ? '#006100' : '#9C0006' }}>{item.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
