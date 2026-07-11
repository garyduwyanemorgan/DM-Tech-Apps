import { useEffect, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { fetchPortfolioStatus, rollup, type SiteStatus, type PortfolioKpis } from '../../lib/status'

export interface PortfolioData {
  loading: boolean
  error: string | null
  statuses: SiteStatus[]
  kpis: PortfolioKpis
  reload: () => void
}

/**
 * Loads every site in the org and summarises each to a traffic-light status,
 * plus a portfolio KPI rollup. Shared by the Project, Portfolio, and Executive
 * dashboards so the aggregation logic lives in one place.
 */
export function usePortfolio(): PortfolioData {
  const { organizationId, token } = useAuth()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statuses, setStatuses] = useState<SiteStatus[]>([])
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const headers: HeadersInit = {}
        if (organizationId) headers['X-Organization-ID'] = organizationId
        if (token) headers['Authorization'] = `Bearer ${token}`
        const res = await fetch('/api/sites', { headers })
        const data = await res.json()
        const names: string[] = (data.sites ?? []).map((s: unknown) =>
          typeof s === 'string' ? s : (s as { name: string }).name,
        )
        const result = await fetchPortfolioStatus(names, { organizationId, token })
        if (!cancelled) setStatuses(result)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load portfolio')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [organizationId, token, nonce])

  return { loading, error, statuses, kpis: rollup(statuses), reload: () => setNonce((n) => n + 1) }
}
