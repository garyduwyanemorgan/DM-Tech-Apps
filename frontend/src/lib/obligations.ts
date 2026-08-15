// Obligation registry — types and PRESENTATION ONLY.
//
// THE RULE THIS FILE EXISTS TO KEEP: nothing here decides whether a duty is
// late. `core/obligations.py:evaluate` does that, once, on the server, with
// `today` as a parameter so an audit can reproduce it. The API hands every row
// its `status`, `kind`, `reason`, `days_until_due` and `needs_attention`; this
// module turns those into a colour, a word and a sort order and does nothing
// else. There is no comparison against a limit or a date anywhere in this file,
// and there must never be one — `frontend/VERDICT_DIVERGENCE.md` documents what
// happens when the same verdict is implemented twice, and this repo is already
// at eight implementations (three of them in this frontend).
//
// The second rule, inherited from the endpoint: `needs_attention` is NOT
// overdue, is not folded into it, and is rendered separately everywhere.
// "You are late" and "we cannot tell whether you are late" are different
// sentences with different remedies.
//
// The third, inherited from lib/status.ts: green is reachable only on an
// explicit `compliant`. Anything unrecognised — including an absent status —
// renders slate and says so. A missing status must never look clean.

import type { BadgeTone } from '../components/ui/StatusBadge'

/** The four statuses `core/obligations.py` can return (023's status CHECK). */
export type ObligationStatusKey = 'compliant' | 'due_soon' | 'overdue' | 'suspended'

/** The three cadence kinds 023's obligations_cadence_check makes exclusive. */
export type ObligationKindKey = 'periodic' | 'event_triggered' | 'self_declared_review'

/** One row of GET /api/obligations. Verdict fields are marked; they are read,
 *  never recomputed. `status` and `kind` are typed as plain strings on purpose —
 *  an unrecognised value from a future server must be renderable, not a crash. */
export interface Obligation {
  id: string
  site_id: string | null
  /** Joined server-side from `sites`; null on an organisation-wide duty. */
  site_name: string | null
  entitlement_id: string | null
  label: string
  obligation_type: string | null
  notes: string | null
  next_due_on: string | null
  grace_days: number | null
  cadence_months: number | null
  cadence_days: number | null
  trigger_event: string | null
  self_declared_review: boolean | null
  last_satisfied_at: string | null
  /** No display name is returned with this — see the note in Obligations.tsx. */
  responsible_user_id: string | null

  // ── Computed by core.obligations.evaluate. Rendered verbatim. ──
  status: string
  /** The `status` COLUMN. Differs from `status` only when the ageing sweep is
   *  stale, which is a finding worth surfacing rather than hiding. */
  stored_status: string | null
  kind: string
  reason: string
  days_until_due: number | null
  needs_attention: boolean
}

/** The block `core.obligations.summarise` returns. */
export interface ObligationCounts {
  compliant: number
  due_soon: number
  overdue: number
  suspended: number
  /** Counted SEPARATELY and never inside `overdue`. */
  needs_attention: number
  total: number
}

export interface SiteCounts extends ObligationCounts {
  site_id: string | null
  /** "Organisation-wide" for site-less duties — labelled by the API, not dropped. */
  site_name: string | null
}

export interface ObligationsResponse {
  as_of: string
  site_id: string | null
  obligations: Obligation[]
  summary: ObligationCounts
}

export interface ObligationsSummaryResponse {
  as_of: string
  by_site: SiteCounts[]
  totals: ObligationCounts
}

export interface StatusPresentation {
  tone: BadgeTone
  label: string
  /** Section order: overdue first, and an unrecognised status is never filed
   *  below `compliant` where it would read as a quiet pass. */
  order: number
  /** Plain-language gloss shown once per section, not per row. */
  blurb: string
}

/**
 * A colour and a word for a status the server already decided.
 *
 * Written as an exhaustive switch with an explicit default rather than a lookup
 * table, so an unknown status cannot land on a green entry by accident and
 * cannot throw. `green` is returned for exactly one input.
 */
