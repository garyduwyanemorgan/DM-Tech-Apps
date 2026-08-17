// System Health — the screen that answers "where and why did it break", per
// site/entity, not "an error occurred". Phase 1 observability.
//
// The pipeline is a fixed sequence: ingest -> parse -> validate -> persist ->
// assess -> obligation -> report. A broken step must be visible at a glance
// (the pipeline strip), the recent failures must be readable without jargon
// (reason codes are rendered from the server's own description map — never
// hardcoded here), and any one failure must be traceable to the exact step
// and moment it happened (the run timeline drill-down).
//
// THREE STATES, never conflated:
//   - data:    the request succeeded and there is something to show.
//   - empty:   the request succeeded and there is genuinely nothing — a good
//              outcome ("no failures in this period"), styled as such.
//   - unavailable: the request failed (network error, 404, 500, bad shape).
//              Said loudly. Never rendered as zero, and never backed by
//              sample data — there is no sample-data fallback anywhere here.
import React, { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { PageHeader } from './PageHeader'
import { tableHeaderStyle, tableCellStyle, labelStyle } from '../lib/ui'
import { COLORS as TOKENS } from '../lib/tokens'
import { AlertCard, Button, StatusBadge } from './ui'
import { RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'

// ---------------------------------------------------------------------------
// API contract (frontend/src/components/SystemHealth.tsx owns these types —
// the backend at api_server.py is being built against this same contract).
// ---------------------------------------------------------------------------

export const PIPELINE_STEPS = [
  'ingest', 'parse', 'validate', 'persist', 'assess', 'obligation', 'report',
] as const
export type PipelineStep = typeof PIPELINE_STEPS[number]

interface StepStatusCount {
  step: string
  status: string
  count: number
}

interface ReasonCodeCount {
  reason_code: string
  count: number
}

interface HealthTotals {
  ok: number
  failed: number
  total: number
}

interface SystemHealthSummary {
  counts: StepStatusCount[]
  by_reason_code: ReasonCodeCount[]
  totals: HealthTotals
  /** Human descriptions keyed by reason_code. This screen never hardcodes
   *  reason-code copy — it renders this map, verbatim, everywhere a code
   *  would otherwise appear. */
  reason_codes: Record<string, string>
}

interface FailureEvent {
  step: string
  reason_code: string
  entity_type: string
  entity_id: string
  run_id: string
  request_id: string
  created_at: string
}

interface SystemFailuresResponse {
  failures: FailureEvent[]
}

interface RunTimelineEvent {
  step: string
  status: string
  reason_code: string | null
  duration_ms: number | null
  created_at: string
  detail?: string | null
}

interface RunTimelineResponse {
  run_id: string
  events: RunTimelineEvent[]
}

/** Fetch outcome, kept distinct from "the data is an empty array" on purpose. */
type Fetched<T> =
  | { state: 'loading' }
  | { state: 'ok'; data: T }
  | { state: 'unavailable'; message: string }

const RANGE_OPTIONS: { label: string; hours: number }[] = [
  { label: 'Last 1h', hours: 1 },
  { label: 'Last 24h', hours: 24 },
  { label: 'Last 7d', hours: 168 },
]

const stepLabel = (step: string): string =>
  step.charAt(0).toUpperCase() + step.slice(1)

const fmtDuration = (ms: number | null): string => {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

const fmtTime = (iso: string): string => {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

// ---------------------------------------------------------------------------

/** One step's tile in the pipeline strip. */
const StepTile: React.FC<{
  step: string
  ok: number
  failed: number
}> = ({ step, ok, failed }) => {
  const broken = failed > 0
  return (
    <div
      className="glass-card"
      style={{
        flex: '1 1 120px',
        minWidth: 120,
        padding: '0.85rem 0.9rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.4rem',
        borderTop: `4px solid ${broken ? TOKENS.critical : TOKENS.compliant}`,
      }}
    >
      <span style={{ fontSize: '0.72rem', fontWeight: 700, color: TOKENS.slate, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {stepLabel(step)}
      </span>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'baseline' }}>
        <span style={{ fontSize: '1.25rem', fontWeight: 800, color: broken ? '#9C0006' : '#006100' }}>
          {ok}
        </span>
        <span style={{ fontSize: '0.68rem', color: TOKENS.slate }}>ok</span>
      </div>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'baseline' }}>
        <span style={{ fontSize: '1.25rem', fontWeight: 800, color: broken ? '#9C0006' : TOKENS.slate }}>
          {failed}
        </span>
        <span style={{ fontSize: '0.68rem', color: TOKENS.slate }}>failed</span>
      </div>
    </div>
  )
}

/** Expanded drill-down: the chronological timeline for one run. */
const RunTimeline: React.FC<{
  run: Fetched<RunTimelineResponse>
  reasonCodes: Record<string, string>
}> = ({ run, reasonCodes }) => {
  if (run.state === 'loading') {
    return (
      <div style={{ padding: '0.9rem 1.1rem', fontSize: '0.82rem', color: TOKENS.slate }}>
        Loading run timeline…
      </div>
    )
  }
  if (run.state === 'unavailable') {
    return (
      <div style={{ padding: '0.75rem 1.1rem' }}>
        <AlertCard tier="critical" title="Could not load this run's timeline" description={run.message} />
      </div>
    )
  }
  if (run.data.events.length === 0) {
    return (
      <div style={{ padding: '0.75rem 1.1rem' }}>
        <AlertCard
          tier="awaiting"
          title="No events recorded for this run"
          description="The run exists but no step events were logged against it. This is not the same as a passing run — treat it as unverified."
        />
      </div>
    )
  }
  return (
    <div style={{ padding: '0.75rem 1.1rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
      {run.data.events.map((ev, i) => {
        const ok = ev.status === 'ok' || ev.status === 'success'
        return (
          <div
            key={`${ev.step}-${i}`}
            style={{
              display: 'flex', alignItems: 'flex-start', gap: '0.75rem',
              padding: '0.5rem 0.6rem',
              borderLeft: `3px solid ${ok ? TOKENS.compliant : TOKENS.critical}`,
              background: TOKENS.surface,
              borderRadius: 6,
            }}
          >
            <StatusBadge tone={ok ? 'green' : 'red'} variant="count">{stepLabel(ev.step)}</StatusBadge>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '0.8rem', color: TOKENS.ink, fontWeight: 600 }}>
                {ev.status}
                <span style={{ fontWeight: 400, color: TOKENS.slate }}> — {fmtDuration(ev.duration_ms)}</span>
              </div>
              {ev.reason_code && (
                <div style={{ fontSize: '0.78rem', color: '#9C0006', marginTop: 2 }}>
                  {reasonCodes[ev.reason_code] || ev.reason_code}
                </div>
              )}
              {ev.detail && (
                <div style={{ fontSize: '0.76rem', color: TOKENS.slate, marginTop: 2 }}>{ev.detail}</div>
              )}
            </div>
            <span style={{ fontSize: '0.72rem', color: TOKENS.slate, flexShrink: 0 }}>{fmtTime(ev.created_at)}</span>
          </div>
        )
      })}
    </div>
  )
}

export const SystemHealth: React.FC = () => {
  const { organizationId, getToken } = useAuth()

  const [health, setHealth] = useState<Fetched<SystemHealthSummary>>({ state: 'loading' })
  const [failures, setFailures] = useState<Fetched<SystemFailuresResponse>>({ state: 'loading' })
  const [sinceHours, setSinceHours] = useState<number>(24)
  const [refreshing, setRefreshing] = useState(false)

  const [expandedRun, setExpandedRun] = useState<string | null>(null)
  const [runTimelines, setRunTimelines] = useState<Record<string, Fetched<RunTimelineResponse>>>({})

  // Fresh token per request — a cached token can expire mid-session and a
  // stale one 401s silently, which would look identical to "nothing failed".
  const makeHeaders = useCallback(async (): Promise<HeadersInit> => {
    const h: Record<string, string> = { 'Content-Type': 'application/json' }
    const t = await getToken()
    if (t) h['Authorization'] = `Bearer ${t}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }, [getToken, organizationId])

  const fetchHealth = useCallback(async () => {
    setHealth(prev => (prev.state === 'ok' ? prev : { state: 'loading' }))
    try {
      const headers = await makeHeaders()
      const res = await fetch('/api/system/health', { headers })
      if (!res.ok) {
        setHealth({ state: 'unavailable', message: `Health endpoint returned ${res.status}. The pipeline status cannot be verified right now.` })
        return
      }
      const data = (await res.json()) as Partial<SystemHealthSummary>
      if (!data || !Array.isArray(data.counts) || !data.reason_codes) {
        setHealth({ state: 'unavailable', message: 'Health endpoint returned an unexpected shape. Refusing to guess at pipeline status.' })
        return
      }
      setHealth({
        state: 'ok',
        data: {
          counts: data.counts,
          by_reason_code: Array.isArray(data.by_reason_code) ? data.by_reason_code : [],
          totals: data.totals ?? { ok: 0, failed: 0, total: 0 },
          reason_codes: data.reason_codes,
        },
      })
    } catch {
      setHealth({ state: 'unavailable', message: 'Network error reaching the health endpoint. Pipeline status is unknown, not clean.' })
    }
  }, [makeHeaders])

  const fetchFailures = useCallback(async () => {
    setFailures(prev => (prev.state === 'ok' ? prev : { state: 'loading' }))
    try {
      const headers = await makeHeaders()
      const res = await fetch(`/api/system/failures?since_hours=${sinceHours}&limit=50`, { headers })
      if (!res.ok) {
        setFailures({ state: 'unavailable', message: `Failures endpoint returned ${res.status}. Recent failures cannot be confirmed — this is not the same as "no failures".` })
        return
      }
      const data = (await res.json()) as Partial<SystemFailuresResponse>
      if (!data || !Array.isArray(data.failures)) {
        setFailures({ state: 'unavailable', message: 'Failures endpoint returned an unexpected shape. Refusing to render it as an empty list.' })
        return
      }
      setFailures({ state: 'ok', data: { failures: data.failures } })
    } catch {
      setFailures({ state: 'unavailable', message: 'Network error reaching the failures endpoint. Recent failures are unknown, not zero.' })
    }
  }, [makeHeaders, sinceHours])

  useEffect(() => { fetchHealth() }, [fetchHealth])
  useEffect(() => { fetchFailures() }, [fetchFailures])

  const refreshAll = async () => {
    setRefreshing(true)
    await Promise.all([fetchHealth(), fetchFailures()])
    setRefreshing(false)
  }

  const toggleRun = async (runId: string) => {
    if (expandedRun === runId) { setExpandedRun(null); return }
    setExpandedRun(runId)
    if (runTimelines[runId]) return // already fetched
    setRunTimelines(prev => ({ ...prev, [runId]: { state: 'loading' } }))
    try {
      const headers = await makeHeaders()
      const res = await fetch(`/api/system/runs/${encodeURIComponent(runId)}`, { headers })
      if (!res.ok) {
        setRunTimelines(prev => ({ ...prev, [runId]: { state: 'unavailable', message: `Run endpoint returned ${res.status}.` } }))
        return
      }
      const data = (await res.json()) as Partial<RunTimelineResponse>
      if (!data || !Array.isArray(data.events)) {
        setRunTimelines(prev => ({ ...prev, [runId]: { state: 'unavailable', message: 'Run endpoint returned an unexpected shape.' } }))
        return
      }
      setRunTimelines(prev => ({ ...prev, [runId]: { state: 'ok', data: { run_id: runId, events: data.events! } } }))
    } catch {
      setRunTimelines(prev => ({ ...prev, [runId]: { state: 'unavailable', message: 'Network error loading this run.' } }))
    }
  }

  const reasonCodes = health.state === 'ok' ? health.data.reason_codes : {}

  // Build the per-step ok/failed tallies for the strip. Every one of the 7
  // fixed steps is always shown, even at zero — a step with no counts at all
  // is still a fact worth seeing, not something to hide.
  const stepCounts: Record<string, { ok: number; failed: number }> = {}
  for (const s of PIPELINE_STEPS) stepCounts[s] = { ok: 0, failed: 0 }
  if (health.state === 'ok') {
    for (const c of health.data.counts) {
      if (!stepCounts[c.step]) stepCounts[c.step] = { ok: 0, failed: 0 }
      if (c.status === 'ok' || c.status === 'success') stepCounts[c.step].ok += c.count
      else stepCounts[c.step].failed += c.count
    }
  }
  const extraSteps = health.state === 'ok'
    ? Array.from(new Set(health.data.counts.map(c => c.step))).filter(s => !(PIPELINE_STEPS as readonly string[]).includes(s))
    : []

  return (
    <div style={{ padding: '24px', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader
        title="System Health"
        subtitle="Where and why did it break — per step, per entity, per run"
        icon="🩺"
      />

      {/* Controls */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1rem', flexWrap: 'wrap', marginBottom: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
          <label style={labelStyle} htmlFor="system-health-range">Time range</label>
          <div style={{ display: 'flex', gap: '0.4rem' }} id="system-health-range">
            {RANGE_OPTIONS.map(opt => (
              <Button
                key={opt.hours}
                variant={sinceHours === opt.hours ? 'primary' : 'secondary'}
                size="sm"
                onClick={() => setSinceHours(opt.hours)}
              >
                {opt.label}
              </Button>
            ))}
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={refreshAll} disabled={refreshing}>
          <RefreshCw size={14} /> {refreshing ? 'Refreshing…' : 'Refresh'}
        </Button>
      </div>

      {/* Pipeline strip */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontWeight: 700, color: TOKENS.ink, marginBottom: 8, fontSize: '0.95rem' }}>Pipeline</div>
        {health.state === 'unavailable' && (
          <AlertCard tier="critical" title="Pipeline status unavailable" description={health.message} />
        )}
        {health.state === 'loading' && (
          <div style={{ fontSize: '0.85rem', color: TOKENS.slate }}>Loading pipeline status…</div>
        )}
        {health.state === 'ok' && (
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            {PIPELINE_STEPS.map(step => (
              <StepTile key={step} step={step} ok={stepCounts[step].ok} failed={stepCounts[step].failed} />
            ))}
            {extraSteps.map(step => (
              <StepTile key={step} step={step} ok={stepCounts[step].ok} failed={stepCounts[step].failed} />
            ))}
          </div>
        )}
        {health.state === 'ok' && health.data.totals.total === 0 && (
          <div style={{ marginTop: 10 }}>
            <AlertCard
              tier="awaiting"
              title="No pipeline activity recorded"
              description="The health endpoint answered, but nothing has run yet. This is not the same as everything passing."
            />
          </div>
        )}
      </div>

      {/* Failures table */}
      <div>
        <div style={{ fontWeight: 700, color: TOKENS.ink, marginBottom: 8, fontSize: '0.95rem' }}>
          Recent failures
        </div>

        {failures.state === 'unavailable' && (
          <AlertCard tier="critical" title="Recent failures unavailable" description={failures.message} />
        )}

        {failures.state === 'loading' && (
          <div style={{ fontSize: '0.85rem', color: TOKENS.slate }}>Loading recent failures…</div>
        )}

        {failures.state === 'ok' && failures.data.failures.length === 0 && (
          <AlertCard
            tier="positive"
            title={`No failures in the selected period (${RANGE_OPTIONS.find(o => o.hours === sinceHours)?.label.toLowerCase()})`}
            description="A genuinely clean run — every event in this window completed without a failure reason."
          />
        )}

        {failures.state === 'ok' && failures.data.failures.length > 0 && (
          <div className="glass-card" style={{ padding: 0, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
              <thead>
                <tr>
                  <th style={tableHeaderStyle}>Time</th>
                  <th style={tableHeaderStyle}>Step</th>
                  <th style={tableHeaderStyle}>Entity</th>
                  <th style={tableHeaderStyle}>Reason</th>
                  <th style={tableHeaderStyle}>Run</th>
                </tr>
              </thead>
              <tbody>
                {failures.data.failures.map((f, i) => {
                  const isOpen = expandedRun === f.run_id
                  return (
                    <React.Fragment key={`${f.run_id}-${f.step}-${i}`}>
                      <tr
                        onClick={() => toggleRun(f.run_id)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td style={tableCellStyle}>{fmtTime(f.created_at)}</td>
                        <td style={tableCellStyle}>
                          <StatusBadge tone="red" variant="count">{stepLabel(f.step)}</StatusBadge>
                        </td>
                        <td style={tableCellStyle}>
                          {f.entity_type
                            ? <span>{f.entity_type} <span style={{ color: TOKENS.slate }}>{f.entity_id}</span></span>
                            : <span style={{ color: TOKENS.slate }}>—</span>}
                        </td>
                        <td style={{ ...tableCellStyle, maxWidth: 340 }}>
                          {reasonCodes[f.reason_code] || f.reason_code}
                        </td>
                        <td style={{ ...tableCellStyle, fontFamily: 'monospace', fontSize: '0.78rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            {f.run_id}
                          </div>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={5} style={{ padding: 0, borderBottom: '1px solid #f1f5f9', background: '#fbfcfe' }}>
                            <RunTimeline run={runTimelines[f.run_id] ?? { state: 'loading' }} reasonCodes={reasonCodes} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
