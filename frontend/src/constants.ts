// All static reference data ported from Python core/constants.py and data/sample_data.py

import { ALERT } from './lib/tokens'

export const MONTH_NAMES = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December',
]

export const COMPLIANCE_LIMITS: Record<string, { parameter: string; unit: string; min: number|null; max: number|null; display: string }> = {
  ph:              { parameter: 'pH',                 unit: 'pH Units',    min: 6.0,  max: 9.0,   display: '6.0 – 9.0' },
  do:              { parameter: 'Dissolved Oxygen',   unit: 'mg/L',        min: 4.0,  max: null,  display: '> 4.0' },
  tss:             { parameter: 'TSS',                unit: 'mg/L',        min: null, max: 50,    display: '< 50' },
  turbidity:       { parameter: 'Turbidity',          unit: 'NTU',         min: null, max: 75,    display: '< 75' },
  cod:             { parameter: 'COD',                unit: 'mg/L',        min: null, max: 50,    display: '< 50' },
  ammonia:         { parameter: 'Ammonia (as N)',     unit: 'mg/L',        min: null, max: 5.0,   display: '< 5.0' },
  phosphate:       { parameter: 'Total Phosphate',    unit: 'mg/L',        min: null, max: 5.0,   display: '< 5.0' },
  oil_grease:      { parameter: 'Oils & Grease',      unit: 'mg/L',        min: null, max: 10,    display: '< 10' },
  ecoli:           { parameter: 'E. coli',            unit: 'CFU/100mL',   min: null, max: 200,   display: '< 200' },
  total_coliforms: { parameter: 'Total Coliforms',    unit: 'CFU/100mL',   min: null, max: 1000,  display: '< 1000' },
}

// Alert-level visuals derive from the canonical design-system tokens
// (lib/tokens.ts ALERT) so the 4-level scale has one source of truth.
export const ALERT_COLORS: Record<number, string> = {
  1: ALERT[1].color, 2: ALERT[2].color, 3: ALERT[3].color, 4: ALERT[4].color,
}

export const ALERT_LABELS: Record<number, string> = {
  1: ALERT[1].label, 2: ALERT[2].label, 3: ALERT[3].label, 4: ALERT[4].label,
}

/** Pastel card background per alert level (badge/banner surfaces). */
export const ALERT_BG: Record<number, string> = {
  1: ALERT[1].bg, 2: ALERT[2].bg, 3: ALERT[3].bg, 4: ALERT[4].bg,
}

/** Text color paired with ALERT_BG per alert level. */
export const ALERT_FG: Record<number, string> = {
  1: ALERT[1].fg, 2: ALERT[2].fg, 3: ALERT[3].fg, 4: ALERT[4].fg,
}

export const ALERT_THRESHOLDS: Record<number, { bloomRange: string; chla: string; doVal: string; phyco: string; temp: string; monitoring: string; reporting: string }> = {
  1: { bloomRange: '0–25%',   chla: '< 10 µg/L',    doVal: '> 5 mg/L',  phyco: '< 50 µg/L',    temp: '< 27°C', monitoring: 'Weekly',    reporting: 'Weekly report' },
  2: { bloomRange: '25–50%',  chla: '10–30 rising', doVal: '< 4 mg/L',  phyco: '> 50 µg/L',    temp: '> 28°C', monitoring: 'Daily',     reporting: 'Daily dashboard' },
  3: { bloomRange: '50–75%',  chla: '> 30 µg/L',   doVal: '< 3 mg/L',  phyco: '> 200 µg/L',   temp: 'Any',    monitoring: 'Hourly',    reporting: 'Real-time alerts' },
  4: { bloomRange: '75–100%', chla: '> 75 µg/L',   doVal: '< 2 mg/L',  phyco: 'Visible mat',  temp: 'Any',    monitoring: '10-min',    reporting: 'Immediate alert' },
}

