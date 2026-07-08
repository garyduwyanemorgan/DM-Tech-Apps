// ─────────────────────────────────────────────────────────────────────────────
// Ecology Loop — Intelligence Engine  (System Intelligence Engine, green loop)
//
// The biological RESPONSE of the lagoon presented as one living system, and the
// SIE's four questions answered for any month:
//
//     What is changing?   →  trend + headline
//     Why is it changing? →  dominant (root-cause) process
//     What happens next?  →  3-month forward trajectory
//     What action?        →  operational response
//
// Encodes the bloom/oxygen response chain:
//   Productivity (light + warmth + nutrients) → algal biomass → night
//   respiration → oxygen crash → fish stress, and cyanobacteria dominance.
//
// Deterministic, transparent: pure functions over the reference constants.
// The stress-colour scale is shared with the Chemistry loop.
// ─────────────────────────────────────────────────────────────────────────────

import { MONTH_NAMES, MONTHLY_DATA, SOLAR_IRRADIANCE, TREATMENT_CALENDAR } from '../constants'
import { stressColor } from './chemistryIntelligence'

export type EcoKey =
  | 'algae'
  | 'plankton'
  | 'productivity'
  | 'respiration'
  | 'fish'
  | 'bacteria'
  | 'biofilms'
  | 'plants'

export interface EcoProcess {
  key: EcoKey
  label: string
  /** 0–100 ecological stress (100 = bloom-dominated / ecosystem under strain) */
  stress: number
  weight: number
  contribution: number
  value: string
  rationale: string
  modelled?: boolean
}

export interface EcoState {
  level: 'Stable' | 'Watch' | 'Stressed' | 'High' | 'Critical'
  color: string
  bg: string
  border: string
}

export interface EcoEvent {
  id: string
  label: string
  color: string
  from: EcoKey
  pulse?: boolean
}

export interface EcoTrajectoryPoint {
  monthIndex: number
  monthName: string
  esi: number
  state: EcoState
  kind: 'past' | 'current' | 'forecast'
}

export interface EcologyIntelligence {
  monthIndex: number
  monthName: string
  /** Ecological Stress Index, 0–100 */
  esi: number
  state: EcoState
  processes: EcoProcess[]
  dominant: EcoProcess
  events: EcoEvent[]
  trajectory: EcoTrajectoryPoint[]
  delta: number
  trend: 'rising' | 'falling' | 'stable'
  headline: string
  cause: string
  outlook: string
  action: {
    priority: string
    phase: string
    enzyme: string
    ultrasound: string
    steps: string[]
  }
}

export const ECO_LOOP_COLOR = '#22c55e' // green — Ecology loop identity (SIE)

// ── helpers ──────────────────────────────────────────────────────────────────
const clamp = (v: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v))
const round = (v: number) => Math.round(v * 10) / 10
const norm = (v: number, lo: number, hi: number) => clamp(((v - lo) / (hi - lo)) * 100)

function classify(esi: number): EcoState {
  if (esi >= 80) return { level: 'Critical', color: '#9C0006', bg: '#FFF0F0', border: '#fecaca' }
  if (esi >= 60) return { level: 'High', color: '#c2410c', bg: '#FFF7ED', border: '#fed7aa' }
  if (esi >= 40) return { level: 'Stressed', color: '#a16207', bg: '#FEFCE8', border: '#fde68a' }
  if (esi >= 20) return { level: 'Watch', color: '#1d4ed8', bg: '#EFF6FF', border: '#bfdbfe' }
  return { level: 'Stable', color: '#15803d', bg: '#F0FDF4', border: '#bbf7d0' }
}

const WEIGHTS: Record<EcoKey, number> = {
  algae: 0.2,
  productivity: 0.14,
  respiration: 0.14,
  fish: 0.12,
  plankton: 0.12,
  bacteria: 0.1,
  biofilms: 0.09,
  plants: 0.09,
}

