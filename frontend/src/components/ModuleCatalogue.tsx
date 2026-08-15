// The Module Catalogue (§4.5, promised by Phase 1 §6).
//
// Every DM guideline module: what kind it is, whether it is on sale, where its
// content came from, and whether this organisation is entitled to it — with the
// tick and un-tick actions.
//
// Three things this screen refuses to do quietly:
//
//   1. TICK WITHOUT SHOWING THE PLAN. POST /api/entitlements with confirm:false
//      writes nothing and returns what ticking WOULD create. Ticking one module
//      instantiates one duty per (template, site), so a contractor with eleven
//      sites can acquire forty immediately-overdue duties in one click. That is
//      the correct outcome and an alarming one to meet by surprise, so the plan
//      is shown and a second, explicit confirmation is required.
//
//   2. UN-TICK WITHOUT NAMING WHAT GOES DARK. §7.5. The DELETE response returns
//      `no_longer_monitored[]`; a count alone does not tell a client WHICH duty
//      stopped being tracked. The names are shown before (read from the
//      registry) and after (from the server's own list).
//
//   3. DRESS A REFUSAL AS A FAILURE. Every module currently loaded is
//      coming_soon/unverified, so 023 legitimately refuses to sell any of them
//      and the API answers 409. That is information — the module is real, nobody
//      has yet read the published DM document against it — and it is rendered as
//      such. So is a 403: entitlements.manage is Executive Management only.
//
// No verdict is computed here either. Statuses on this page are catalogue
// lifecycle states, not compliance verdicts, and the plan's counts come from
// core.entitlements.plan_summary, which ages every provisional row through
// core.obligations.evaluate on the server.
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { hasPermission } from '../lib/permissions'
import { PageHeader } from './PageHeader'
import { COLORS, tableHeaderStyle, tableCellStyle, inputStyle, labelStyle, fieldStyle } from '../lib/ui'
import { COLORS as TOKENS } from '../lib/tokens'
import { AlertCard, Button, StatusBadge } from './ui'
import { Info, Lock, RefreshCw } from 'lucide-react'
import {
  presentModuleKind, presentModuleStatus, presentProvenance,
  type DeactivateResponse, type EntitlementPlan, type EntitlementPlanResponse,
  type GuidelineModule, type ModulesResponse, type NoLongerMonitored,
  type Obligation, type ObligationsResponse,
} from '../lib/obligations'

const today = () => new Date().toISOString().slice(0, 10)

const Modal: React.FC<{ title: string; onClose: () => void; children: React.ReactNode }> = ({
  title, onClose, children,
}) => (
  <div
    role="dialog" aria-modal="true" aria-label={title}
    onClick={onClose}
    style={{
      position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem',
    }}
  >
    <div
      onClick={e => e.stopPropagation()}
      style={{
        background: '#fff', borderRadius: 10, padding: '1.5rem', maxWidth: 640, width: '100%',
        maxHeight: '85vh', overflowY: 'auto', boxShadow: '0 20px 50px rgba(15,23,42,0.28)',
      }}
    >
      <h3 className="section-heading" style={{ marginTop: 0 }}>{title}</h3>
      {children}
    </div>
  </div>
)

/** The plan, rendered so the two counts that matter cannot be skimmed past:
 *  how many duties are due the moment this is ticked, and how many need a
 *  cadence agreed with the client before they can be tracked at all. */
