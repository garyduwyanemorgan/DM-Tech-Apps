import React from 'react'
import { PageHeader } from '../PageHeader'
import { usePortfolio } from './usePortfolio'
import { LIGHT_STYLE } from '../../lib/status'

interface Props {
  setActiveSite: (s: string) => void
  setActiveTab: (t: string) => void
}

const KpiTile: React.FC<{ label: string; value: string | number; color?: string; sub?: string }> = ({ label, value, color = '#1B3A5C', sub }) => (
  <div className="glass-card" style={{ textAlign: 'center', padding: '1.1rem 1rem' }}>
    <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.45rem' }}>{label}</div>
    <div style={{ fontSize: '1.7rem', fontWeight: 800, color }}>{value}</div>
    {sub && <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.25rem' }}>{sub}</div>}
  </div>
)

/**
 * Tier 3 — General Manager view.
 * Portfolio across all projects: each project a status dot, plus organisation-wide
 * KPIs (% compliant, projects needing attention, awaiting-lab count).
 */
export const PortfolioDashboard: React.FC<Props> = ({ setActiveSite, setActiveTab }) => {
  const { loading, error, statuses, kpis } = usePortfolio()

  const drill = (site: string) => {
    setActiveSite(site)
    setActiveTab('monitoring')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <PageHeader
        title="Portfolio Overview"
        subtitle="General Manager view — all projects at a glance"
        icon="🗂️"
      />

      {loading && <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading portfolio…</div>}
      {error && <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.75rem 1rem', borderRadius: 6 }}>{error}</div>}

      {/* KPI rollup */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem' }}>
        <KpiTile label="Projects" value={kpis.total} />
        <KpiTile label="Avg. Compliance" value={kpis.avgCompliancePct === null ? '—' : `${kpis.avgCompliancePct}%`} color={kpis.avgCompliancePct !== null && kpis.avgCompliancePct >= 90 ? '#006100' : '#856404'} />
        <KpiTile label="Needs Attention" value={kpis.needsAttention} color={kpis.needsAttention > 0 ? '#9C0006' : '#006100'} sub="Yellow + Red" />
        <KpiTile label="Awaiting Lab" value={kpis.blue} color="#1B3A5C" />
      </div>

      {/* Status-dot grid */}
      <div className="glass-card">
        <h2 className="section-heading" style={{ fontSize: '1rem', marginBottom: '1rem' }}>Project Status</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.75rem' }}>
          {statuses.map((s) => {
            const style = LIGHT_STYLE[s.light]
            return (
              <button
                key={s.site}
                onClick={() => drill(s.site)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.7rem', width: '100%',
                  padding: '0.7rem 0.9rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left',
                  background: '#f8fafc', border: '1px solid #e2e8f0', fontFamily: 'inherit',
                }}
              >
                <span style={{ width: 14, height: 14, borderRadius: '50%', background: style.dot, flexShrink: 0, boxShadow: `0 0 0 3px ${style.bg}` }} />
                <span style={{ display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontWeight: 700, color: '#1B3A5C', fontSize: '0.9rem' }}>{s.site}</span>
                  <span style={{ fontSize: '0.72rem', color: style.color, fontWeight: 600 }}>
                    {style.label}{s.compliancePct !== null ? ` · ${s.compliancePct}%` : ''}
                  </span>
                </span>
              </button>
            )
          })}
          {!loading && statuses.length === 0 && (
            <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>No projects found.</span>
          )}
        </div>
      </div>
    </div>
  )
}