export const TREATMENT_ACTIONS: Record<number, { enzyme: string; aeration: string; ultrasound: string; monitoring: string; doNot: string }> = {
  1: {
    enzyme: 'Monthly maintenance dose (pelletised sludge)',
    aeration: 'Low-intensity continuous; Night boost sunset–sunrise 50%',
    ultrasound: 'Preventive mode, adaptive low-frequency',
    monitoring: 'Weekly manual sampling; 10-min sensor cycle',
    doNot: '—',
  },
  2: {
    enzyme: 'Fortnightly liquid dosing; Protease-heavy if phycocyanin rising',
    aeration: '75% capacity; Night boost 2hr before sunset; Target DO ≥ 4',
    ultrasound: 'Increase freq rotation; Cyano-targeted if phycocyanin rising',
    monitoring: '2×/week manual N, P, species; Daily auto-reports',
    doNot: '—',
  },
  3: {
    enzyme: 'Pulse dose 3× intensity; Species-specific blend; Continuous 48hr',
    aeration: '100% continuous; Emergency aerators; Destratification protocol',
    ultrasound: 'Maximum interactive programme; All units full power',
    monitoring: 'Continuous auto-analysis; Hourly trends; Toxin screening',
    doNot: 'DO NOT DEPLOY ALGICIDE',
  },
  4: {
    enzyme: 'Daily full-spectrum cocktail; Reinoculate bacteria if DO killed population',
    aeration: 'Emergency protocol; All capacity + contingency; DO must stay > 2',
    ultrasound: 'Continue maximum; Shift to aeration if dinoflagellates',
    monitoring: '10-min reporting; Toxin analysis; Independent lab verification',
    doNot: 'DO NOT DEPLOY ALGICIDE',
  },
}

export const SEASONAL_PHASES = [
  { name: 'Phase 1: Pre-load', months: [1,2,3],     color: '#5dade2', objective: 'Establish bacterial populations before heat' },
  { name: 'Phase 2: Ramp',     months: [4,5],        color: '#f4d03f', objective: 'Transition to active bloom prevention' },
  { name: 'Phase 3: Peak',     months: [6,7,8,9],   color: '#e74c3c', objective: 'Continuous bloom suppression; compliance' },
  { name: 'Phase 4: Recovery', months: [10,11,12],  color: '#27ae60', objective: 'System recovery; Sludge management; Planning' },
]

export const SPECIES_PROFILES = [
  { category: 'HIGH THREAT', group: 'Dinoflagellates',    keySpecies: 'Cochlodinium, Chattonella, Noctiluca, Blixaea', salinity: '35–45 PSU', temp: '25–33°C', toxin: 'Ichthyotoxic (fish-killing)',    threat: 'HIGH',     season: 'Year-round, peak summer', treatment: 'Aeration + enzymes',           color: '#e74c3c' },
  { category: 'HIGH THREAT', group: 'Cyanobacteria',      keySpecies: 'Microcystis, Oscillatoria, Lyngbya',           salinity: '0–15 PSU',  temp: '28–35°C', toxin: 'Hepatotoxic (microcystins)',    threat: 'HIGH',     season: 'Summer (TSE lens)',       treatment: 'Ultrasound + enzymes',         color: '#c0392b' },
  { category: 'MODERATE',    group: 'Green Macroalgae',   keySpecies: 'Ulva, Chaetomorpha, Cladophora',               salinity: '5–50+ PSU', temp: 'Broad',   toxin: 'Non-toxic (aesthetic/odour/BOD)',threat: 'MODERATE', season: 'Year-round',              treatment: 'Enzyme removal',               color: '#f39c12' },
  { category: 'MODERATE',    group: 'Diatoms',            keySpecies: 'Pseudo-nitzschia, Chaetoceros, Skeletonema',   salinity: '35–40 PSU', temp: '15–25°C', toxin: 'Domoic acid (some)',            threat: 'MODERATE', season: 'Dec–Mar',                 treatment: 'Seasonal monitoring',          color: '#e67e22' },
  { category: 'SPECIALIST',  group: 'Hypersaline Green',  keySpecies: 'Dunaliella salina',                            salinity: '35–200+ PSU',temp: 'Broad',  toxin: 'None (indicator)',              threat: 'LOW',      season: 'When hypersaline',        treatment: 'Indicator of poor exchange',   color: '#3498db' },
  { category: 'SPECIALIST',  group: 'Benthic Cyano Mats', keySpecies: 'Lyngbya, Phormidium',                          salinity: '35–60 PSU', temp: 'Broad',   toxin: 'Variable',                     threat: 'LOW',      season: 'Year-round (bottom)',     treatment: 'Sludge management',            color: '#2980b9' },
]

