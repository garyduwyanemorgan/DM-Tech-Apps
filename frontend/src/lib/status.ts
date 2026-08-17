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
//   🟣 unavailable — the /api/status call itself failed (network error,
//              non-2xx, unreadable body). This is NOT the same as blue: blue
//              means the site legitimately has no readings yet; unavailable
//              means we don't know what the site's readings are because the
//              call to find out did not succeed. Conflating the two used to
//              make failed status calls look like quiet, compliant sites —
//              undercounting `needsAttention` and diluting `avgCompliancePct`
//              on exactly the rollups regulators and executives read.
//
// Derived from the shape returned by GET /api/status/{site}:
//   { readings: [{ month, compliance, compliance_pct, alert_level, alert_label,
//                  failing_params, ...paramValues }] }

import { STATUS } from './tokens'
import { lastRequestId, readRequestId } from './requestId'

export type TrafficLight = 'green' | 'yellow' | 'red' | 'blue' | 'grey' | 'unavailable'

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
  /**
   * Correlation id for this site's status lookup, when known. Populated on the
   * `unavailable` factory so a failed call can be traced to server-side logs;
   * `undefined` on every other path (nothing failed, nothing to trace).
   */
  requestId?: string | null
}

/** Visual tokens for a traffic-light value — derived from the canonical STATUS tokens. */
export const LIGHT_STYLE: Record<TrafficLight, { bg: string; color: string; dot: string; label: string }> = {
  green:       { bg: STATUS.compliant.bg,      color: STATUS.compliant.fg,      dot: STATUS.compliant.dot,      label: STATUS.compliant.label },
  yellow:      { bg: STATUS.actionRequired.bg, color: STATUS.actionRequired.fg, dot: STATUS.actionRequired.dot, label: STATUS.actionRequired.label },
  red:         { bg: STATUS.critical.bg,       color: STATUS.critical.fg,       dot: STATUS.critical.dot,       label: STATUS.critical.label },
  blue:        { bg: STATUS.awaitingLab.bg,    color: STATUS.awaitingLab.fg,    dot: STATUS.awaitingLab.dot,    label: STATUS.awaitingLab.label },
  grey:        { bg: STATUS.notAssessed.bg,    color: STATUS.notAssessed.fg,    dot: STATUS.notAssessed.dot,    label: STATUS.notAssessed.label },
  unavailable: { bg: STATUS.unavailable.bg,    color: STATUS.unavailable.fg,    dot: STATUS.unavailable.dot,    label: STATUS.unavailable.label },
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
 * Explicit factory for a site whose status lookup failed — a non-2xx response,
 * an unreadable body, or a thrown network error. Deliberately not routed
 * through `statusFromReadings(site, null)`: that path means "no readings
 * yet" (blue), which is a legitimate, known state. This means "we don't know
 * what this site's readings are", which must never be scored as compliant,
 * averaged into `avgCompliancePct`, or silently dropped from `needsAttention`
 * accounting. `requestId` carries the correlation id (see lib/requestId.ts)
 * so the failure can be traced server-side.
 */
export function statusUnavailable(site: string, requestId: string | null): SiteStatus {
  return {
    site,
    latest: null,
    light: 'unavailable',
    compliancePct: null,
    failingParams: [],
    alertLevel: null,
    requestId,
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
        const requestId = readRequestId(res)
        if (!res.ok) return statusUnavailable(site, requestId)
        const data = await res.json()
        return statusFromReadings(site, data.readings)
      } catch {
        return statusUnavailable(site, lastRequestId())
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
  /**
   * Sites whose status lookup failed outright (network error, non-2xx, bad
   * shape) — we don't have a reading to even call unjudgeable. Counted
   * separately from `blue`/`grey` on purpose: these are not compliant,
   * excluded from `avgCompliancePct`'s denominator (not scored 0 or 100), and
   * NOT folded into `needsAttention` (that is a compliance signal; this is an
   * infrastructure one) — but they must never be invisible, which is why this
   * field exists at all. A rollup with `unavailable > 0` covers fewer sites
   * than `total` suggests, and any consumer showing `avgCompliancePct` or
   * `needsAttention` must say so.
   */
  unavailable: number
  /** Mean of known compliance_pct values (0–100), null when none reported. */
  avgCompliancePct: number | null
  /** Sites that actually contributed a figure to `avgCompliancePct`.
   *  Quote THIS, not `total - unavailable`: a site awaiting lab results is
   *  reachable but contributes nothing, so the reachable count overstates
   *  the sample the average rests on. */
  compliancePctBasis: number
  /** Sites needing management attention (yellow + red). */
  needsAttention: number
}

export function rollup(statuses: SiteStatus[]): PortfolioKpis {
  const counts = { green: 0, yellow: 0, red: 0, blue: 0, grey: 0, unavailable: 0 }
  let pctSum = 0
  let pctCount = 0
  for (const s of statuses) {
    counts[s.light] += 1
    // Excluded from the denominator, not scored — an unavailable site has no
    // known compliance_pct to average in either direction.
    if (s.light !== 'unavailable' && typeof s.compliancePct === 'number') {
      pctSum += s.compliancePct
      pctCount += 1
    }
  }
  return {
    total: statuses.length,
    ...counts,
    avgCompliancePct: pctCount > 0 ? Math.round(pctSum / pctCount) : null,
    // How many sites actually contributed a number to that average. NOT
    // `total - unavailable`: a blue "awaiting lab" site is reachable but has no
    // compliance_pct, so quoting the reachable count overstates the sample the
    // figure rests on.
    compliancePctBasis: pctCount,
    needsAttention: counts.yellow + counts.red,
  }
}