export function presentStatus(status: string | null | undefined): StatusPresentation {
  switch (status) {
    case 'overdue':
      return {
        tone: 'red', label: 'Overdue', order: 0,
        blurb: 'Past the due date (and any grace period). Evidence is owed now.',
      }
    case 'due_soon':
      return {
        tone: 'amber', label: 'Due soon', order: 1,
        blurb: 'Inside the warning window, or inside the grace period after the due date.',
      }
    case 'suspended':
      return {
        tone: 'slate', label: 'Suspended', order: 3,
        blurb: 'The entitlement is inactive, so this is not monitored. Deliberately not '
          + '"compliant": a commercial decision is not a clean compliance record. History is retained.',
      }
    case 'compliant':
      return {
        tone: 'green', label: 'Compliant', order: 4,
        blurb: 'Scheduled and not yet inside the warning window, or awaiting its trigger.',
      }
    default:
      return {
        tone: 'slate',
        label: status ? `Unrecognised status: ${status}` : 'No status returned',
        order: 2,
        blurb: 'The server returned a status this build does not recognise. It is shown '
          + 'as unjudged — never as a pass — until the vocabulary is reconciled.',
      }
  }
}

export interface KindPresentation {
  label: string
  description: string
}

/** How the duty comes due. Wording only — the server chose the kind. */
export function presentKind(kind: string | null | undefined): KindPresentation {
  switch (kind) {
    case 'periodic':
      return { label: 'Periodic', description: 'Falls due again on a fixed cadence.' }
    case 'event_triggered':
      return { label: 'Event-triggered', description: 'Becomes due when a named event occurs.' }
    case 'self_declared_review':
      return {
        label: 'Self-declared review',
        description: 'The guideline states the duty but no frequency.',
      }
    default:
      return { label: kind || 'Unknown', description: 'Cadence kind not recognised by this build.' }
  }
}

export interface AttentionPresentation {
  /** Short badge text. Never the word "overdue". */
  label: string
  /** What the user has to DO about it. */
  remedy: string
}

/**
 * The separate "we cannot tell" signal.
 *
 * Returns null when the row does not carry it — the flag comes from the server,
 * this only chooses the wording, keyed off the server's `kind`. A duty whose
 * guideline states no frequency is an unanswered question, not a breach, and
 * the remedy is a conversation, so the remedy is what is shown.
 */
export function presentAttention(obligation: Obligation): AttentionPresentation | null {
  if (!obligation.needs_attention) return null
  switch (obligation.kind) {
    case 'self_declared_review':
      return {
        label: 'Cadence to agree',
        remedy: 'The guideline sets no frequency for this duty, so it cannot be aged. '
          + 'This is not a breach. Agree a cadence with the client and record it, and '
          + 'this duty starts being tracked.',
      }
    case 'periodic':
      return {
        label: 'Never scheduled',
        remedy: 'This duty has a cadence but no due date has ever been set, so its ageing '
          + 'cannot be trusted. Give it a first due date.',
      }
    default:
      return { label: 'Needs attention', remedy: obligation.reason }
  }
}

/** `days_until_due` as words. Formatting of a number the server computed. */
export function formatDaysUntilDue(days: number | null | undefined): string {
  if (days === null || days === undefined) return 'No due date'
  if (days === 0) return 'Due today'
  if (days < 0) return `${Math.abs(days)} day${Math.abs(days) === 1 ? '' : 's'} late`
  return `in ${days} day${days === 1 ? '' : 's'}`
}

/** Colour for the days-until-due cell — taken from the status the server gave,
 *  never from the sign of the number, so the two can never disagree. */
export function daysTone(obligation: Obligation): BadgeTone {
  return presentStatus(obligation.status).tone
}

/**
 * Sort inside a section: soonest first, unscheduled last.
 *
 * Ordering by a number the server supplied. It decides nothing — every row in a
 * section already carries the same server-issued status.
 */
export function byUrgency(a: Obligation, b: Obligation): number {
  const av = a.days_until_due
  const bv = b.days_until_due
  if (av === null || av === undefined) return bv === null || bv === undefined ? 0 : 1
  if (bv === null || bv === undefined) return -1
  return av - bv
}

/** Group rows into sections in `presentStatus.order`, ready to render. */
export function groupByStatus(
  obligations: Obligation[],
): { status: string; presentation: StatusPresentation; rows: Obligation[] }[] {
  const buckets = new Map<string, Obligation[]>()
  for (const o of obligations) {
    const key = o.status ?? ''
    const bucket = buckets.get(key)
    if (bucket) bucket.push(o)
    else buckets.set(key, [o])
  }
  return [...buckets.entries()]
    .map(([status, rows]) => ({
      status,
      presentation: presentStatus(status),
      rows: [...rows].sort(byUrgency),
    }))
    .sort((a, b) => a.presentation.order - b.presentation.order)
}