function processesForMonth(i: number): EcoProcess[] {
  const chla = MONTHLY_DATA.chla[i]
  const phyco = MONTHLY_DATA.phycocyanin[i]
  const ecoli = MONTHLY_DATA.ecoli[i]
  const coli = MONTHLY_DATA.coliforms[i]
  const doVal = MONTHLY_DATA.do[i]
  const temp = MONTHLY_DATA.water_temp[i]
  const turb = MONTHLY_DATA.turbidity[i]
  const cod = MONTHLY_DATA.cod[i]
  const nh4 = MONTHLY_DATA.ammonia[i]
  const solar = SOLAR_IRRADIANCE[i]

  const oxygenStress = clamp(((7 - doVal) / 3) * 100)
  const tempNorm = norm(temp, 22, 33)
  const heatStress = clamp(((temp - 28) / (34 - 28)) * 100)

  // biomass & bloom
  const algae = clamp(0.5 * (chla / 50) * 100 + 0.5 * (phyco / 350) * 100)
  const plankton = clamp(((chla / 50) * 100 + (turb / 75) * 100) / 2)
  const productivity = clamp((norm(solar, 4, 7.2) + tempNorm + (chla / 50) * 100) / 3)
  const respiration = clamp((tempNorm + (cod / 50) * 100 + (chla / 50) * 100) / 3)
  const fish = clamp((oxygenStress + heatStress + (nh4 / 5) * 100) / 3)
  const bacteria = clamp(((ecoli / 200) * 100 + (coli / 1000) * 100) / 2)
  const biofilms = clamp((tempNorm + (cod / 50) * 100) / 2)
  const plants = clamp((turb / 75) * 100)

  const raw: Omit<EcoProcess, 'contribution'>[] = [
    {
      key: 'algae',
      label: 'Algae',
      stress: round(algae),
      weight: WEIGHTS.algae,
      value: `Chl-a ${chla} · Phyco ${phyco} µg/L`,
      rationale:
        algae >= 60
          ? 'Chlorophyll-a and phycocyanin are high — a cyanobacteria-led bloom is under way.'
          : 'Algal biomass is low; no bloom signal.',
    },
    {
      key: 'productivity',
      label: 'Primary Productivity',
      stress: round(productivity),
      weight: WEIGHTS.productivity,
      value: `Solar ${solar} · ${temp}°C`,
      rationale:
        productivity >= 60
          ? 'Strong light and warmth drive photosynthesis faster than the system can absorb it.'
          : 'Photosynthetic production is moderate.',
    },
    {
      key: 'respiration',
      label: 'Respiration',
      stress: round(respiration),
      weight: WEIGHTS.respiration,
      value: `${temp}°C · COD ${cod}`,
      rationale:
        respiration >= 60
          ? 'High biomass and warmth push night-time oxygen demand up — the source of dawn oxygen sags.'
          : 'Community respiration is manageable.',
    },
    {
      key: 'fish',
      label: 'Fish',
      stress: round(fish),
      weight: WEIGHTS.fish,
      value: `DO ${doVal} · ${temp}°C`,
      rationale:
        fish >= 60
          ? 'Low oxygen, heat and ammonia together put fish under acute stress — kill risk rises.'
          : 'Conditions are tolerable for fish.',
    },
    {
      key: 'plankton',
      label: 'Surface Plankton',
      stress: round(plankton),
      weight: WEIGHTS.plankton,
      value: `Chl-a ${chla} · Turb ${turb}`,
      rationale:
        plankton >= 60
          ? 'Dense surface plankton and turbidity shade the water column.'
          : 'Plankton load is moderate.',
    },
    {
      key: 'bacteria',
      label: 'Bacteria',
      stress: round(bacteria),
      weight: WEIGHTS.bacteria,
      value: `E.coli ${ecoli} · Coli ${coli}`,
      rationale:
        bacteria >= 55
          ? 'Faecal-indicator bacteria are elevated — a pathogen and decomposition signal.'
          : 'Bacterial indicators are within a comfortable band.',
    },
    {
      key: 'biofilms',
      label: 'Biofilms',
      stress: round(biofilms),
      weight: WEIGHTS.biofilms,
      value: 'Warmth + organics',
      modelled: true,
      rationale:
        biofilms >= 60
          ? 'Warm, organic-rich water favours heavy biofilm growth on surfaces and sediment.'
          : 'Biofilm growth is modest.',
    },
    {
      key: 'plants',
      label: 'Aquatic Plants',
      stress: round(plants),
      weight: WEIGHTS.plants,
      value: `Turbidity ${turb} NTU`,
      modelled: true,
      rationale:
        plants >= 60
          ? 'Bloom-driven turbidity shades submerged plants — light limitation and die-back.'
          : 'Light reaches submerged plants adequately.',
    },
  ]

  return raw.map((p) => ({ ...p, contribution: round(p.stress * p.weight) }))
}

function esiForMonth(i: number): number {
  return round(processesForMonth(i).reduce((s, p) => s + p.contribution, 0))
}

function eventsForMonth(procs: EcoProcess[]): EcoEvent[] {
  const s = (k: EcoKey) => procs.find((p) => p.key === k)!.stress
  const evts: EcoEvent[] = []
  if (s('algae') >= 60) evts.push({ id: 'bloom', label: 'Algae Bloom', color: '#16a34a', from: 'algae', pulse: true })
  if (s('algae') >= 70) evts.push({ id: 'cyano', label: 'Cyanobacteria Dominance', color: '#dc2626', from: 'algae', pulse: true })
  if (s('respiration') >= 65) evts.push({ id: 'anoxia', label: 'Night Oxygen Crash', color: '#7c3aed', from: 'respiration', pulse: true })
  if (s('fish') >= 65) evts.push({ id: 'fishkill', label: 'Fish Kill Risk', color: '#ea580c', from: 'fish' })
  if (s('bacteria') >= 55) evts.push({ id: 'pathogen', label: 'Pathogen Load', color: '#0891b2', from: 'bacteria' })
  if (s('plants') >= 65) evts.push({ id: 'plantloss', label: 'Aquatic Plant Loss', color: '#65a30d', from: 'plants' })
  return evts
}

