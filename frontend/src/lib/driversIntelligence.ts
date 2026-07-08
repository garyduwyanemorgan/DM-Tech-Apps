// ─────────────────────────────────────────────────────────────────────────────
// Environmental Drivers — Intelligence Engine
//
// A deterministic, transparent model that fuses the four environmental drivers
// (temperature, nutrients, solar radiation, salinity/stratification) into a
// single Bloom Pressure Index (BPI) and answers the System Intelligence Engine's
// four questions for any month:
//
//     What is changing?   →  trend + headline
//     Why is it changing? →  dominant (root-cause) driver
//     What happens next?  →  3-month forward trajectory
//     What action?        →  operational recommendation
//
// The model is intentionally non-complex: pure functions over the existing
// reference constants, no ML, no external calls. Every score is explainable.
// ─────────────────────────────────────────────────────────────────────────────

import {
  MONTH_NAMES,
  MONTHLY_DATA,
  SOLAR_IRRADIANCE,
  TREATMENT_CALENDAR,
} from '../constants'

export type DriverKey = 'temperature' | 'nutrients' | 'solar' | 'stratification'

export interface DriverScore {
  key: DriverKey
  label: string
  /** 0–100: favourability of this driver to a cyanobacteria bloom */
  score: number
  weight: number
  /** score × weight — the driver's share of total bloom pressure */
  contribution: number
  /** human-readable current value, e.g. "33°C" */
  value: string
  /** permanent identity colour (SIE loop-style) */
  color: string
  rationale: string
}

export interface DriverState {
  level: 'Dormant' | 'Watch' | 'Elevated' | 'High' | 'Critical'
  color: string
  bg: string
  border: string
}

export interface TrajectoryPoint {
  monthIndex: number
  monthName: string
  bpi: number
  state: DriverState
  kind: 'past' | 'current' | 'forecast'
}

export interface MonthIntelligence {
  monthIndex: number
  monthName: string
  /** Bloom Pressure Index, 0–100 */
  bpi: number
  state: DriverState
  drivers: DriverScore[]
  /** highest-contribution driver = root cause */
  dominant: DriverScore
  /** lowest-score driver = the brake currently holding pressure down */
  limiting: DriverScore
  trajectory: TrajectoryPoint[]
  /** BPI change vs previous month */
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

// ── helpers ──────────────────────────────────────────────────────────────────

const clamp = (v: number, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v))
const norm = (v: number, lo: number, hi: number) => clamp(((v - lo) / (hi - lo)) * 100)
const round = (v: number) => Math.round(v * 10) / 10

// ── driver scoring (0–100, higher = more favourable to cyanobacteria) ─────────

/** Solar: cyanobacteria are light-hungry; risk climbs steeply past ~6 kWh/m²/day. */
function solarScore(irradiance: number): number {
  return norm(irradiance, 4.0, 7.2)
}

/** Temperature: Gaussian around the cyanobacteria thermal optimum (30.6 °C). */
function tempScore(temp: number): number {
  const OPT = 30.6
  const SIGMA = 4.5
  return clamp(100 * Math.exp(-((temp - OPT) ** 2) / (2 * SIGMA ** 2)))
}

/** Nutrients: N & P fuel. Mean of normalised phosphate and ammonia loading. */
function nutrientScore(phosphate: number, ammonia: number): number {
  return (norm(phosphate, 1.5, 4.0) + norm(ammonia, 1.2, 3.5)) / 2
}

/**
 * Stratification: the enabling condition. Dense evaporative brine below +
 * warm surface = stable freshwater lens where cyanobacteria incubate.
 * Weighted blend of salinity (density contrast) and temperature (thermal).
 */
function stratificationScore(salinity: number, temp: number): number {
  return 0.6 * norm(salinity, 42, 55) + 0.4 * norm(temp, 22, 33)
}

const WEIGHTS: Record<DriverKey, number> = {
  temperature: 0.3,
  nutrients: 0.3,
  solar: 0.2,
  stratification: 0.2,
}

const IDENTITY: Record<DriverKey, string> = {
  temperature: '#ef4444', // heat
  nutrients: '#f59e0b', // amber — chemistry fuel
  solar: '#eab308', // sun
  stratification: '#3b82f6', // hydrology blue
}

