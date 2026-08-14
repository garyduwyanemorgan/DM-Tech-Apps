// Traffic-light business-intelligence signal shared by every role dashboard, so the
// meaning is consistent across the Supervisor, Project, Portfolio, and Executive views.
//
//   🟢 green  — fully compliant
//   🟡 yellow — warning / action required
//   🔴 red    — non-compliant / critical
//   🔵 blue   — awaiting laboratory results (no readings yet)
//   ⚪ grey   — a reading exists but could not be judged (INCOMPLETE /
//              NOT_ASSESSED / an unrecognised verdict). Deliberately neither
//              green nor red: "this certificate does not say" is a third answer,
//              and rendering it as a pass is the exact failure DM_COMPLIANCE_SCOPING
//              §7.4 forbids.
//
// Derived from the shape returned by GET /api/status/{site}:
//   { readings: [{ month, compliance, compliance_pct, alert_level, alert_label,
//                  failing_params, ...paramValues }] }

import { STATUS } from './tokens'

export type TrafficLight = 'green' | 'yellow' | 'red' | 'blue' | 'grey'

/**
 * Canonical certificate verdict. The producers disagree on spelling —
 * `core/calculations.py:compliance_summary` emits `NON-COMPLIANT` (hyphen)
 * while `ingestion/schema.py:ComplianceStatus`, the database and `core/specs.py`
 * use `NON_COMPLIANT` (underscore) — so every raw string is normalised once, at
 * this boundary, by `normaliseVerdict`. Nothing downstream pattern-matches on
 * the wire spelling.
 */
export type ComplianceVerdict =
  | 'COMPLIANT'
  | 'NON_COMPLIANT'
  | 'INCOMPLETE'
  | 'NOT_ASSESSED'
  | 'UNKNOWN'

/**
 * Map a raw verdict string from any producer onto the canonical set.
 *
 * Hyphen, underscore and whitespace are treated as the same separator; case is
 * ignored. Anything not in the known vocabulary — including an absent or empty
 * value — is `UNKNOWN`, which is rendered as "cannot be judged", never as a
 * pass. This replaces the previous `.includes('NON')` substring test, which
 * both over-matched (any future status containing `NON` read as a breach) and
 * under-matched (`INCOMPLETE` fell through to the compliant branch).
 */
export function normaliseVerdict(raw: string | null | undefined): ComplianceVerdict {
  const key = (raw ?? '').trim().toUpperCase().replace(/[\s-]+/g, '_')
  switch (key) {
    case 'COMPLIANT':
      return 'COMPLIANT'
    case 'NON_COMPLIANT':
      return 'NON_COMPLIANT'
    case 'INCOMPLETE':
      return 'INCOMPLETE'
    case 'NOT_ASSESSED':
      return 'NOT_ASSESSED'
    default:
      return 'UNKNOWN'
  }
}

export interface SiteReading {
  month?: string
  /** Raw verdict as sent by the API — "COMPLIANT" | "NON-COMPLIANT" | "NON_COMPLIANT" | "INCOMPLETE" | … */
  compliance?: string
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

/** Visual tokens for a traffic-light value — derived from the canonical STATUS tokens. */
export const LIGHT_STYLE: Record<TrafficLight, { bg: string; color: string; dot: string; label: string }> = {
  green:  { bg: STATUS.compliant.bg,      color: STATUS.compliant.fg,      dot: STATUS.compliant.dot,      label: STATUS.compliant.label },
  yellow: { bg: STATUS.actionRequired.bg, color: STATUS.actionRequired.fg, dot: STATUS.actionRequired.dot, label: STATUS.actionRequired.label },
  red:    { bg: STATUS.critical.bg,       color: STATUS.critical.fg,       dot: STATUS.critical.dot,       label: STATUS.critical.label },
  blue:   { bg: STATUS.awaitingLab.bg,    color: STATUS.awaitingLab.fg,    dot: STATUS.awaitingLab.dot,    label: STATUS.awaitingLab.label },
  grey:   { bg: STATUS.notAssessed.bg,    color: STATUS.notAssessed.fg,    dot: STATUS.notAssessed.dot,    label: STATUS.notAssessed.label },
}

/**
 * Reduce a single reading to a traffic-light value.
 *
 * Order matters and is deliberate:
 *   1. no reading at all           → blue  (awaiting the laboratory)
 *   2. an actual breach            → red   (an explicit NON_COMPLIANT verdict, a
 *                                          failing parameter, or alert level 3–4)
 *   3. no judgeable verdict        → grey  (INCOMPLETE / NOT_ASSESSED / UNKNOWN)
 *   4. alert level 2               → yellow
 *   5. otherwise                   → green (reached only on an explicit COMPLIANT)
 *
 * The breach test stays ahead of the unjudged test so that no reading which is
 * red today can turn grey: this change moves readings out of green only.
 */
export function lightForReading(reading: SiteReading | null | undefined): TrafficLight {
  if (!reading) return 'blue'
  const level = reading.alert_level ?? 1
  const verdict = normaliseVerdict(reading.compliance)
  const hasFailingParams = (reading.failing_params?.length ?? 0) > 0

  if (verdict === 'NON_COMPLIANT' || hasFailingParams || level >= 3) return 'red'
  if (verdict !== 'COMPLIANT') return 'grey'
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
  /** Sites whose latest reading carries no judgeable verdict. */
  grey: number
  /** Mean of known compliance_pct values (0–100), null when none reported. */
  avgCompliancePct: number | null
  /** Sites needing management attention (yellow + red). */
  needsAttention: number
}

export function rollup(statuses: SiteStatus[]): PortfolioKpis {
  const counts = { green: 0, yellow: 0, red: 0, blue: 0, grey: 0 }
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
