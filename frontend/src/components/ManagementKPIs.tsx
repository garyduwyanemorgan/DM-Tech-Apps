import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { hasPermission } from '../lib/permissions'
import { PageHeader } from './PageHeader'
import { COLORS } from '../lib/ui'
import { MetricCard } from './ui'

interface Kpi {
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