const PlanPanel: React.FC<{ plan: EntitlementPlan }> = ({ plan }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
    <AlertCard
      tier={plan.obligations.due_immediately > 0 ? 'actionRequired' : 'awaiting'}
      title={`${plan.obligations.total} obligation(s) would be created across ${plan.sites} site(s)`}
      description={plan.warning}
    />
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.6rem' }}>
      <div className="glass-card" style={{ padding: '0.8rem 0.9rem' }}>
        <div style={{ fontSize: '1.5rem', fontWeight: 800, color: plan.obligations.due_immediately > 0 ? '#9C0006' : COLORS.slate }}>
          {plan.obligations.due_immediately}
        </div>
        <div style={{ fontSize: '0.7rem', fontWeight: 700, color: COLORS.slate, textTransform: 'uppercase' }}>
          Due or overdue immediately
        </div>
        <div style={{ fontSize: '0.72rem', color: COLORS.slate, marginTop: 4, lineHeight: 1.45 }}>
          No evidence exists for these yet, so they are outstanding from the moment the module is ticked.
        </div>
      </div>
      <div className="glass-card" style={{ padding: '0.8rem 0.9rem' }}>
        <div style={{ fontSize: '1.5rem', fontWeight: 800, color: plan.obligations.needs_cadence_agreed > 0 ? '#1E40AF' : COLORS.slate }}>
          {plan.obligations.needs_cadence_agreed}
        </div>
        <div style={{ fontSize: '0.7rem', fontWeight: 700, color: '#1E40AF', textTransform: 'uppercase' }}>
          Need a cadence agreed
        </div>
        <div style={{ fontSize: '0.72rem', color: COLORS.slate, marginTop: 4, lineHeight: 1.45 }}>
          The guideline states these duties but no frequency. Not breaches — conversations somebody
          has to have with the client before they can be tracked.
        </div>
      </div>
      <div className="glass-card" style={{ padding: '0.8rem 0.9rem' }}>
        <div style={{ fontSize: '1.5rem', fontWeight: 800, color: COLORS.slate }}>
          {plan.obligations.awaiting_trigger}
        </div>
        <div style={{ fontSize: '0.7rem', fontWeight: 700, color: COLORS.slate, textTransform: 'uppercase' }}>
          Awaiting a trigger
        </div>
        <div style={{ fontSize: '0.72rem', color: COLORS.slate, marginTop: 4, lineHeight: 1.45 }}>
          Become due when a named event occurs — nothing is owed until then.
        </div>
      </div>
    </div>
    {Object.keys(plan.obligations.by_kind).length > 0 && (
      <div style={{ fontSize: '0.78rem', color: COLORS.slate }}>
        By kind:{' '}
        {Object.entries(plan.obligations.by_kind)
          .map(([kind, n]) => `${presentModuleKindSafeLabel(kind)} ${n}`)
          .join(' · ')}
      </div>
    )}
  </div>
)

/** Cadence kinds share wording with the registry; kept local and total so an
 *  unrecognised key from the server prints itself rather than blanking. */
function presentModuleKindSafeLabel(kind: string): string {
  switch (kind) {
    case 'periodic': return 'periodic'
    case 'event_triggered': return 'event-triggered'
    case 'self_declared_review': return 'self-declared review'
    default: return kind
  }
}

