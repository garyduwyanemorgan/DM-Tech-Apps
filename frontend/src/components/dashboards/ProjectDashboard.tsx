import React from 'react'
import { PageHeader } from '../PageHeader'
import { usePortfolio } from './usePortfolio'
import { LIGHT_STYLE } from '../../lib/status'
import { ChevronRight } from 'lucide-react'

interface Props {
  setActiveSite: (s: string) => void
  setActiveTab: (t: string) => void
}

/**
 * Tier 2 — Project / Contract Manager view.
 * Per-project summary: overall compliance traffic light, outstanding actions, key
 * risks. No individual lab values unless the user drills into a site's detail.
 */
export const ProjectDashboard: React.FC<Props> = ({ setActiveSite, setActiveTab }) => {
  const { loading, error, statuses } = usePortfolio()

  const drill = (site: string) => {
    setActiveSite(site)
    setActiveTab('monitoring')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <PageHeader
        title="Project Compliance Summary"
        subtitle="Project / Contract Manager view — overall status, outstanding actions, key risks"
        icon="📋"
      />

      {loading && <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading projects…</div>}
      {error && <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.75rem 1rem', borderRadius: 6 }}>{error}</div>}
      {!loading && !error && statuses.length === 0 && (
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: '3rem', textAlign: 'center', color: '#94a3b8' }}>
          No projects found for your organisation yet.
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
        {statuses.map((s) => {
          const style = LIGHT_STYLE[s.light]
          const actions = s.failingParams.length
          return (
            <div
              key={s.site}
              className="glass-card"
              onClick={() => drill(s.site)}
              style={{ cursor: 'pointer', borderLeft: `5px solid ${style.dot}`, display: 'flex', flexDirection: 'column', gap: '0.85rem' }}
            >
              {/* Header row: project name + traffic-light chip */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ fontWeight: 700, fontSize: '1.05rem', color: '#1B3A5C' }}>{s.site}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: style.bg, color: style.color, fontWeight: 700, fontSize: '0.72rem', borderRadius: 999, padding: '3px 11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: style.dot }} />
                  {style.label}
                </span>
              </div>

              {/* Compliance + actions */}
              <div style={{ display: 'flex', gap: '1.5rem' }}>
                <div>
                  <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Compliance</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: style.color }}>
                    {s.compliancePct === null ? '—' : `${s.compliancePct}%`}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Outstanding actions</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: actions > 0 ? '#9C0006' : '#006100' }}>{actions}</div>
                </div>
              </div>

              {/* Key risks */}
              <div>
                <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.3rem' }}>Key risks</div>
                {actions > 0 ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                    {s.failingParams.map((p) => (
                      <span key={p} style={{ background: '#FFC7CE', color: '#9C0006', fontSize: '0.72rem', fontWeight: 600, borderRadius: 4, padding: '2px 8px' }}>{p}</span>
                    ))}
                  </div>
                ) : (
                  <span style={{ fontSize: '0.8rem', color: s.light === 'blue' ? '#1B3A5C' : '#006100' }}>
                    {s.light === 'blue' ? 'Awaiting laboratory results' : 'No outstanding compliance issues'}
                  </span>
                )}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#2E5D8A', fontSize: '0.8rem', fontWeight: 600, marginTop: 'auto' }}>
                View detail <ChevronRight size={15} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