// ── state classification ─────────────────────────────────────────────────────

function classify(bpi: number): DriverState {
  if (bpi >= 80) return { level: 'Critical', color: '#9C0006', bg: '#FFF0F0', border: '#fecaca' }
  if (bpi >= 60) return { level: 'High', color: '#c2410c', bg: '#FFF7ED', border: '#fed7aa' }
  if (bpi >= 40) return { level: 'Elevated', color: '#a16207', bg: '#FEFCE8', border: '#fde68a' }
  if (bpi >= 20) return { level: 'Watch', color: '#1d4ed8', bg: '#EFF6FF', border: '#bfdbfe' }
  return { level: 'Dormant', color: '#15803d', bg: '#F0FDF4', border: '#bbf7d0' }
}

// ── core computation ─────────────────────────────────────────────────────────

function driversForMonth(i: number): DriverScore[] {
  const temp = MONTHLY_DATA.water_temp[i]
  const phosphate = MONTHLY_DATA.phosphate[i]
  const ammonia = MONTHLY_DATA.ammonia[i]
  const salinity = MONTHLY_DATA.salinity[i]
  const solar = SOLAR_IRRADIANCE[i]

  const raw: Omit<DriverScore, 'contribution'>[] = [
    {
      key: 'temperature',
      label: 'Temperature',
      score: round(tempScore(temp)),
      weight: WEIGHTS.temperature,
      value: `${temp}°C`,
      color: IDENTITY.temperature,
      rationale:
        temp >= 29
          ? 'Water sits at the cyanobacteria thermal optimum (30.6 °C) while suppressing competitors.'
          : temp >= 25
          ? 'Warming through the chlorophyte band — approaching cyanobacteria territory.'
          : 'Too cool for cyanobacteria; diatoms and green algae dominate.',
    },
    {
      key: 'nutrients',
      label: 'Nutrients (N & P)',
      score: round(nutrientScore(phosphate, ammonia)),
      weight: WEIGHTS.nutrients,
      value: `PO₄ ${phosphate} · NH₄ ${ammonia} mg/L`,
      color: IDENTITY.nutrients,
      rationale:
        phosphate >= 3
          ? 'Phosphate and ammonia loading is high — abundant fuel for a bloom (TSE-driven).'
          : phosphate >= 2
          ? 'Nutrient loading rising as TSE inflow and internal sediment release increase.'
          : 'Nutrient loading is low; growth is fuel-limited.',
    },
    {
      key: 'solar',
      label: 'Solar Radiation',
      score: round(solarScore(solar)),
      weight: WEIGHTS.solar,
      value: `${solar} kWh/m²/day`,
      color: IDENTITY.solar,
      rationale:
        solar >= 6.0
          ? 'Irradiance above the 6.0 high-growth threshold — ample photosynthetic energy.'
          : 'Irradiance below the high-growth threshold; energy supply is moderate.',
    },
    {
      key: 'stratification',
      label: 'Salinity / Stratification',
      score: round(stratificationScore(salinity, temp)),
      weight: WEIGHTS.stratification,
      value: `${salinity} PSU`,
      color: IDENTITY.stratification,
      rationale:
        salinity >= 50
          ? 'Strong evaporative brine below a warm surface — a stable freshwater-lens incubator.'
          : salinity >= 46
          ? 'Density contrast building; stratification risk climbing with evaporation.'
          : 'Weak stratification; the water column mixes readily.',
    },
  ]

  return raw.map((d) => ({ ...d, contribution: round(d.score * d.weight) }))
}

function bpiForMonth(i: number): number {
  return round(driversForMonth(i).reduce((sum, d) => sum + d.contribution, 0))
}

