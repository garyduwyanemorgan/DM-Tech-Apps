// ─────────────────────────────────────────────────────────────────────────────
// Chemistry Loop — Intelligence Engine  (System Intelligence Engine, amber loop)
//
// Presents the lagoon's chemical parameters as one interconnected system rather
// than independent laboratory values, and answers the SIE's four questions for
// any month:
//
//     What is changing?   →  trend + headline
//     Why is it changing? →  dominant (root-cause) process
//     What happens next?  →  3-month forward trajectory
//     What action?        →  operational response
//
// The model encodes the core forensic chain:
//   Organic loading → oxygen depletion → redox shift → sulphide + metal
//   mobility → internal phosphate release → fuels blooms.
//
// Deterministic, transparent: pure functions over the existing reference
// constants + regulatory limits. No ML, no external calls.
// ─────────────────────────────────────────────────────────────────────────────

import { MONTH_NAMES, MONTHLY_DATA, TREATMENT_CALENDAR } from '../constants'

export type ProcessKey =
  | 'nitrogen'
  | 'oxygen'
  | 'organic'
  | 'redox'
  | 'phosphorus'
  | 'buffering'
  | 'salinity'
  | 'metals'

export interface ProcessScore {
  key: ProcessKey
  label: string
  /** 0–100 chemical stress (100 = fully stressed / compliance pressure) */
  stress: number
  weight: number
  contribution: number
  /** driving parameter(s) as a readable value string */
  value: string
  rationale: string
  /** true if this process is modelled from redox rather than measured directly */
  modelled?: boolean
}

export interface ChemState {
  level: 'Stable' | 'Watch' | 'Stressed' | 'High' | 'Critical'
  color: string
  bg: string
  border: string
}

export interface ChemEvent {
  id: string
  label: string
  color: string
  from: ProcessKey
  pulse?: boolean
}

export interface ChemTrajectoryPoint {
  monthIndex: number
  monthName: string
  csi: number
  state: ChemState
  kind: 'past' | 'current' | 'forecast'
}

export interface ChemistryIntelligence {
  monthIndex: number
  monthName: string
  /** Chemical Stress Index, 0–100 */
  csi: number
  state: ChemState
  processes: ProcessScore[]
  dominant: ProcessScore
  events: ChemEvent[]
  trajectory: ChemTrajectoryPoint[]
  delta: number
  trend: 'rising' | 'falling' | 'stable'
  headline: string
  cause: string
  outlook: string
  action: {
    priority: string
    phase: string
    enzyme: string
    aeration: string
    steps: string[]
  }
}

export const CHEM_LOOP_COLOR = '#f59e0b' // amber — Chemistry loop identity (SIE)

// ── helpers ──────────────────────────────────────────────────────────────────
const clamp = (v: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v))
const round = (v: number) => Math.round(v * 10) / 10

/** stress (0–100) for a parameter with an upper regulatory limit */
const maxStress = (v: number, limit: number) => clamp((v / limit) * 100)

// ── stress → health colour ───────────────────────────────────────────────────
export function stressColor(stress: number): string {
  if (stress >= 80) return '#ef4444'
  if (stress >= 60) return '#f97316'
  if (stress >= 40) return '#eab308'
  if (stress >= 20) return '#38bdf8'
  return '#22c55e'
}

function classify(csi: number): ChemState {
  if (csi >= 80) return { level: 'Critical', color: '#9C0006', bg: '#FFF0F0', border: '#fecaca' }
  if (csi >= 60) return { level: 'High', color: '#c2410c', bg: '#FFF7ED', border: '#fed7aa' }
  if (csi >= 40) return { level: 'Stressed', color: '#a16207', bg: '#FEFCE8', border: '#fde68a' }
  if (csi >= 20) return { level: 'Watch', color: '#1d4ed8', bg: '#EFF6FF', border: '#bfdbfe' }
  return { level: 'Stable', color: '#15803d', bg: '#F0FDF4', border: '#bbf7d0' }
}

// ── process scoring ──────────────────────────────────────────────────────────

const WEIGHTS: Record<ProcessKey, number> = {
  oxygen: 0.18,
  organic: 0.16,
  redox: 0.14,
  phosphorus: 0.14,
  nitrogen: 0.14,
  buffering: 0.08,
  salinity: 0.08,
  metals: 0.08,
}

