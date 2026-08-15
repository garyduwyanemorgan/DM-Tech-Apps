// The Obligation Registry (§4.3, promised by Phase 1 §6).
//
// What is due, what is due soon, what is overdue — and, kept firmly apart from
// all three, what cannot be aged at all. The product's whole claim is that it
// notices the test that never happened, so this screen must never make an
// absence look like a pass.
//
// NO VERDICT IS COMPUTED HERE. Every row arrives from GET /api/obligations with
// its `status`, `kind`, `reason`, `days_until_due` and `needs_attention` already
// decided by core.obligations.evaluate. This file chooses words, colours and an
// order; lib/obligations.ts holds those choices. If you are about to compare a
// date to today in this file, stop and read frontend/VERDICT_DIVERGENCE.md.
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { PageHeader } from './PageHeader'
import { COLORS, tableHeaderStyle, tableCellStyle, inputStyle, labelStyle } from '../lib/ui'
import { COLORS as TOKENS } from '../lib/tokens'
import { AlertCard, StatusBadge, Button } from './ui'
import { RefreshCw } from 'lucide-react'
import {
  formatDaysUntilDue, groupByStatus, presentAttention, presentKind, presentStatus,
  type Obligation, type ObligationCounts, type ObligationsResponse,
  type ObligationsSummaryResponse, type SiteCounts,
} from '../lib/obligations'

const ALL_SITES = '__all__'
/** Site-less duties (a competency, an org-wide policy review). The API labels
 *  them "Organisation-wide" rather than dropping them, and so does this filter —
 *  they have no site_id to send, so this option narrows client-side. */
const ORG_WIDE = '__org__'

interface Props {
  /** Site NAME from the sidebar. Used only to preselect the filter; the filter
   *  itself works on site_id, which is what the API validates against scope. */
  activeSite?: string
}

const countCellStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 2, minWidth: 78,
}

