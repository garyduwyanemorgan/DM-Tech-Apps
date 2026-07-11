import React from 'react'
import { PageHeader } from '../PageHeader'
import { usePortfolio } from './usePortfolio'
import { LIGHT_STYLE } from '../../lib/status'
import { TrendingUp, AlertTriangle, ShieldCheck, Layers } from 'lucide-react'

interface Props {
  setActiveSite: (s: string) => void
  setActiveTab: (t: string) => void
}

const MetricCard: React.FC<{ icon: React.ReactNode; label: string; value: string; accent: string; sub?: string }> = ({ icon, label, value, accent, sub }) => (
  <div className="glass-card" style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '1.1rem 1.25rem' }}>
    <div style={{ width: 44, height: 44, borderRadius: 10, background: `${accent}1A`, color: accent, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
      {icon}
    </div>
    <div>
      <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
      <div style={{ fontSize: '1.55rem', fontWeight: 800, color: '#1B3A5C', lineHeight: 1.15 }}>{value}</div>
      {sub && <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>{sub}</div>}
    </div>
  </div>
)

/**
 * Tier 4 — Executive Management view.
 * High-level business metrics across the whole organisation, plus a shortlist of
 * projects requiring management attention (drill-down on demand).
 */
export const ExecutiveDashboard: React.FC<Props> = ({ setActiveSite, setActiveTab }) => {
  const { loading, error, statuses, kpis } = usePortfolio()

  const attention = statuses
    .filter((s) => s.light === 'red' || s.light === 'yellow')
    .sort((a, b) => (a.light === 'red' ? -1 : 1) - (b.light === 'red' ? -1 : 1))

  const compliantRate = kpis.total > 0 ? Math.round((kpis.green / kpis.total) * 100) : null

  const drill = (site: string) => {
    setActiveSite(site)
    setActiveTab('monitoring')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <PageHeader
        title="Executive Overview"
        subtitle="Organisation-wide compliance, performance, and regulatory risk"
        icon="📈"
      />

      {loading && <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading organisation metrics…</div>}
      {error && <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.75rem 1rem', borderRadius: 6 }}>{error}</div>}

      {/* Business metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: '1rem' }}>
        <MetricCard icon={<ShieldCheck size={22} />} label="Overall Compliance" value={kpis.avgCompliancePct === null ? '—' : `${kpis.avgCompliancePct}%`} accent="#27ae60" sub="Mean across projects" />
        <MetricCard icon={<Layers size={22} />} label="Projects Fully Compliant" value={compliantRate === null ? '—' : `${kpis.green}/${kpis.total}`} accent="#2E5D8A" sub={compliantRate === null ? undefined : `${compliantRate}% green`} />
        <MetricCard icon={<AlertTriangle size={22} />} label="Regulatory Risk" value={String(kpis.red)} accent="#e74c3c" sub="Projects critical / non-compliant" />
        <MetricCard icon={<TrendingUp size={22} />} label="Needs Attention" value={String(kpis.needsAttention)} accent="#f39c12" sub="Warning + critical" />
      </div>

      {/* Projects needing attention */}
      <div className="glass-card">
        <h2 className="section-heading" style={{ fontSize: '1rem', marginBottom: '1rem' }}>Projects Requiring Management Attention</h2>
        {attention.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', color: '#006100', fontSize: '0.9rem', fontWeight: 600 }}>
            <ShieldCheck size={18} /> All projects within compliance — no escalations.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {attention.map((s) => {
              const style = LIGHT_STYLE[s.light]
              return (
                <button
                  key={s.site}
                  onClick={() => drill(s.site)}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', width: '100%',
                    padding: '0.7rem 1rem', borderRadius: 8, cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
                    background: '#f8fafc', border: `1px solid #e2e8f0`, borderLeft: `4px solid ${style.dot}`,
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.7rem' }}>
                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: style.dot }} />
                    <span style={{ fontWeight: 700, color: '#1B3A5C', fontSize: '0.92rem' }}>{s.site}</span>
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                    {s.failingParams.length > 0 && (
                      <span style={{ fontSize: '0.75rem', color: '#9C0006' }}>{s.failingParams.length} action{s.failingParams.length > 1 ? 's' : ''}</span>
                    )}
                    <span style={{ background: style.bg, color: style.color, fontWeight: 700, fontSize: '0.72rem', borderRadius: 999, padding: '3px 11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      {style.label}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