function processesForMonth(i: number): ProcessScore[] {
  const ph = MONTHLY_DATA.ph[i]
  const doVal = MONTHLY_DATA.do[i]
  const cod = MONTHLY_DATA.cod[i]
  const nh4 = MONTHLY_DATA.ammonia[i]
  const po4 = MONTHLY_DATA.phosphate[i]
  const oil = MONTHLY_DATA.oil_grease[i]
  const sal = MONTHLY_DATA.salinity[i]

  // Oxygen: healthy ≈ 7 mg/L, stress climbs as DO falls toward the 4.0 floor
  const oxygen = clamp(((7 - doVal) / 3) * 100)
  // Organic loading: mean of COD and Oil & Grease pressure vs their limits
  const organic = (maxStress(cod, 50) + maxStress(oil, 10)) / 2
  // Redox: low DO drives the column reducing — reuse oxygen as the redox proxy
  const redox = oxygen
  // Nitrogen: ammonia vs 5 mg/L limit
  const nitrogen = maxStress(nh4, 5)
  // Phosphorus: measured PO₄ OR internal release when sediments go anoxic
  const phosphorus = Math.max(maxStress(po4, 5), 0.7 * redox)
  // Buffering: pH drift below ~7.8 (organic-acid accumulation from respiration)
  const buffering = clamp(((7.8 - ph) / 1.3) * 100)
  // Salinity: evaporative brine (no regulatory limit — 42→58 PSU band)
  const salinity = clamp(((sal - 42) / (58 - 42)) * 100)
  // Metal mobility: Fe²⁺/Mn²⁺ released under reducing conditions (modelled from redox)
  const metals = 0.8 * redox

  const raw: Omit<ProcessScore, 'contribution'>[] = [
    {
      key: 'oxygen',
      label: 'Oxygen Cycle',
      stress: round(oxygen),
      weight: WEIGHTS.oxygen,
      value: `DO ${doVal} mg/L`,
      rationale:
        oxygen >= 60
          ? 'Dissolved oxygen is falling toward the 4 mg/L floor — respiration is outpacing reaeration.'
          : 'Oxygen supply is adequate; the column stays oxidising.',
    },
    {
      key: 'organic',
      label: 'Organic Loading',
      stress: round(organic),
      weight: WEIGHTS.organic,
      value: `COD ${cod} · O&G ${oil} mg/L`,
      rationale:
        organic >= 60
          ? 'High COD and oil & grease impose a heavy oxygen demand and feed decomposition.'
          : 'Organic load is moderate; oxygen demand is manageable.',
    },
    {
      key: 'redox',
      label: 'Redox',
      stress: round(redox),
      weight: WEIGHTS.redox,
      value: doVal >= 6 ? 'Oxidising' : doVal >= 4.5 ? 'Transitional' : 'Reducing',
      modelled: true,
      rationale:
        redox >= 70
          ? 'The bottom is turning reducing — sulphate reduction and metal release begin.'
          : 'Redox potential stays oxidising to transitional.',
    },
    {
      key: 'phosphorus',
      label: 'Phosphorus Cycle',
      stress: round(phosphorus),
      weight: WEIGHTS.phosphorus,
      value: `PO₄ ${po4} mg/L`,
      rationale:
        phosphorus >= 60
          ? 'Phosphate is elevated — measured load plus internal release from anoxic sediment (Fe²⁺-bound P).'
          : 'Phosphate is contained; little internal release.',
    },
    {
      key: 'nitrogen',
      label: 'Nitrogen Cycle',
      stress: round(nitrogen),
      weight: WEIGHTS.nitrogen,
      value: `NH₄ ${nh4} mg/L`,
      rationale:
        nitrogen >= 60
          ? 'Ammonia is high — incomplete nitrification under low oxygen; a direct bloom nutrient.'
          : 'Ammonia is within a comfortable band.',
    },
    {
      key: 'buffering',
      label: 'Buffering Capacity',
      stress: round(buffering),
      weight: WEIGHTS.buffering,
      value: `pH ${ph}`,
      rationale:
        buffering >= 55
          ? 'pH is drifting down as respiration produces organic acids — buffering is under pressure.'
          : 'pH is well buffered within the 6–9 compliance band.',
    },
    {
      key: 'salinity',
      label: 'Salinity',
      stress: round(salinity),
      weight: WEIGHTS.salinity,
      value: `${sal} PSU`,
      rationale:
        salinity >= 60
          ? 'Evaporative concentration is driving high salinity and a dense bottom layer.'
          : 'Salinity is elevated but not extreme.',
    },
    {
      key: 'metals',
      label: 'Metal Mobility',
      stress: round(metals),
      weight: WEIGHTS.metals,
      value: doVal >= 4.5 ? 'Bound' : 'Mobilising',
      modelled: true,
      rationale:
        metals >= 55
          ? 'Reducing conditions mobilise Fe, Mn (and co-release bound phosphate) from sediment.'
          : 'Metals remain bound in oxidised sediment.',
    },
  ]

  return raw.map((p) => ({ ...p, contribution: round(p.stress * p.weight) }))
}

function csiForMonth(i: number): number {
  return round(processesForMonth(i).reduce((s, p) => s + p.contribution, 0))
}

function eventsForMonth(procs: ProcessScore[]): ChemEvent[] {
  const s = (k: ProcessKey) => procs.find((p) => p.key === k)!.stress
  const evts: ChemEvent[] = []
  if (s('organic') >= 60) evts.push({ id: 'organic-load', label: 'High Organic Loading', color: '#d97706', from: 'organic' })
  if (s('oxygen') >= 60) evts.push({ id: 'low-o2', label: 'Low Oxygen Event', color: '#dc2626', from: 'oxygen', pulse: true })
  if (s('redox') >= 70) evts.push({ id: 'anaerobic', label: 'Anaerobic / Sediment Release', color: '#7c3aed', from: 'redox', pulse: true })
  if (s('phosphorus') >= 55 && s('redox') >= 55) evts.push({ id: 'internal-p', label: 'Internal Nutrient Loading', color: '#0891b2', from: 'phosphorus' })
  if (s('metals') >= 55) evts.push({ id: 'metals', label: 'Metal Mobilisation', color: '#a855f7', from: 'metals' })
  if (s('buffering') >= 60) evts.push({ id: 'acid', label: 'Acidification', color: '#ea580c', from: 'buffering' })
  return evts
}