const CountCell: React.FC<{ label: string; value: number; color: string }> = ({ label, value, color }) => (
  <div style={countCellStyle}>
    <span style={{ fontSize: '1.35rem', fontWeight: 800, color, lineHeight: 1.1 }}>{value}</span>
    <span style={{ fontSize: '0.68rem', fontWeight: 700, color: COLORS.slate, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
      {label}
    </span>
  </div>
)

/**
 * One site's counts.
 *
 * The four statuses sit together; `needs_attention` sits on the other side of a
 * divider with its own explanation. That separation is the point of the card —
 * summarise() counts it separately precisely so a configuration gap cannot hide
 * inside a lateness figure, and a layout that lined all five up as peers would
 * undo that on screen.
 */
const SummaryCard: React.FC<{ title: string; counts: ObligationCounts; emphasis?: boolean }> = ({
  title, counts, emphasis,
}) => (
  <div
    className="glass-card"
    style={{
      padding: '1rem 1.15rem', display: 'flex', flexDirection: 'column', gap: '0.75rem',
      borderLeft: `5px solid ${counts.overdue > 0 ? TOKENS.critical : emphasis ? TOKENS.navy : TOKENS.border}`,
    }}
  >
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '0.5rem' }}>
      <span style={{ fontWeight: 700, color: TOKENS.ink, fontSize: '0.98rem' }}>{title}</span>
      <span style={{ fontSize: '0.72rem', color: COLORS.slate }}>{counts.total} duties</span>
    </div>

    <div style={{ display: 'flex', gap: '1.1rem', flexWrap: 'wrap' }}>
      <CountCell label="Overdue" value={counts.overdue} color={counts.overdue > 0 ? '#9C0006' : COLORS.slate} />
      <CountCell label="Due soon" value={counts.due_soon} color={counts.due_soon > 0 ? '#856404' : COLORS.slate} />
      <CountCell label="Compliant" value={counts.compliant} color={counts.compliant > 0 ? '#006100' : COLORS.slate} />
      <CountCell label="Suspended" value={counts.suspended} color={COLORS.slate} />
    </div>

    {/* Deliberately below a rule, deliberately not a fifth status pill. */}
    <div style={{ borderTop: `1px dashed ${TOKENS.border}`, paddingTop: '0.6rem' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
        <span style={{ fontSize: '1.1rem', fontWeight: 800, color: counts.needs_attention > 0 ? '#1E40AF' : COLORS.slate }}>
          {counts.needs_attention}
        </span>
        <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#1E40AF', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Need attention
        </span>
      </div>
      <div style={{ fontSize: '0.72rem', color: COLORS.slate, marginTop: 2, lineHeight: 1.45 }}>
        {counts.needs_attention > 0
          ? 'Not late — unanswerable. These duties cannot be aged until a cadence or a first due date is agreed. Counted separately from Overdue on purpose.'
          : 'Every duty here can be aged.'}
      </div>
    </div>
  </div>
)

export const Obligations: React.FC<Props> = ({ activeSite }) => {
  const { organizationId, token } = useAuth()

  const [rows, setRows] = useState<Obligation[]>([])
  const [summary, setSummary] = useState<ObligationCounts | null>(null)
  const [bySite, setBySite] = useState<SiteCounts[]>([])
  const [totals, setTotals] = useState<ObligationCounts | null>(null)
  const [asOf, setAsOf] = useState<string>('')
  // null = the user has not chosen yet, so the sidebar's active site is used.
  // Derived rather than written back by an effect: an effect that copies props
  // into state re-renders twice and gets out of step the moment the sidebar
  // changes site.
  const [chosenSite, setChosenSite] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The filter actually in force: the user's choice if they made one, otherwise
  // the sidebar's active site once its id is known from the summary.
  const siteFilter = useMemo(() => {
    if (chosenSite) return chosenSite
    if (!activeSite) return ALL_SITES
    return bySite.find(s => s.site_name === activeSite && s.site_id)?.site_id ?? ALL_SITES
  }, [chosenSite, activeSite, bySite])

  const makeHeaders = useCallback((): HeadersInit => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [token, organizationId])

  /** Per-site counts for the strip, and the site options for the filter. */
  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch('/api/obligations/summary', { headers: makeHeaders() })
      const data: ObligationsSummaryResponse & { detail?: string } = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to load the obligation summary.'); return }
      setBySite(data.by_site || [])
      setTotals(data.totals || null)
    } catch {
      setError('Network error loading the obligation summary.')
    }
  }, [makeHeaders])

  const fetchRegistry = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      // A real site is filtered by the API, which validates the id against the
      // caller's organisation and site scope. ALL and ORG_WIDE have no id to
      // send, so they are narrowed below from the full result.
      const query = siteFilter !== ALL_SITES && siteFilter !== ORG_WIDE
        ? `?site_id=${encodeURIComponent(siteFilter)}`
        : ''
      const res = await fetch(`/api/obligations${query}`, { headers: makeHeaders() })
      const data: ObligationsResponse & { detail?: string } = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to load the obligation registry.'); return }
      setRows(data.obligations || [])
      setSummary(data.summary || null)
      setAsOf(data.as_of || '')
    } catch {
      setError('Network error loading the obligation registry.')
    } finally {
      setLoading(false)
    }
  }, [makeHeaders, siteFilter])

  useEffect(() => { fetchSummary() }, [fetchSummary])
  useEffect(() => { fetchRegistry() }, [fetchRegistry])

  const visible = useMemo(
    () => (siteFilter === ORG_WIDE ? rows.filter(r => !r.site_id) : rows),
    [rows, siteFilter],
  )
  const sections = useMemo(() => groupByStatus(visible), [visible])

  // Which counts head the page. The API's own summary is used unchanged for a
  // server-side filter; the org-wide narrowing happens client-side, so its
  // strip falls back to the per-site card the API already computed.
  const scopeCounts: ObligationCounts | null = siteFilter === ORG_WIDE
    ? bySite.find(s => !s.site_id) ?? null
    : summary
  const scopeLabel = siteFilter === ALL_SITES
    ? 'All sites'
    : siteFilter === ORG_WIDE
      ? 'Organisation-wide duties'
      : bySite.find(s => s.site_id === siteFilter)?.site_name || 'Selected site'

  const attentionRows = visible.filter(r => r.needs_attention)

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader
        title="Obligation Registry"
        subtitle="What each site owes, when it is owed, and what cannot yet be judged"
        icon="📌"
      />

      {error && (
        <div style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #fecaca' }}>
          {error}
        </div>
      )}

      {/* Controls */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1rem', flexWrap: 'wrap', marginBottom: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
          <label style={labelStyle} htmlFor="obligation-site-filter">Site</label>
          <select
            id="obligation-site-filter"
            value={siteFilter}
            onChange={e => setChosenSite(e.target.value)}
            style={{ ...inputStyle, minWidth: 260 }}
          >
            <option value={ALL_SITES}>All sites</option>
            {bySite.filter(s => s.site_id).map(s => (
              <option key={s.site_id} value={s.site_id as string}>
                {s.site_name || s.site_id}
                {s.overdue > 0 ? ` — ${s.overdue} overdue` : ''}
              </option>
            ))}
            {bySite.some(s => !s.site_id) && (
              <option value={ORG_WIDE}>Organisation-wide duties</option>
            )}
          </select>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => { fetchSummary(); fetchRegistry() }}
          disabled={loading}
        >
          <RefreshCw size={14} /> {loading ? 'Loading…' : 'Refresh'}
        </Button>
        {asOf && (
          <span style={{ fontSize: '0.75rem', color: COLORS.slate, paddingBottom: 6 }}>
            Aged as at <strong>{asOf}</strong> by the server, not by this browser.
          </span>
        )}
      </div>

      {/* Headline banners — overdue and needs-attention are two separate messages. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginBottom: 16 }}>
        {(scopeCounts?.overdue ?? 0) > 0 && (
          <AlertCard
            tier="critical"
            title={`${scopeCounts?.overdue} obligation(s) overdue — ${scopeLabel}`}
            description="Past the due date and any grace period. Evidence is owed now."
          />
        )}
        {(scopeCounts?.needs_attention ?? 0) > 0 && (
          <AlertCard
            tier="awaiting"
            title={`${scopeCounts?.needs_attention} obligation(s) cannot be aged — ${scopeLabel}`}
            description={
              'This is not lateness. These duties either state no frequency in the guideline '
              + 'or have never been given a first due date, so nobody can say whether they are '
              + 'late. Agree a cadence with the client, or set a first due date, and they start '
              + 'being tracked. They are counted apart from Overdue everywhere on this page.'
            }
          />
        )}
        {!loading && scopeCounts && scopeCounts.total === 0 && (
          <AlertCard
            tier="awaiting"
            title="No obligations recorded for this scope"
            description={
              'An empty registry is the honest answer to "nothing is recorded". It is not '
              + 'evidence of compliance. Duties appear here once a guideline module is ticked '
              + 'in the Module Catalogue.'
            }
          />
        )}
      </div>

      {/* Per-site summary strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(310px, 1fr))', gap: '0.85rem', marginBottom: 20 }}>
        {siteFilter === ALL_SITES && totals && (
          <SummaryCard title="All sites — total" counts={totals} emphasis />
        )}
        {(siteFilter === ALL_SITES
          ? bySite
          : bySite.filter(s => (siteFilter === ORG_WIDE ? !s.site_id : s.site_id === siteFilter))
        ).map(s => (
          <SummaryCard
            key={s.site_id || 'org-wide'}
            title={s.site_name || 'Organisation-wide'}
            counts={s}
          />
        ))}
      </div>

      {/* Needs-attention list, on its own, before the status sections. It is not
          a status, so it does not get a section down there. */}
      {attentionRows.length > 0 && (
        <div
          className="glass-card"
          style={{ padding: '1rem 1.15rem', marginBottom: 20, borderLeft: `5px solid ${TOKENS.awaiting}` }}
        >
          <div style={{ fontWeight: 700, color: TOKENS.ink, marginBottom: 4 }}>
            Unanswered questions ({attentionRows.length})
          </div>
          <div style={{ fontSize: '0.8rem', color: COLORS.slate, marginBottom: '0.75rem', lineHeight: 1.5 }}>
            Duties whose ageing cannot be trusted. Each one names what has to happen before it
            can be tracked. None of these is a breach, and none is counted as overdue.
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {attentionRows.map(o => {
              const attention = presentAttention(o)
              return (
                <div key={o.id} style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
                  <StatusBadge tone="blue" variant="count" style={{ flexShrink: 0, marginTop: 2 }}>
                    {attention?.label ?? 'Needs attention'}
                  </StatusBadge>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '0.86rem', fontWeight: 600, color: TOKENS.ink }}>
                      {o.label}
                      <span style={{ fontWeight: 400, color: COLORS.slate }}>
                        {' '}— {o.site_name || 'Organisation-wide'}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.78rem', color: COLORS.slate, lineHeight: 1.45 }}>
                      {attention?.remedy}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* The registry itself, grouped by the status the server issued. Overdue
          is the first section by construction (presentStatus.order). */}
      {sections.map(section => (
        <div key={section.status || 'unknown'} style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.4rem', flexWrap: 'wrap' }}>
            <StatusBadge tone={section.presentation.tone}>{section.presentation.label}</StatusBadge>
            <span style={{ fontWeight: 700, color: TOKENS.ink }}>{section.rows.length}</span>
            <span style={{ fontSize: '0.78rem', color: COLORS.slate }}>{section.presentation.blurb}</span>
          </div>

          <div className="glass-card" style={{ padding: 0, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
              <thead>
                <tr>
                  <th style={tableHeaderStyle}>Duty</th>
                  <th style={tableHeaderStyle}>Site</th>
                  <th style={tableHeaderStyle}>Type</th>
                  <th style={tableHeaderStyle}>Kind</th>
                  <th style={tableHeaderStyle}>Status</th>
                  <th style={tableHeaderStyle}>Due</th>
                  <th style={tableHeaderStyle}>Why</th>
                  <th style={tableHeaderStyle}>Responsible</th>
                </tr>
              </thead>
              <tbody>
                {section.rows.map(o => {
                  const status = presentStatus(o.status)
                  const kind = presentKind(o.kind)
                  const attention = presentAttention(o)
                  // A disagreement between the computed verdict and the stored
                  // column means the ageing sweep has not run. Surfaced, not hidden.
                  const stale = o.stored_status && o.stored_status !== o.status
                  return (
                    <tr key={o.id}>
                      <td style={{ ...tableCellStyle, fontWeight: 600, color: TOKENS.ink }}>
                        {o.label}
                        {o.notes && (
                          <div style={{ fontWeight: 400, fontSize: '0.76rem', color: COLORS.slate, marginTop: 2 }}>
                            {o.notes}
                          </div>
                        )}
                      </td>
                      <td style={tableCellStyle}>
                        {o.site_name || <span style={{ color: COLORS.slate }}>Organisation-wide</span>}
                      </td>
                      <td style={tableCellStyle}>{o.obligation_type || '—'}</td>
                      <td style={tableCellStyle} title={kind.description}>{kind.label}</td>
                      <td style={tableCellStyle}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-start' }}>
                          <StatusBadge tone={status.tone} variant="count">{status.label}</StatusBadge>
                          {attention && (
                            // Distinct badge, distinct colour, distinct sentence.
                            // "We cannot tell" is never dressed as "you are late".
                            <StatusBadge tone="blue" variant="count" style={{ maxWidth: 220 }}>
                              {attention.label}
                            </StatusBadge>
                          )}
                          {stale && (
                            <span style={{ fontSize: '0.68rem', color: COLORS.slate }}>
                              registry column still says “{o.stored_status}” — the ageing sweep is behind
                            </span>
                          )}
                        </div>
                      </td>
                      <td style={tableCellStyle}>
                        <div style={{ fontWeight: 600 }}>{formatDaysUntilDue(o.days_until_due)}</div>
                        <div style={{ fontSize: '0.74rem', color: COLORS.slate }}>
                          {o.next_due_on ? `next due ${o.next_due_on}` : 'no due date set'}
                        </div>
                      </td>
                      <td style={{ ...tableCellStyle, maxWidth: 320, color: COLORS.slate, fontSize: '0.8rem' }}>
                        {/* The server's own sentence, verbatim. */}
                        {o.reason}
                        {attention && (
                          <div style={{ color: '#1E40AF', marginTop: 3 }}>{attention.remedy}</div>
                        )}
                      </td>
                      <td style={tableCellStyle}>
                        {/* The API returns responsible_user_id only — there is no
                            name on this payload, so an id is all that can honestly
                            be shown. Inventing "Unassigned" for a set id would be
                            worse than a truncated uuid. */}
                        {o.responsible_user_id
                          ? <span title={o.responsible_user_id}>User {o.responsible_user_id.slice(0, 8)}…</span>
                          : <span style={{ color: COLORS.slate }}>Nobody assigned</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}
