// Traffic-light business-intelligence signal shared by every role dashboard, so the
// meaning is consistent across the Supervisor, Project, Portfolio, and Executive views.
//
//   🟢 green  — fully compliant
//   🟡 yellow — warning / action required
//   🔴 red    — non-compliant / critical
//   🔵 blue   — awaiting laboratory results (no readings yet)
//
// Derived from the shape returned by GET /api/status/{site}:
//   { readings: [{ month, compliance, compliance_pct, alert_level, alert_label,
//                  failing_params, ...paramValues }] }

export type TrafficLight = 'green' | 'yellow' | 'red' | 'blue'

export interface SiteReading {
  month?: string
  compliance?: string          // "COMPLIANT" | "NON-COMPLIANT"
  compliance_pct?: number
  alert_level?: 1 | 2 | 3 | 4
  alert_label?: string
  failing_params?: string[]
  [param: string]: unknown
}

export interface SiteStatus {
  site: string
  light: TrafficLight
  /** Latest reading, or null when awaiting lab results. */
  latest: SiteReading | null
  /** % of parameters compliant on the latest reading (0–100), null when unknown. */
  compliancePct: number | null
  /** Names of failing parameters on the latest reading. */
  failingParams: string[]
  /** Alert level 1–4, or null when no readings. */
  alertLevel: 1 | 2 | 3 | 4 | null
}

/** Visual tokens for a traffic-light value — aligned with the app's .badge-* palette. */
export const LIGHT_STYLE: Record<TrafficLight, { bg: string; color: string; dot: string; label: string }> = {
  green:  { bg: '#C6EFCE', color: '#006100', dot: '#27ae60', label: 'Compliant' },
  yellow: { bg: '#FFEB9C', color: '#856404', dot: '#f39c12', label: 'Action Required' },
  red:    { bg: '#FFC7CE', color: '#9C0006', dot: '#e74c3c', label: 'Critical' },
  blue:   { bg: '#D6E4F0', color: '#1B3A5C', dot: '#3b82f6', label: 'Awaiting Lab' },
}

/** Reduce a single reading to a traffic-light value. */
export function lightForReading(reading: SiteReading | null | undefined): TrafficLight {
  if (!reading) return 'blue'
  const level = reading.alert_level ?? 1
  const nonCompliant =
    (reading.compliance ?? '').toUpperCase().includes('NON') ||
    (reading.failing_params?.length ?? 0) > 0
  if (level >= 3 || nonCompliant) return 'red'
  if (level === 2) return 'yellow'
  return 'green'
}

/** Reduce a site's /api/status readings array to a single SiteStatus summary. */
export function statusFromReadings(site: string, readings: SiteReading[] | null | undefined): SiteStatus {
  const latest = readings && readings.length > 0 ? readings[readings.length - 1] : null
  return {
    site,
    latest,
    light: lightForReading(latest),
    compliancePct: latest?.compliance_pct ?? null,
    failingParams: latest?.failing_params ?? [],
    alertLevel: latest?.alert_level ?? null,
  }
}

/**
 * Fetch and summarise the traffic-light status for many sites in parallel.
 * MVP client-side fan-out over the existing per-site endpoint; a backend
 * /api/portfolio aggregate is a documented follow-up if this proves slow.
 */
export async function fetchPortfolioStatus(
  sites: string[],
  opts: { organizationId?: string | null; token?: string | null; year?: number } = {},
): Promise<SiteStatus[]> {
  const headers: HeadersInit = {}
  if (opts.organizationId) headers['X-Organization-ID'] = opts.organizationId
  if (opts.token) headers['Authorization'] = `Bearer ${opts.token}`
  const year = opts.year ?? new Date().getFullYear()

  const results = await Promise.all(
    sites.map(async (site) => {
      try {
        const res = await fetch(`/api/status/${encodeURIComponent(site)}?year=${year}`, { headers })
        if (!res.ok) return statusFromReadings(site, null)
        const data = await res.json()
        return statusFromReadings(site, data.readings)
      } catch {
        return statusFromReadings(site, null)
      }
    }),
  )
  return results
}

/** Portfolio-level KPI rollup used by the GM and Executive dashboards. */
export interface PortfolioKpis {
  total: number
  green: number
  yellow: number
  red: number
  blue: number
  /** Mean of known compliance_pct values (0–100), null when none reported. */
  avgCompliancePct: number | null
  /** Sites needing management attention (yellow + red). */
  needsAttention: number
}

export function rollup(statuses: SiteStatus[]): PortfolioKpis {
  const counts = { green: 0, yellow: 0, red: 0, blue: 0 }
  let pctSum = 0
  let pctCount = 0
  for (const s of statuses) {
    counts[s.light] += 1
    if (typeof s.compliancePct === 'number') {
      pctSum += s.compliancePct
      pctCount += 1
    }
  }
  return {
    total: statuses.length,
    ...counts,
    avgCompliancePct: pctCount > 0 ? Math.round(pctSum / pctCount) : null,
    needsAttention: counts.yellow + counts.red,
  }
}