function buildAction(state: ChemState, i: number) {
  const cal = TREATMENT_CALENDAR[i]
  const stepsByLevel: Record<ChemState['level'], string[]> = {
    Critical: [
      'Run aeration + destratification at 100% to re-oxygenate the bottom',
      'Deploy enzyme / bioaugmentation to cut organic load (COD, oil & grease)',
      'Escalate to weekly sampling — add a sulphide and dissolved-metals panel',
      'Notify operator; investigate the TSE / industrial inflow source',
    ],
    High: [
      'Raise aeration to 75–100% with a night-time boost',
      'Confirm TSE nutrient (N & P) inflow controls are enforced',
      'Add sulphide + bottom-DO checks to the fortnightly round',
      'Audit organic-loading sources (grease traps, discharges)',
    ],
    Stressed: [
      'Increase circulation to keep the column oxidising',
      'Audit organic and nutrient inputs; verify grease interception',
      'Track bottom-DO and phosphate trend closely',
      'Pre-position enzyme dosing before conditions tip',
    ],
    Watch: [
      'Hold preventive enzyme dosing and aeration baseline',
      'Verify buffering (pH) stability',
      'Watch DO for the first sign of an oxygen sag',
    ],
    Stable: [
      'Maintain baseline monitoring',
      'Use the window for aeration / ultrasound servicing',
      'Confirm inflow nutrient controls remain in place',
    ],
  }
  return {
    priority: `${cal?.risk ?? state.level} risk · ${cal?.phase ?? ''}`.trim(),
    phase: cal?.phase ?? '',
    enzyme: cal?.enzyme ?? '',
    aeration: cal?.aeration ?? '',
    steps: stepsByLevel[state.level],
  }
}

/** Full chemistry read-out for a month index (0 = January). */
export function analyzeChemistry(monthIndex: number): ChemistryIntelligence {
  const i = ((monthIndex % 12) + 12) % 12
  const processes = processesForMonth(i)
  const csi = round(processes.reduce((s, p) => s + p.contribution, 0))
  const state = classify(csi)

  const dominant = [...processes].sort((a, b) => b.contribution - a.contribution)[0]
  const events = eventsForMonth(processes)

  const window = [i - 1, i, i + 1, i + 2].map((m) => {
    const mi = ((m % 12) + 12) % 12
    const c = csiForMonth(mi)
    return {
      monthIndex: mi,
      monthName: MONTH_NAMES[mi],
      csi: c,
      state: classify(c),
      kind: mi === i ? 'current' : m < i ? 'past' : 'forecast',
    } as ChemTrajectoryPoint
  })

  const prev = csiForMonth(((i - 1) % 12 + 12) % 12)
  const delta = round(csi - prev)
  const trend: ChemistryIntelligence['trend'] = delta > 5 ? 'rising' : delta < -5 ? 'falling' : 'stable'

  const forecastPeak = Math.max(...window.filter((w) => w.kind === 'forecast').map((w) => w.csi))
  const peakPoint = window.find((w) => w.csi === forecastPeak && w.kind === 'forecast')

  const trendWord = trend === 'rising' ? 'climbing' : trend === 'falling' ? 'easing' : 'holding'
  const headline = `Chemical stress is ${trendWord} in ${MONTH_NAMES[i]} — ${state.level} (CSI ${csi}${
    delta === 0 ? '' : delta > 0 ? `, ▲${delta}` : `, ▼${Math.abs(delta)}`
  }).`

  const eventLine = events.length ? ` Active: ${events.map((e) => e.label).join(', ')}.` : ''
  const cause = `${dominant.label} is the leading stress (${dominant.value}). ${dominant.rationale}${eventLine}`

  const outlook =
    forecastPeak > csi
      ? `Stress is projected to keep rising — peaking around ${peakPoint?.monthName} at CSI ${forecastPeak} (${peakPoint?.state.level}). Re-oxygenate ahead of the curve.`
      : forecastPeak < csi - 3
      ? `Stress is projected to ease over the next two months (toward CSI ${forecastPeak}). Sustain aeration through the decline.`
      : `Stress is projected to hold near its current level over the next two months. Maintain the active regime.`

  return {
    monthIndex: i,
    monthName: MONTH_NAMES[i],
    csi,
    state,
    processes,
    dominant,
    events,
    trajectory: window,
    delta,
    trend,
    headline,
    cause,
    outlook,
    action: buildAction(state, i),
  }
}

export function annualCsi(): number[] {
  return MONTH_NAMES.map((_, i) => csiForMonth(i))
}

export { classify as classifyCsi }