export const NUTRIENT_SOURCES = [
  { rank: 1, source: 'Treated Sewage Effluent (TSE)', contribution: 'DOMINANT',   controllability: 'HIGH',   monitoring: 'Inflow meters + lab analysis', mechanism: 'Residual N & P; DM standard 25 mg PO₄/L' },
  { rank: 2, source: 'Landscape Irrigation Runoff',   contribution: 'Significant', controllability: 'MEDIUM', monitoring: 'Drain sampling',               mechanism: 'TSE nutrients + landscape fertiliser' },
  { rank: 3, source: 'Greywater / Detergent Phosphates', contribution: 'Moderate', controllability: 'HIGH',  monitoring: 'Source auditing',              mechanism: 'Phosphate-containing detergents common' },
  { rank: 4, source: 'Atmospheric Deposition (Dust)', contribution: 'Variable',    controllability: 'NONE',   monitoring: 'Met forecast; Dust index API', mechanism: 'Dust delivers Fe, N, P; Gulf is N-limited' },
  { rank: 5, source: 'Internal Sediment Loading',     contribution: '30–60% of total P', controllability: 'MEDIUM', monitoring: 'Sediment cores; Bottom DO',mechanism: 'Anoxic sediment releases Fe²⁺-bound PO₄' },
  { rank: 6, source: 'Groundwater Seepage',           contribution: 'Low–Moderate', controllability: 'LOW',  monitoring: 'Piezometers',                  mechanism: 'High water table + saline groundwater' },
]

export const ENZYME_TOOLKIT = [
  { enzyme: 'Cellulases',  target: 'Algal cell walls',          ph: '4–7', temp: '~50°C',  dubaiRange: 'Active at 30–38°C',           species: 'All algae with cellulose walls' },
  { enzyme: 'Proteases',   target: 'Algal proteins (~50% dry)', ph: '6–9', temp: '~37°C',  dubaiRange: 'Optimal at Dubai summer temps',species: 'Especially cyano' },
  { enzyme: 'Lipases',     target: 'Fats, oils, membranes',     ph: '7–9', temp: '30–37°C',dubaiRange: 'Optimal at Dubai water temps', species: 'All species' },
  { enzyme: 'Amylases',    target: 'Starch, glycogen',          ph: '5–8', temp: '~37°C',  dubaiRange: 'Active in Dubai conditions',   species: 'Green algae especially' },
]

export const BACTERIAL_CONSORTIUM = [
  { genus: 'Bacillus',    species: 'B. altitudinis, B. subtilis', saltTolerance: 'Up to ~2M NaCl',      role: 'Broad enzyme production',          suitability: 'HIGH',                      sporeForming: true },
  { genus: 'Halomonas',   species: 'H. elongata',                 saltTolerance: '0–5M NaCl (halophile)',role: 'High-salinity bioremediation',     suitability: 'ESSENTIAL for 50+ PSU',     sporeForming: false },
  { genus: 'Pseudomonas', species: 'P. aeruginosa, P. fluorescens',saltTolerance: 'Moderate',            role: 'Versatile organic degradation',    suitability: 'MODERATE — lower salinity', sporeForming: false },
]

export const ML_MODELS = [
  { model: 'Random Forest', range: '1–7 days', dataNeed: '4+ years', r2: '0.78–0.88', advantage: 'Interpretable (SHAP); handles missing data', tier: 1, role: 'Near-term snapshots' },
  { model: 'XGBoost',       range: '1–7 days', dataNeed: '4+ years', r2: '0.92',       advantage: 'Speed + accuracy; Gradient boosting',         tier: 1, role: 'Near-term high accuracy' },
  { model: 'LSTM',          range: '1–30 days',dataNeed: '3+ years', r2: 'Comparable', advantage: 'Captures temporal dynamics and lag effects',   tier: 1, role: 'Temporal trajectory' },
]