function buildAction(state: DriverState, i: number) {
  const cal = TREATMENT_CALENDAR[i]
  const stepsByLevel: Record<DriverState['level'], string[]> = {
    Critical: [
      'Run aeration / destratification at 100% capacity',
      'Deploy species-specific (protease-heavy) enzyme blend',
      'Increase sampling to weekly; watch for a bloom crash',
      'Notify operator and put emergency aeration on standby',
    ],
    High: [
      'Raise aeration to 75–100% with a night-time boost',
      'Confirm TSE phosphate inflow controls are enforced',
      'Move to fortnightly species-specific enzyme dosing',
      'Sample fortnightly and track Chl-a / phycocyanin',
    ],
    Elevated: [
      'Shift enzyme programme to maintenance dosing',
      'Increase circulation to disrupt the surface lens',
      'Audit TSE and landscape-runoff nutrient load',
      'Tighten monitoring as temperature crosses 26 °C',
    ],
    Watch: [
      'Hold preventive enzyme dosing',
      'Verify aeration baseline and destratification cover',
      'Begin adaptive ultrasound frequency rotation',
      'Watch for the temperature crossing into the cyano band',
    ],
    Dormant: [
      'Use the low-risk window for pre-load enzyme dosing',
      'Service aeration and ultrasound units',
      'Pellet / remove accumulated sludge where accessible',
      'Plan the coming season’s treatment calendar',
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

/**
 * Full intelligence read-out for a given month index (0 = January).
 */
export function analyzeMonth(monthIndex: number): MonthIntelligence {
  const i = ((monthIndex % 12) + 12) % 12
  const drivers = driversForMonth(i)
  const bpi = round(drivers.reduce((sum, d) => sum + d.contribution, 0))
  const state = classify(bpi)

  const sorted = [...drivers].sort((a, b) => b.contribution - a.contribution)
  const dominant = sorted[0]
  const limiting = [...drivers].sort((a, b) => a.score - b.score)[0]

  // Trajectory window: previous month → two months ahead
  const window = [i - 1, i, i + 1, i + 2].map((m) => {
    const mi = ((m % 12) + 12) % 12
    const b = bpiForMonth(mi)
    return {
      monthIndex: mi,
      monthName: MONTH_NAMES[mi],
      bpi: b,
      state: classify(b),
      kind: mi === i ? 'current' : m < i ? 'past' : 'forecast',
    } as TrajectoryPoint
  })

  const prevBpi = bpiForMonth(((i - 1) % 12 + 12) % 12)
  const delta = round(bpi - prevBpi)
  const trend: MonthIntelligence['trend'] = delta > 5 ? 'rising' : delta < -5 ? 'falling' : 'stable'

  const forecastPeak = Math.max(...window.filter((w) => w.kind === 'forecast').map((w) => w.bpi))
  const peakPoint = window.find((w) => w.bpi === forecastPeak && w.kind === 'forecast')

  const trendWord = trend === 'rising' ? 'climbing' : trend === 'falling' ? 'easing' : 'holding'
  const headline = `Bloom pressure is ${trendWord} in ${MONTH_NAMES[i]} — ${state.level} (BPI ${bpi}${
    delta === 0 ? '' : delta > 0 ? `, ▲${delta}` : `, ▼${Math.abs(delta)}`
  }).`

  const cause = `${dominant.label} is the leading pressure (${dominant.value}). ${dominant.rationale} The ${limiting.label.toLowerCase()} driver is currently the brake holding pressure down.`

  const outlook =
    forecastPeak > bpi
      ? `Pressure is projected to keep rising — peaking around ${peakPoint?.monthName} at BPI ${forecastPeak} (${peakPoint?.state.level}). Act ahead of the curve.`
      : forecastPeak < bpi - 3
      ? `Pressure is projected to ease over the next two months (toward BPI ${forecastPeak}). Sustain controls through the decline to avoid a rebound.`
      : `Pressure is projected to hold near its current level over the next two months. Maintain the active regime.`

  return {
    monthIndex: i,
    monthName: MONTH_NAMES[i],
    bpi,
    state,
    drivers,
    dominant,
    limiting,
    trajectory: window,
    delta,
    trend,
    headline,
    cause,
    outlook,
    action: buildAction(state, i),
  }
}

/** BPI for every month — handy for a full-year context strip. */
export function annualBpi(): number[] {
  return MONTH_NAMES.map((_, i) => bpiForMonth(i))
}

export { classify as classifyBpi }
