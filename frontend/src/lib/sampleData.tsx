/**
 * The single gate between built-in sample data and real lab readings.
 *
 * Two rules, and they are the whole point of this module:
 *
 *  1. A series is EITHER entirely live OR entirely sample. It is never a blend.
 *     Back-filling a missing live value with a sample one produces a number that
 *     looks measured, gets scored against a compliance limit, and can end up in
 *     front of a regulator. Months with no reading stay `null` and render as "—".
 *
 *  2. When the user has sample data switched off, sample data is not rendered
 *     anywhere, for any page, in any form. Pages show `<NoData />` instead.
 *
 * Live values always come from `/api/readings/{site}`, which returns all 14
 * parameters per month. `/api/status` returns only compliance + alert level and
 * must never be used as a value source.
 */
import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { MONTHLY_DATA } from '../constants'

/** Parameter keys of a monthly series — matches MONTHLY_DATA. */
export type ParamKey = keyof typeof MONTHLY_DATA

/** 12 slots (Jan–Dec). `null` = no reading for that month. Never a sample stand-in. */
export type Series = Record<ParamKey, (number | null)[]>

export type SeriesSource = 'live' | 'sample' | 'none'

export interface MonthlySeries {
  /** null when there is nothing legitimate to show. */
  series: Series | null
  source: SeriesSource
  loading: boolean
  /** Month indices (0–11) that carry a real reading. Empty for sample data. */
  liveMonths: number[]
}

const PARAM_KEYS = Object.keys(MONTHLY_DATA) as ParamKey[]

/** `/api/readings` names it total_coliforms; MONTHLY_DATA names it coliforms. */
const API_FIELD: Record<ParamKey, string> = {
  ph: 'ph',
  do: 'do',
  tss: 'tss',
  turbidity: 'turbidity',
  cod: 'cod',
  ammonia: 'ammonia',
  phosphate: 'phosphate',
  oil_grease: 'oil_grease',
  ecoli: 'ecoli',
  coliforms: 'total_coliforms',
  chla: 'chla',
  phycocyanin: 'phycocyanin',
  salinity: 'salinity',
  water_temp: 'water_temp',
}

interface ReadingRow {
  month: number // 1–12
  [param: string]: number | string | null
}

function emptySeries(): Series {
  return PARAM_KEYS.reduce((acc, key) => {
    acc[key] = Array(12).fill(null)
    return acc
  }, {} as Series)
}

function seriesFromRows(rows: ReadingRow[]): { series: Series; liveMonths: number[] } {
  const series = emptySeries()
  const liveMonths: number[] = []

  for (const row of rows) {
    const i = (row.month ?? 0) - 1
    if (i < 0 || i > 11) continue
    liveMonths.push(i)
    for (const key of PARAM_KEYS) {
      const raw = row[API_FIELD[key]]
      series[key][i] = typeof raw === 'number' ? raw : null
    }
  }

  return { series, liveMonths: [...new Set(liveMonths)].sort((a, b) => a - b) }
}

/** The sample seasonal baseline, widened to the nullable series type. */
function sampleSeries(): Series {
  return PARAM_KEYS.reduce((acc, key) => {
    acc[key] = [...MONTHLY_DATA[key]]
    return acc
  }, {} as Series)
}

/**
 * Resolve the 12-month series for a site.
 *
 * Live readings if the site has any; otherwise the sample baseline, but only if
 * the user has sample data switched on; otherwise nothing.
 */
export function useMonthlySeries(activeSite: string, year = new Date().getFullYear()): MonthlySeries {
  const { organizationId, token, showSampleData } = useAuth()
  const [live, setLive] = useState<{ series: Series; liveMonths: number[] } | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!activeSite) {
      setLive(null)
      return
    }
    let cancelled = false
    setLoading(true)

    const load = async () => {
      try {
        const headers: HeadersInit = {}
        if (organizationId) headers['X-Organization-ID'] = organizationId
        if (token) headers['Authorization'] = `Bearer ${token}`
        const res = await fetch(
          `/api/readings/${encodeURIComponent(activeSite)}?year=${year}`,
          { headers },
        )
        const json = await res.json()
        const rows: ReadingRow[] = res.ok && Array.isArray(json.rows) ? json.rows : []
        if (!cancelled) setLive(rows.length > 0 ? seriesFromRows(rows) : null)
      } catch {
        if (!cancelled) setLive(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [activeSite, organizationId, token, year])

  if (live) {
    return { series: live.series, source: 'live', loading, liveMonths: live.liveMonths }
  }
  if (showSampleData) {
    return { series: sampleSeries(), source: 'sample', loading, liveMonths: [] }
  }
  return { series: null, source: 'none', loading, liveMonths: [] }
}

/** Format a possibly-absent measurement. Never invents a value. */
export function fmt(value: number | null | undefined, digits = 2): string {
  return typeof value === 'number' ? value.toFixed(digits) : '—'
}

/** Mean of the months that actually carry a reading. null if there are none. */
export function meanOf(values: (number | null)[]): number | null {
  const present = values.filter((v): v is number => typeof v === 'number')
  if (present.length === 0) return null
  return present.reduce((a, b) => a + b, 0) / present.length
}

export function maxOf(values: (number | null)[]): number | null {
  const present = values.filter((v): v is number => typeof v === 'number')
  return present.length ? Math.max(...present) : null
}

export function minOf(values: (number | null)[]): number | null {
  const present = values.filter((v): v is number => typeof v === 'number')
  return present.length ? Math.min(...present) : null
}

/**
 * Shown wherever a page would otherwise have rendered sample data the user has
 * switched off. Deliberately offers no numbers at all.
 */
export const NoData: React.FC<{ title?: string; icon?: string }> = ({
  title = 'No data to display',
  icon = '📊',
}) => (
  <div
    style={{
      background: '#f8fafc',
      border: '1px solid #e2e8f0',
      borderRadius: 10,
      padding: '3rem',
      textAlign: 'center',
      color: '#94a3b8',
    }}
  >
    <div style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>{icon}</div>
    <div style={{ fontWeight: 600, color: '#64748b', marginBottom: '0.5rem' }}>{title}</div>
    <div style={{ fontSize: '0.875rem' }}>
      Sample data is off for your account. Select a site with submitted lab readings, or
      re-enable sample data in Settings.
    </div>
  </div>
)

/** The amber "these numbers are not real" banner. Shown on every sample-fed page. */
export const SampleBanner: React.FC = () => (
  <div
    style={{
      background: '#FFEB9C',
      color: '#856404',
      padding: '0.65rem 1rem',
      borderRadius: 6,
      fontSize: '0.875rem',
      border: '1px solid #fcd34d',
    }}
  >
    <strong>Sample data — not lab readings.</strong> These values are a built-in demonstration
    baseline. Select a site with submitted readings for live figures.
  </div>
)
