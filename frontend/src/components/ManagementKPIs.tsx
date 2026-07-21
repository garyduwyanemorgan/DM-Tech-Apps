import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { hasPermission } from '../lib/permissions'
import { PageHeader } from './PageHeader'
import { COLORS } from '../lib/ui'
import { MetricCard, StatusBadge } from './ui'

/**
 * Certificate compliance roll-up, exactly as `/api/kpi/{scope}` returns it.
 * Nothing on this page derives, totals or infers a verdict — INCOMPLETE and
 * "no verdict" are carried through as their own counts and are never folded
 * into `compliant`.
 */
interface ComplianceKpi {
  certificates: number
  compliant: number
  non_compliant: number
  incomplete: number
  no_verdict: number
  pending_review: number
  failing_parameters: number
  latest_sampled_at: string | null
}

interface Kpi {
  compliance?: ComplianceKpi
  corrective_actions?: { total?: number; open?: number; pending_approval?: number; closed?: number }
  inventory?: { item_count?: number; low_stock_items?: number; total_valuation?: number }
}

export const ManagementKPIs: React.FC = () => {
  const { organizationId, token, role } = useAuth()
  // Executive scope wins when available; otherwise portfolio (General Manager+).
  const canExec = hasPermission(role, 'analytics.executive.read')
  const canPortfolio = hasPermission(role, 'analytics.portfolio.read')
  const scope = canExec ? 'executive' : 'portfolio'

  const [kpi, setKpi] = useState<Kpi | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const makeHeaders = useCallback((): HeadersInit => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [token, organizationId])

  useEffect(() => {
    if (!canPortfolio && !canExec) return
    setLoading(true); setError(null)
    fetch(`/api/kpi/${scope}`, { headers: makeHeaders() })
      .then(async res => {
        const data = await res.json()
        if (!res.ok) { setError(data.detail || 'Failed to load KPIs.'); return }
        setKpi(data.kpi)
      })
      .catch(() => setError('Network error loading KPIs.'))
      .finally(() => setLoading(false))
  }, [scope, makeHeaders, canPortfolio, canExec])

  if (!canPortfolio && !canExec) {
    return (
      <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
        <PageHeader title="Management KPIs" subtitle="Portfolio and executive metrics" />
        <div className="glass-card" style={{ textAlign: 'center', color: COLORS.slate }}>
          Your role does not have access to management KPIs.
        </div>
      </div>
    )
  }

  const comp = kpi?.compliance
  const ca = kpi?.corrective_actions || {}
  const inv = kpi?.inventory || {}
  const cards = [
    { label: 'Open Actions', value: ca.open ?? 0, color: (ca.open ?? 0) ? COLORS.amberFg : COLORS.greenFg, sub: 'open + in progress' },
    { label: 'Pending Approval', value: ca.pending_approval ?? 0, color: (ca.pending_approval ?? 0) ? COLORS.navy : COLORS.slate, sub: 'awaiting sign-off' },
    { label: 'Closed Actions', value: ca.closed ?? 0, color: COLORS.greenFg, sub: 'resolved' },
    { label: 'Stock Items', value: inv.item_count ?? 0, color: COLORS.navy, sub: 'tracked SKUs' },
    { label: 'Low Stock', value: inv.low_stock_items ?? 0, color: (inv.low_stock_items ?? 0) ? COLORS.redFg : COLORS.greenFg, sub: 'at/below reorder' },
    ...(inv.total_valuation != null ? [{ label: 'Inventory Value', value: `$${Number(inv.total_valuation).toLocaleString()}`, color: COLORS.navy, sub: 'on-hand valuation' }] : []),
  ]

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader title="Management KPIs" subtitle={`${scope === 'executive' ? 'Organization-wide executive' : 'Portfolio'} health · corrective actions and inventory`} />
      {error && <div style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #fecaca' }}>{error}</div>}

      {/* ─── LABORATORY CERTIFICATE COMPLIANCE ──────────────────────────
          First on the page: it is the reason the page gets opened. Every
          number below is rendered straight from the API payload. */}
      <div className="glass-card" style={{ marginBottom: 24, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <h2 className="section-heading" style={{ fontSize: '1.1rem', fontWeight: 700, color: COLORS.navy, marginBottom: '0.35rem' }}>
            Laboratory Certificate Compliance
          </h2>
          <p style={{ fontSize: '0.9rem', color: COLORS.slate, margin: 0 }}>
            Verdicts recorded on saved certificates across the {scope === 'executive' ? 'organization' : 'portfolio'}
            {comp?.latest_sampled_at ? ` · most recent sample ${comp.latest_sampled_at}` : ''}.
          </p>
        </div>

        {loading ? (
          <p style={{ color: COLORS.slateLight, fontSize: '0.875rem', margin: 0 }}>Loading compliance figures…</p>
        ) : !comp ? (
          // A failed or incomplete response must never read as "nothing is wrong".
          <div style={{ padding: '1rem', border: `1px solid ${COLORS.redBorder}`, background: COLORS.redBg, color: COLORS.redFg, borderRadius: 8, fontSize: '0.875rem' }}>
            <strong>Certificate compliance data is unavailable.</strong> The figures could not be
            loaded, so no count is shown — this is not a statement that there are zero certificates
            or zero failures.
          </div>
        ) : comp.certificates === 0 ? (
          <div style={{ padding: '1.5rem', textAlign: 'center', border: `1px dashed ${COLORS.border}`, borderRadius: 8, background: COLORS.surface }}>
            <p style={{ fontSize: '0.9rem', color: '#374151', fontWeight: 600, margin: 0 }}>
              No laboratory certificates saved yet.
            </p>
            <p style={{ fontSize: '0.82rem', color: COLORS.slate, margin: '0.4rem 0 0' }}>
              Certificates appear here once you save one from <strong>Upload Lab Report</strong> —
              saving is the point at which you confirm the extracted result is correct.
            </p>
          </div>
        ) : (
          <>
            <div className="grid-cols-3">
              <MetricCard label="Certificates" value={comp.certificates} valueColor={COLORS.navy} sub="saved lab certificates" />
              <MetricCard label="Compliant" value={comp.compliant} valueColor={COLORS.greenFg} sub="met the cited specification" />
              <MetricCard label="Not Compliant" value={comp.non_compliant} valueColor={COLORS.redFg} sub="a parameter exceeded the specification" />
              <MetricCard label="Incomplete" value={comp.incomplete} valueColor={COLORS.amberFg} sub="Incomplete — not a pass; parameters were not assessed" />
              <MetricCard label="No Verdict Recorded" value={comp.no_verdict} valueColor={COLORS.slate} sub="the certificate carries no overall status" />
            </div>

            {/* The two numbers that drive action. */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', paddingTop: '0.5rem', borderTop: `1px solid ${COLORS.border}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <StatusBadge tone={comp.pending_review > 0 ? 'amber' : 'slate'} variant="count">
                  {comp.pending_review} awaiting review
                </StatusBadge>
                <span style={{ fontSize: '0.82rem', color: COLORS.slate }}>
                  Certificates not yet approved by a reviewer — not settled compliance records.
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <StatusBadge tone={comp.failing_parameters > 0 ? 'red' : 'slate'} variant="count">
                  {comp.failing_parameters} failing parameters
                </StatusBadge>
                <span style={{ fontSize: '0.82rem', color: COLORS.slate }}>
                  Individual results outside their specification.
                </span>
              </div>
            </div>

            <p style={{ fontSize: '0.78rem', color: COLORS.slateLight, margin: 0 }}>
              Incomplete certificates are counted separately and are never included in the
              compliant total.
            </p>
          </>
        )}
      </div>

      {loading ? (
        <div className="glass-card" style={{ textAlign: 'center', color: COLORS.slate }}>Loading KPIs…</div>
      ) : (
        <div className="grid-cols-3">
          {cards.map(c => (
            <MetricCard key={c.label} label={c.label} value={c.value} valueColor={c.color} sub={c.sub} />
          ))}
        </div>
      )}
    </div>
  )
}