function buildAction(state: EcoState, i: number) {
  const cal = TREATMENT_CALENDAR[i]
  const stepsByLevel: Record<EcoState['level'], string[]> = {
    Critical: [
      'Skim / harvest surface bloom mat where accessible',
      'Run aeration at 100% to prevent a fish kill; watch the dawn oxygen sag',
      'Apply cyanobacteria-targeted ultrasound across all units',
      'Escalate to weekly biomass + cyanotoxin sampling; notify operator',
    ],
    High: [
      'Increase ultrasound cyano-targeting and rotation',
      'Dose protease-heavy enzyme blend against cyanobacteria',
      'Boost aeration and monitor diel (day/night) DO swing',
      'Sample chlorophyll-a and phycocyanin fortnightly',
    ],
    Stressed: [
      'Pre-position bloom controls before biomass tips over',
      'Increase circulation to break the surface lens',
      'Track chlorophyll-a trend and bottom DO',
      'Verify aeration and ultrasound coverage',
    ],
    Watch: [
      'Hold preventive enzyme dosing',
      'Watch chlorophyll-a as temperature crosses into the cyano band',
      'Confirm aeration baseline',
    ],
    Stable: [
      'Maintain baseline biomass monitoring',
      'Use the window for biodiversity / plant surveys',
      'Service ultrasound and aeration units',
    ],
  }
  return {
    priority: `${cal?.risk ?? state.level} risk · ${cal?.phase ?? ''}`.trim(),
    phase: cal?.phase ?? '',
    enzyme: cal?.enzyme ?? '',
    ultrasound: cal?.ultrasound ?? '',
    steps: stepsByLevel[state.level],
  }
}

/** Full ecology read-out for a month index (0 = January). */
export function analyzeEcology(monthIndex: number): EcologyIntelligence {
  const i = ((monthIndex % 12) + 12) % 12
  const processes = processesForMonth(i)
  const esi = round(processes.reduce((s, p) => s + p.contribution, 0))
  const state = classify(esi)

  const dominant = [...processes].sort((a, b) => b.contribution - a.contribution)[0]
  const events = eventsForMonth(processes)

  const window = [i - 1, i, i + 1, i + 2].map((m) => {
    const mi = ((m % 12) + 12) % 12
    const e = esiForMonth(mi)
    return {
      monthIndex: mi,
      monthName: MONTH_NAMES[mi],
      esi: e,
      state: classify(e),
      kind: mi === i ? 'current' : m < i ? 'past' : 'forecast',
    } as EcoTrajectoryPoint
  })

  const prev = esiForMonth(((i - 1) % 12 + 12) % 12)
  const delta = round(esi - prev)
  const trend: EcologyIntelligence['trend'] = delta > 5 ? 'rising' : delta < -5 ? 'falling' : 'stable'

  const forecastPeak = Math.max(...window.filter((w) => w.kind === 'forecast').map((w) => w.esi))
  const peakPoint = window.find((w) => w.esi === forecastPeak && w.kind === 'forecast')

  const trendWord = trend === 'rising' ? 'climbing' : trend === 'falling' ? 'easing' : 'holding'
  const headline = `Ecological stress is ${trendWord} in ${MONTH_NAMES[i]} — ${state.level} (ESI ${esi}${
    delta === 0 ? '' : delta > 0 ? `, ▲${delta}` : `, ▼${Math.abs(delta)}`
  }).`

  const eventLine = events.length ? ` Active: ${events.map((e) => e.label).join(', ')}.` : ''
  const cause = `${dominant.label} is the leading pressure (${dominant.value}). ${dominant.rationale}${eventLine}`

  const outlook =
    forecastPeak > esi
      ? `Stress is projected to keep rising — peaking around ${peakPoint?.monthName} at ESI ${forecastPeak} (${peakPoint?.state.level}). Get bloom controls ahead of the curve.`
      : forecastPeak < esi - 3
      ? `Stress is projected to ease over the next two months (toward ESI ${forecastPeak}). Sustain controls through the decline — watch for a bloom crash.`
      : `Stress is projected to hold near its current level over the next two months. Maintain the active regime.`

  return {
    monthIndex: i,
    monthName: MONTH_NAMES[i],
    esi,
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

export function annualEsi(): number[] {
  return MONTH_NAMES.map((_, i) => esiForMonth(i))
}

export { classify as classifyEsi, stressColor }