export const ENSEMBLE_WEIGHTS = [
  { horizon: '1-day', rf: 70, lstm: 30, rationale: 'RF excels at near-term snapshots' },
  { horizon: '3-day', rf: 40, lstm: 60, rationale: 'LSTM captures emerging temporal patterns' },
  { horizon: '7-day', rf: 20, lstm: 80, rationale: 'LSTM dominates for trajectory prediction' },
]

export const MONTHLY_DATA = {
  ph:          [7.6, 7.5, 7.4, 7.3, 7.2, 7.1, 7.0, 7.0, 7.1, 7.2, 7.4, 7.5],
  do:          [7.2, 7.0, 6.5, 6.0, 5.5, 4.8, 4.5, 4.3, 4.5, 5.2, 6.2, 7.0],
  tss:         [15,  16,  18,  22,  28,  32,  38,  40,  36,  28,  20,  16],
  turbidity:   [12,  13,  15,  18,  22,  28,  32,  35,  30,  22,  16,  13],
  cod:         [20,  22,  25,  28,  32,  36,  40,  42,  38,  30,  24,  21],
  ammonia:     [1.2, 1.3, 1.5, 1.8, 2.2, 2.8, 3.2, 3.5, 3.0, 2.2, 1.6, 1.3],
  phosphate:   [1.5, 1.6, 1.8, 2.2, 2.8, 3.2, 3.8, 4.0, 3.5, 2.5, 1.8, 1.5],
  oil_grease:  [2.0, 2.1, 2.5, 2.8, 3.2, 3.8, 4.5, 4.8, 4.0, 3.0, 2.5, 2.0],
  ecoli:       [30,  32,  38,  45,  55,  72,  85,  90,  75,  52,  38,  30],
  coliforms:   [120, 130, 155, 180, 220, 280, 350, 380, 300, 210, 160, 130],
  chla:        [5,   6,   10,  15,  22,  30,  42,  45,  35,  18,  10,  6],
  phycocyanin: [15,  18,  35,  55,  95,  180, 320, 350, 250, 80,  30,  18],
  salinity:    [42,  43,  44,  46,  48,  50,  53,  55,  54,  50,  46,  43],
  water_temp:  [22,  23,  26,  29,  31,  33,  33,  33,  32,  29,  25,  24],
}

export const SOLAR_IRRADIANCE = [4.2, 5.0, 5.8, 6.5, 7.0, 7.2, 7.0, 6.8, 6.2, 5.5, 4.5, 4.0]

export const SLUDGE_ZONES = [
  { name: 'Zone A — Inlet',        totalDepth: 10, sludgeDepth: 2.5 },
  { name: 'Zone B — Central',      totalDepth: 10, sludgeDepth: 1.8 },
  { name: 'Zone C — Deep Basin',   totalDepth: 12, sludgeDepth: 3.2 },
  { name: 'Zone D — Shallow Edge', totalDepth: 6,  sludgeDepth: 2.0 },
  { name: 'Zone E — Outlet',       totalDepth: 8,  sludgeDepth: 1.5 },
]