// ── Module catalogue (GET /api/modules) ──────────────────────────────────────

export interface GuidelineModule {
  id: string
  key: string | null
  label: string | null
  category: string | null
  standard_id: string | null
  /** §7.12 — what a report may CLAIM for this module. Only 'compliance' may
   *  produce a verdict at all. */
  module_kind: string | null
  obligation_type: string | null
  status: string | null
  provenance: string | null
  notes: string | null
  entitled: boolean
  entitlement_id: string | null
  active_from: string | null
  active_until: string | null
  /** 023 refuses status='available' unless provenance='verified'. */
  sellable: boolean
  /** Why not, in words, straight from the server. Null when it is sellable. */
  not_sellable_reason: string | null
  /** Present only for roles holding billing.read. */
  list_price_monthly?: number | null
  currency?: string | null
}

export interface ModulesResponse {
  modules: GuidelineModule[]
  entitled_count: number
  sellable_count: number
}

/** What ticking WOULD create — `core.entitlements.plan_summary`, verbatim. */
export interface EntitlementPlan {
  module: { id: string; key: string | null; label: string | null; module_kind: string | null }
  sites: number
  obligations: {
    total: number
    by_kind: Record<string, number>
    needs_cadence_agreed: number
    due_immediately: number
    awaiting_trigger: number
  }
  warning: string
}

export interface EntitlementPlanResponse {
  created: boolean
  plan: EntitlementPlan
  message?: string
  entitlement?: { id: string; active_from: string; active_until: string | null }
  obligations_created?: number
}

/** One duty that stops being tracked when a module is un-ticked (§7.5). */
export interface NoLongerMonitored {
  id: string
  label: string | null
  site_id: string | null
  next_due_on: string | null
}

export interface DeactivateResponse {
  deactivated: boolean
  obligations_suspended: number
  obligations_deleted: number
  no_longer_monitored: NoLongerMonitored[]
  message: string
}

export interface ModuleKindPresentation {
  label: string
  tone: BadgeTone
  description: string
}

/** §7.12 module kind — what the module is allowed to claim. */
export function presentModuleKind(kind: string | null | undefined): ModuleKindPresentation {
  switch (kind) {
    case 'compliance':
      return {
        label: 'Compliance', tone: 'green',
        description: 'Sets testable limits, so a report may state a compliance verdict.',
      }
    case 'procedural':
      return {
        label: 'Procedural', tone: 'blue',
        description: 'States duties and practice, not limits. A report may evidence the duty '
          + 'was done — it may not claim a compliance verdict.',
      }
    case 'advisory':
      return {
        label: 'Advisory', tone: 'blue',
        description: 'Guidance only. Sellable, but not the same product as a compliance module.',
      }
    case 'unusable':
      return {
        label: 'Unusable', tone: 'red',
        description: 'The guideline contradicts itself — there is nothing a report could '
          + 'truthfully say against it.',
      }
    default:
      return {
        label: kind || 'Unknown', tone: 'slate',
        description: 'Module kind not recognised by this build.',
      }
  }
}

/** Catalogue lifecycle status. Not a compliance verdict — never green here
 *  except for a module actually on sale. */
export function presentModuleStatus(status: string | null | undefined): { label: string; tone: BadgeTone } {
  switch (status) {
    case 'available': return { label: 'Available', tone: 'green' }
    case 'coming_soon': return { label: 'Coming soon', tone: 'blue' }
    case 'retired': return { label: 'Retired', tone: 'slate' }
    default: return { label: status || 'Unknown', tone: 'slate' }
  }
}

/** Provenance of the module's content against the published DM document. */
export function presentProvenance(provenance: string | null | undefined): { label: string; tone: BadgeTone } {
  switch (provenance) {
    case 'verified': return { label: 'Verified', tone: 'green' }
    case 'unverified': return { label: 'Unverified', tone: 'amber' }
    case 'extracted': return { label: 'Extracted, unread', tone: 'amber' }
    default: return { label: provenance || 'Unknown', tone: 'slate' }
  }
}