export const ModuleCatalogue: React.FC = () => {
  const { organizationId, token, role } = useAuth()
  const canManage = hasPermission(role, 'entitlements.manage')

  const [modules, setModules] = useState<GuidelineModule[]>([])
  const [entitledCount, setEntitledCount] = useState(0)
  const [sellableCount, setSellableCount] = useState(0)
  const [registry, setRegistry] = useState<Obligation[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // Tick flow
  const [tickTarget, setTickTarget] = useState<GuidelineModule | null>(null)
  const [activeFrom, setActiveFrom] = useState(today())
  const [firstDueOn, setFirstDueOn] = useState('')
  const [tickNotes, setTickNotes] = useState('')
  const [plan, setPlan] = useState<EntitlementPlan | null>(null)
  const [busy, setBusy] = useState(false)
  /** A refusal (409) or a permission answer (403) — not an error. */
  const [refusal, setRefusal] = useState<{ kind: 'unavailable' | 'forbidden' | 'conflict'; detail: string } | null>(null)
  const [tickError, setTickError] = useState<string | null>(null)

  // Un-tick flow
  const [untickTarget, setUntickTarget] = useState<GuidelineModule | null>(null)
  const [wentDark, setWentDark] = useState<{ module: string; rows: NoLongerMonitored[]; message: string } | null>(null)

  const makeHeaders = useCallback((): HeadersInit => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [token, organizationId])

  const fetchModules = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await fetch('/api/modules', { headers: makeHeaders() })
      const data: ModulesResponse & { detail?: string } = await res.json()
      if (!res.ok) { setError(data.detail || 'Failed to load the module catalogue.'); return }
      setModules(data.modules || [])
      setEntitledCount(data.entitled_count ?? 0)
      setSellableCount(data.sellable_count ?? 0)
    } catch {
      setError('Network error loading the module catalogue.')
    } finally {
      setLoading(false)
    }
  }, [makeHeaders])

  /** The registry is read only so un-ticking can NAME the duties that would stop
   *  being monitored before the client commits, rather than after. */
  const fetchRegistry = useCallback(async () => {
    try {
      const res = await fetch('/api/obligations', { headers: makeHeaders() })
      const data: ObligationsResponse = await res.json()
      if (res.ok) setRegistry(data.obligations || [])
    } catch { /* the un-tick modal falls back to the server's after-the-fact list */ }
  }, [makeHeaders])

  useEffect(() => { fetchModules() }, [fetchModules])
  useEffect(() => { fetchRegistry() }, [fetchRegistry])

  const closeTick = () => {
    setTickTarget(null); setPlan(null); setRefusal(null); setTickError(null)
    setFirstDueOn(''); setTickNotes(''); setActiveFrom(today())
  }

  const openTick = (m: GuidelineModule) => {
    closeTick()
    setTickTarget(m)
  }

  /** One call for both steps — the endpoint answers "what would happen" and
   *  "do it" on the same route, and the status code says which it answered. */
  const postEntitlement = async (m: GuidelineModule, confirm: boolean) => {
    setBusy(true); setRefusal(null); setTickError(null)
    try {
      const res = await fetch('/api/entitlements', {
        method: 'POST',
        headers: makeHeaders(),
        body: JSON.stringify({
          module_id: m.id,
          active_from: activeFrom,
          confirm,
          first_due_on: firstDueOn || null,
          notes: tickNotes.trim() || null,
        }),
      })
      const data: EntitlementPlanResponse & { detail?: string } = await res.json()

      if (res.status === 403) {
        setRefusal({ kind: 'forbidden', detail: data.detail || 'Only Executive Management can change entitlements.' })
        return
      }
      if (res.status === 409) {
        // 023's verified-to-sell constraint, answered in words. The module is
        // real; it is simply not verified yet. Also covers "already entitled".
        const detail = data.detail || 'This module cannot be ticked yet.'
        setRefusal({
          kind: detail.toLowerCase().includes('already entitled') ? 'conflict' : 'unavailable',
          detail,
        })
        return
      }
      if (!res.ok) { setTickError(data.detail || 'The request could not be completed.'); return }

      setPlan(data.plan)
      if (confirm && data.created) {
        setNotice(
          `${m.label || m.key} ticked. ${data.obligations_created ?? 0} obligation(s) created — `
          + 'they are now in the Obligation Registry.',
        )
        closeTick()
        await fetchModules()
        await fetchRegistry()
      }
    } catch {
      setTickError('Network error. Nothing was written.')
    } finally {
      setBusy(false)
    }
  }

  const confirmUntick = async (m: GuidelineModule) => {
    if (!m.entitlement_id) return
    setBusy(true); setRefusal(null); setTickError(null)
    try {
      const res = await fetch(`/api/entitlements/${encodeURIComponent(m.entitlement_id)}`, {
        method: 'DELETE',
        headers: makeHeaders(),
      })
      const data: DeactivateResponse & { detail?: string } = await res.json()
      if (res.status === 403) {
        setRefusal({ kind: 'forbidden', detail: data.detail || 'Only Executive Management can change entitlements.' })
        return
      }
      if (!res.ok) { setTickError(data.detail || 'The entitlement could not be closed.'); return }
      setWentDark({
        module: m.label || m.key || 'module',
        rows: data.no_longer_monitored || [],
        message: data.message,
      })
      setUntickTarget(null)
      await fetchModules()
      await fetchRegistry()
    } catch {
      setTickError('Network error. The entitlement was not changed.')
    } finally {
      setBusy(false)
    }
  }

  /** Duties currently attached to this entitlement — what would go dark. Read
   *  straight from the registry rows; no status is derived from them here. */
  const dutiesFor = (m: GuidelineModule): Obligation[] =>
    m.entitlement_id ? registry.filter(o => o.entitlement_id === m.entitlement_id) : []

  const showsPrice = modules.some(m => m.list_price_monthly !== undefined)

  const grouped = useMemo(() => {
    const byCategory = new Map<string, GuidelineModule[]>()
    for (const m of modules) {
      const key = m.category || 'Uncategorised'
      const bucket = byCategory.get(key)
      if (bucket) bucket.push(m)
      else byCategory.set(key, [m])
    }
    return [...byCategory.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [modules])

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader
        title="Module Catalogue"
        subtitle="Every DM guideline module — what it claims, where its content came from, and what this organisation is entitled to"
        icon="🧾"
      />

      {error && (
        <div style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #fecaca' }}>
          {error}
        </div>
      )}
      {notice && (
        <div style={{ background: COLORS.greenBg, color: COLORS.greenFg, padding: '0.75rem 1rem', borderRadius: 6, marginBottom: 16, fontSize: '0.875rem', border: '1px solid #86efac' }}>
          {notice}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginBottom: 16 }}>
        <span style={{ fontSize: '0.82rem', color: COLORS.slate }}>
          <strong style={{ color: TOKENS.ink }}>{modules.length}</strong> modules ·{' '}
          <strong style={{ color: TOKENS.ink }}>{entitledCount}</strong> entitled ·{' '}
          <strong style={{ color: TOKENS.ink }}>{sellableCount}</strong> on sale
        </span>
        <Button variant="secondary" size="sm" onClick={fetchModules} disabled={loading}>
          <RefreshCw size={14} /> {loading ? 'Loading…' : 'Refresh'}
        </Button>
      </div>

      {!canManage && (
        <AlertCard
          style={{ marginBottom: 16 }}
          tier="awaiting"
          title="You can read this catalogue but not change it"
          description={
            'Ticking and un-ticking modules is reserved to Executive Management '
            + '(entitlements.manage). Un-ticking is the reason: it stops monitoring, so it is '
            + 'not offered to the role most likely to want an overdue duty to stop being tracked. '
            + 'Everything on this page is still readable.'
          }
        />
      )}

      {sellableCount === 0 && modules.length > 0 && (
        <AlertCard
          style={{ marginBottom: 16 }}
          tier="awaiting"
          title="No module is on sale yet"
          description={
            'Every module in the catalogue is loaded but not yet verified — nobody has read the '
            + 'published DM document against its content, and migration 023 refuses to put an '
            + 'unverified module on sale (§7.1). The modules are real; verification is editorial '
            + 'work, not a code change. Ticking one will be refused, with the reason, until then.'
          }
        />
      )}

      {wentDark && (
        <div className="glass-card" style={{ padding: '1rem 1.15rem', marginBottom: 20, borderLeft: `5px solid ${TOKENS.warning}` }}>
          <div style={{ fontWeight: 700, color: TOKENS.ink }}>
            Monitoring stopped — {wentDark.module}
          </div>
          <div style={{ fontSize: '0.8rem', color: COLORS.slate, margin: '4px 0 10px', lineHeight: 1.5 }}>
            {wentDark.message}
          </div>
          {wentDark.rows.length > 0 && (
            <>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: COLORS.slate, marginBottom: 6 }}>
                No longer monitored ({wentDark.rows.length})
              </div>
              <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.82rem', color: TOKENS.ink }}>
                {wentDark.rows.map(r => (
                  <li key={r.id} style={{ marginBottom: 2 }}>
                    {r.label || r.id}
                    <span style={{ color: COLORS.slate }}>
                      {r.next_due_on ? ` — was next due ${r.next_due_on}` : ' — had no due date'}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <div style={{ marginTop: 12 }}>
            <Button variant="secondary" size="sm" onClick={() => setWentDark(null)}>Dismiss</Button>
          </div>
        </div>
      )}

      {grouped.map(([category, rows]) => (
        <div key={category} style={{ marginBottom: 24 }}>
          <div style={{ fontWeight: 700, color: TOKENS.ink, marginBottom: '0.4rem' }}>{category}</div>
          <div className="glass-card" style={{ padding: 0, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1040 }}>
              <thead>
                <tr>
                  <th style={tableHeaderStyle}>Module</th>
                  <th style={tableHeaderStyle}>Kind</th>
                  <th style={tableHeaderStyle}>Catalogue status</th>
                  <th style={tableHeaderStyle}>Provenance</th>
                  {showsPrice && <th style={tableHeaderStyle}>List price</th>}
                  <th style={tableHeaderStyle}>Entitled</th>
                  <th style={tableHeaderStyle}>Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(m => {
                  const kind = presentModuleKind(m.module_kind)
                  const status = presentModuleStatus(m.status)
                  const provenance = presentProvenance(m.provenance)
                  const duties = dutiesFor(m)
                  return (
                    <tr key={m.id}>
                      <td style={{ ...tableCellStyle, maxWidth: 340 }}>
                        <div style={{ fontWeight: 600, color: TOKENS.ink }}>{m.label || m.key}</div>
                        {m.key && m.label && (
                          <div style={{ fontSize: '0.72rem', color: COLORS.slate }}>{m.key}</div>
                        )}
                        {m.obligation_type && (
                          <div style={{ fontSize: '0.72rem', color: COLORS.slate }}>
                            Duty type: {m.obligation_type}
                          </div>
                        )}
                        {m.notes && (
                          <div style={{ fontSize: '0.74rem', color: COLORS.slate, marginTop: 3, lineHeight: 1.45 }}>
                            {m.notes}
                          </div>
                        )}
                      </td>
                      <td style={tableCellStyle}>
                        <StatusBadge tone={kind.tone} variant="count">{kind.label}</StatusBadge>
                        <div style={{ fontSize: '0.72rem', color: COLORS.slate, marginTop: 4, maxWidth: 220, lineHeight: 1.45 }}>
                          {kind.description}
                        </div>
                      </td>
                      <td style={tableCellStyle}>
                        <StatusBadge tone={status.tone} variant="count">{status.label}</StatusBadge>
                      </td>
                      <td style={tableCellStyle}>
                        <StatusBadge tone={provenance.tone} variant="count">{provenance.label}</StatusBadge>
                      </td>
                      {showsPrice && (
                        <td style={tableCellStyle}>
                          {m.list_price_monthly == null
                            ? <span style={{ color: COLORS.slate }}>—</span>
                            : `${m.currency || ''} ${m.list_price_monthly}`.trim()}
                        </td>
                      )}
                      <td style={tableCellStyle}>
                        {m.entitled ? (
                          <>
                            <StatusBadge tone="green" variant="count">Entitled</StatusBadge>
                            <div style={{ fontSize: '0.72rem', color: COLORS.slate, marginTop: 4 }}>
                              since {m.active_from}
                              {duties.length > 0 && ` · ${duties.length} duties tracked`}
                            </div>
                          </>
                        ) : m.active_until ? (
                          <>
                            <StatusBadge tone="slate" variant="count">Closed</StatusBadge>
                            <div style={{ fontSize: '0.72rem', color: COLORS.slate, marginTop: 4 }}>
                              until {m.active_until} — history retained
                            </div>
                          </>
                        ) : (
                          <StatusBadge tone="slate" variant="count">Not entitled</StatusBadge>
                        )}
                      </td>
                      <td style={tableCellStyle}>
                        {m.entitled ? (
                          <Button
                            variant="secondary" size="sm"
                            disabled={!canManage}
                            title={canManage ? undefined : 'Executive Management only'}
                            onClick={() => { setTickError(null); setRefusal(null); setUntickTarget(m) }}
                          >
                            {!canManage && <Lock size={13} />} Un-tick…
                          </Button>
                        ) : (
                          <Button
                            variant={m.sellable ? 'primary' : 'secondary'} size="sm"
                            disabled={!canManage}
                            title={canManage ? undefined : 'Executive Management only'}
                            onClick={() => openTick(m)}
                          >
                            {!canManage && <Lock size={13} />}
                            {m.sellable ? 'Tick module…' : 'Why not available?'}
                          </Button>
                        )}
                        {/* The server's own words for why 023 would refuse this
                            module. More useful than a disabled checkbox. */}
                        {!m.sellable && m.not_sellable_reason && (
                          <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start', marginTop: 6, maxWidth: 260 }}>
                            <Info size={13} color={TOKENS.awaiting} style={{ flexShrink: 0, marginTop: 2 }} />
                            <span style={{ fontSize: '0.72rem', color: COLORS.slate, lineHeight: 1.45 }}>
                              {m.not_sellable_reason}
                            </span>
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {/* ── Tick: plan first, then confirm ─────────────────────────────────── */}
      {tickTarget && (
        <Modal title={`Tick ${tickTarget.label || tickTarget.key}`} onClose={closeTick}>
          {refusal && (
            <AlertCard
              style={{ marginBottom: 14 }}
              tier="awaiting"
              title={
                refusal.kind === 'forbidden' ? 'Not your permission to use'
                  : refusal.kind === 'conflict' ? 'Already entitled'
                    : 'Not on sale yet — the module is real, it is simply not verified'
              }
              description={refusal.detail}
            />
          )}
          {tickError && (
            <div style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.6rem 0.8rem', borderRadius: 6, marginBottom: 14, fontSize: '0.82rem' }}>
              {tickError}
            </div>
          )}

          {!plan && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              <div style={fieldStyle}>
                <label style={labelStyle} htmlFor="active-from">Active from</label>
                <input
                  id="active-from" type="date" style={inputStyle}
                  value={activeFrom} onChange={e => setActiveFrom(e.target.value)}
                />
                <span style={{ fontSize: '0.72rem', color: COLORS.slate }}>
                  When monitoring and billing begin. Required and never defaulted by the server —
                  a guessed date either backdates a commercial agreement or opens a window of
                  unmonitored time nobody can see.
                </span>
              </div>
              <div style={fieldStyle}>
                <label style={labelStyle} htmlFor="first-due">First due date (optional)</label>
                <input
                  id="first-due" type="date" style={inputStyle}
                  value={firstDueOn} onChange={e => setFirstDueOn(e.target.value)}
                />
                <span style={{ fontSize: '0.72rem', color: COLORS.slate }}>
                  Left empty means today: a newly entitled module has no evidence on file, so its
                  duties are outstanding now. Setting this is a claim about the past — say why in
                  the note.
                </span>
              </div>
              <div style={fieldStyle}>
                <label style={labelStyle} htmlFor="tick-notes">Note (optional)</label>
                <input
                  id="tick-notes" type="text" style={inputStyle} value={tickNotes}
                  onChange={e => setTickNotes(e.target.value)}
                  placeholder="e.g. agreed with client 14 Aug, backdated to contract start"
                />
              </div>
              <div style={{ fontSize: '0.76rem', color: COLORS.slate, lineHeight: 1.5 }}>
                This covers every site in your organisation. Nothing is written until you have seen
                the plan and confirmed it.
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                <Button variant="secondary" size="sm" onClick={closeTick}>Cancel</Button>
                <Button
                  size="sm" disabled={busy || !activeFrom}
                  onClick={() => postEntitlement(tickTarget, false)}
                >
                  {busy ? 'Checking…' : 'Show me what this creates'}
                </Button>
              </div>
            </div>
          )}

          {plan && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
              <PlanPanel plan={plan} />
              <div style={{ fontSize: '0.76rem', color: COLORS.slate }}>
                Nothing has been written yet. Confirming creates the entitlement from{' '}
                <strong>{activeFrom}</strong> and instantiates the duties above.
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                <Button variant="secondary" size="sm" onClick={closeTick}>Cancel — write nothing</Button>
                <Button
                  size="sm" disabled={busy}
                  onClick={() => postEntitlement(tickTarget, true)}
                >
                  {busy ? 'Ticking…' : `Confirm — create ${plan.obligations.total} obligation(s)`}
                </Button>
              </div>
            </div>
          )}
        </Modal>
      )}

      {/* ── Un-tick: name what stops being tracked, before it stops ────────── */}
      {untickTarget && (
        <Modal title={`Un-tick ${untickTarget.label || untickTarget.key}`} onClose={() => setUntickTarget(null)}>
          {refusal && (
            <AlertCard
              style={{ marginBottom: 14 }}
              tier="awaiting"
              title="Not your permission to use"
              description={refusal.detail}
            />
          )}
          {tickError && (
            <div style={{ background: COLORS.redBg, color: COLORS.redFg, padding: '0.6rem 0.8rem', borderRadius: 6, marginBottom: 14, fontSize: '0.82rem' }}>
              {tickError}
            </div>
          )}
          <AlertCard
            tier="actionRequired"
            title={`${dutiesFor(untickTarget).length} obligation(s) stop being monitored`}
            description={
              'Nothing is deleted. Every obligation, sample and certificate is retained and stays '
              + 'visible as suspended — deliberately not "compliant", because a commercial decision '
              + 'must not read as a clean compliance record. What changes is that these duties stop '
              + 'being aged, so nobody will be told when they next fall due.'
            }
          />
          {dutiesFor(untickTarget).length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', color: COLORS.slate, marginBottom: 6 }}>
                These go dark
              </div>
              <ul style={{ margin: 0, paddingLeft: '1.1rem', fontSize: '0.83rem', color: TOKENS.ink, maxHeight: 220, overflowY: 'auto' }}>
                {dutiesFor(untickTarget).map(o => (
                  <li key={o.id} style={{ marginBottom: 3 }}>
                    {o.label}
                    <span style={{ color: COLORS.slate }}>
                      {' '}— {o.site_name || 'Organisation-wide'}
                      {o.next_due_on ? `, next due ${o.next_due_on}` : ', no due date set'}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: 16 }}>
            <Button variant="secondary" size="sm" onClick={() => setUntickTarget(null)}>Keep monitoring</Button>
            <Button
              variant="destructive" size="sm" disabled={busy}
              onClick={() => confirmUntick(untickTarget)}
            >
              {busy ? 'Closing…' : 'Stop monitoring this module'}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