export const TEMP_SPECIES_DOMINANCE = [
  { month: 'January',   temp: 22, cyano: 'Far below',  chloro: 'Below',        diatom: 'Near optimum', dominant: 'Diatoms' },
  { month: 'February',  temp: 23, cyano: 'Far below',  chloro: 'Below',        diatom: 'Near optimum', dominant: 'Diatoms' },
  { month: 'March',     temp: 26, cyano: 'Below',      chloro: 'Near optimum', diatom: 'Above',        dominant: 'Chlorophytes / Diatoms' },
  { month: 'April',     temp: 29, cyano: 'Near',       chloro: 'Above',        diatom: 'Above',        dominant: 'Chlorophytes → Cyano' },
  { month: 'May',       temp: 31, cyano: 'AT OPTIMUM', chloro: 'Above',        diatom: 'Far above',    dominant: 'Cyanobacteria' },
  { month: 'June',      temp: 33, cyano: 'AT OPTIMUM', chloro: 'Far above',    diatom: 'Far above',    dominant: 'Cyanobacteria' },
  { month: 'July',      temp: 33, cyano: 'AT OPTIMUM', chloro: 'Far above',    diatom: 'Far above',    dominant: 'Cyanobacteria' },
  { month: 'August',    temp: 33, cyano: 'AT OPTIMUM', chloro: 'Far above',    diatom: 'Far above',    dominant: 'Cyanobacteria' },
  { month: 'September', temp: 32, cyano: 'Near',       chloro: 'Above',        diatom: 'Far above',    dominant: 'Cyanobacteria' },
  { month: 'October',   temp: 29, cyano: 'Near',       chloro: 'Above',        diatom: 'Above',        dominant: 'Mixed → Chlorophytes' },
  { month: 'November',  temp: 25, cyano: 'Below',      chloro: 'Near optimum', diatom: 'Near optimum', dominant: 'Chlorophytes / Diatoms' },
  { month: 'December',  temp: 24, cyano: 'Far below',  chloro: 'Below',        diatom: 'AT OPTIMUM',   dominant: 'Diatoms' },
]

export const TREATMENT_CALENDAR = [
  { month: 'January',   phase: 'Phase 1: Pre-load', enzyme: 'Higher initial dosing; Pelletised sludge',         aeration: 'Low-intensity continuous',        ultrasound: 'Preventive mode',              risk: 'Low' },
  { month: 'February',  phase: 'Phase 1: Pre-load', enzyme: 'Continue elevated dosing',                          aeration: 'Low-intensity continuous',        ultrasound: 'Preventive mode',              risk: 'Low' },
  { month: 'March',     phase: 'Phase 1: Pre-load', enzyme: 'Final pre-load push',                               aeration: 'Increase to moderate',            ultrasound: 'Begin adaptive freq',          risk: 'Rising' },
  { month: 'April',     phase: 'Phase 2: Ramp',     enzyme: 'Shift to maintenance dosing',                       aeration: 'Moderate; Night boost begins',    ultrasound: 'Cyano-targeted if needed',     risk: 'Moderate' },
  { month: 'May',       phase: 'Phase 2: Ramp',     enzyme: 'Maintenance; Increase if Chl-a >15',               aeration: '75% capacity',                    ultrasound: 'Increase freq rotation',       risk: 'High' },
  { month: 'June',      phase: 'Phase 3: Peak',     enzyme: 'Fortnightly species-specific blend',                aeration: '100% continuous',                 ultrasound: 'Maximum interactive',          risk: 'VERY HIGH' },
  { month: 'July',      phase: 'Phase 3: Peak',     enzyme: 'Fortnightly protease-heavy for cyano',              aeration: '100% + emergency standby',        ultrasound: 'Maximum all units',            risk: 'CRITICAL' },
  { month: 'August',    phase: 'Phase 3: Peak',     enzyme: 'Fortnightly full-spectrum if Chl-a >30',            aeration: '100% + destratification',         ultrasound: 'Maximum adaptive',             risk: 'CRITICAL' },
  { month: 'September', phase: 'Phase 3: Peak',     enzyme: 'Continue fortnightly; Begin tapering',              aeration: '100%; Crash monitoring',          ultrasound: 'Maximum; Watch for crash',     risk: 'HIGH' },
  { month: 'October',   phase: 'Phase 4: Recovery', enzyme: 'Reduce frequency; Residual biomass',                aeration: 'Reduce to 75%',                   ultrasound: 'Step down to moderate',        risk: 'Moderate' },
  { month: 'November',  phase: 'Phase 4: Recovery', enzyme: 'Monthly maintenance; Sludge-targeted',              aeration: 'Reduce to moderate',              ultrasound: 'Preventive mode',              risk: 'Low' },
  { month: 'December',  phase: 'Phase 4: Recovery', enzyme: 'Monthly maintenance; Plan next year',               aeration: 'Low-intensity continuous',        ultrasound: 'Preventive; System maintenance',risk: 'Low' },
]
