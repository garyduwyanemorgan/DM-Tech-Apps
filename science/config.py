"""Scientific engine configuration — ALL thresholds and coefficients.

Design rule (Architecture.md): "No hard-coded thresholds". Every tunable
parameter used by the science engines lives here, with the scientific
justification documented inline. Engines import from this module; they never
inline a magic number.

Where a value is calibratable per-site, it is marked CALIBRATE. Defaults are
literature-based starting points for warm, hypersaline GCC lagoons fed by
Treated Sewage Effluent (TSE).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


# ════════════════════════════════════════════════════════════════════════════
# ENGINE 1 — NUTRIENT SOURCE ATTRIBUTION
# ════════════════════════════════════════════════════════════════════════════
# Each nutrient source has a characteristic chemical "signature". We score how
# well an observed reading (plus optional context) matches each end-member,
# then normalise to percentage contributions. This is an explainable
# signature-matching model — NOT isotopic fingerprinting (which would need
# δ15N / δ18O lab data). Confidence reflects how distinct the match is and
# how much context was supplied.

@dataclass(frozen=True)
class SourceSignature:
    """Characteristic ranges for one nutrient end-member."""
    name: str
    # Typical N:P mass ratio of the source (helps discriminate sources)
    np_ratio: float
    # Does this source carry high ammonia (reduced N)? 0..1 weight
    ammonia_affinity: float
    # Is it episodic (rain/dust) vs continuous (TSE/groundwater)? 0..1 (1=episodic)
    episodic: float
    # Salinity association: -1 freshening (runoff/TSE), 0 neutral, +1 saline (groundwater)
    salinity_sign: float
    description: str


# Signatures for GCC TSE-fed lagoons. CALIBRATE per site from inflow sampling.
NUTRIENT_SIGNATURES: Dict[str, SourceSignature] = {
    "TSE": SourceSignature(
        "Treated Sewage Effluent", np_ratio=4.0, ammonia_affinity=0.8,
        episodic=0.0, salinity_sign=-0.6,
        description="Continuous high-N, high-P municipal effluent; elevated ammonia; freshening."),
    "internal_loading": SourceSignature(
        "Internal Sediment Loading", np_ratio=0.5, ammonia_affinity=0.4,
        episodic=0.0, salinity_sign=0.0,
        description="Redox-driven Fe-P release from sediment; very low N:P (P-dominated)."),
    "runoff": SourceSignature(
        "Landscape / Irrigation Runoff", np_ratio=6.0, ammonia_affinity=0.3,
        episodic=0.6, salinity_sign=-0.4,
        description="Fertiliser + TSE irrigation return; high N:P; rain/irrigation driven."),
    "groundwater": SourceSignature(
        "Groundwater Seepage", np_ratio=2.0, ammonia_affinity=0.2,
        episodic=0.0, salinity_sign=0.9,
        description="Steady saline baseline seepage; high water table; moderate nutrients."),
    "atmospheric": SourceSignature(
        "Atmospheric Deposition (Dust)", np_ratio=8.0, ammonia_affinity=0.1,
        episodic=1.0, salinity_sign=0.1,
        description="Dust delivers Fe, N, P; episodic; Gulf is N-limited so dust-N matters."),
}

# How strongly each contextual flag pulls attribution toward a source.
# Context flags are optional; without them the model leans on chemistry alone
# and lowers confidence accordingly.
NUTRIENT_CONTEXT_WEIGHT = 0.35   # 0..1 — weight given to context vs chemistry
NUTRIENT_MIN_CONFIDENCE = 25.0   # % — floor when only chemistry is available
NUTRIENT_MAX_CONFIDENCE = 92.0   # % — ceiling without isotopic confirmation


# ════════════════════════════════════════════════════════════════════════════
# ENGINE 2 — INTERNAL SEDIMENT LOADING (Fe-P REDOX)
# ════════════════════════════════════════════════════════════════════════════
# Classic limnology (Mortimer 1941; Boström et al. 1988): ferric iron Fe(III)
# binds phosphate at the oxidised sediment surface. When the sediment-water
# interface goes reducing, Fe(III)→Fe(II) and the bound PO4 is released:
#       Fe(OOH)~P  +  e-  →  Fe2+  +  PO4(3-)
# Release risk rises as DO and ORP fall and as temperature accelerates
# microbial O2 demand. These thresholds are the redox ladder.

# Dissolved oxygen at the sediment interface (mg/L). Oxic retains P; anoxic releases.
SEDIMENT_DO_OXIC = 4.0       # > this: Fe oxidised, P retained
SEDIMENT_DO_HYPOXIC = 2.0    # between: transitional
SEDIMENT_DO_ANOXIC = 0.5     # < this: strongly reducing, P release

# Redox potential ORP (mV). Mortimer's critical Fe-P boundary ~ +200 mV.
SEDIMENT_ORP_OXIC = 200.0    # > this: P retained
SEDIMENT_ORP_TRANSITION = 100.0
SEDIMENT_ORP_REDUCING = 0.0  # < this: active P release

# Temperature acceleration. Microbial respiration roughly doubles per 10°C (Q10≈2),
# deepening hypoxia and speeding release. Reference 20°C.
SEDIMENT_TEMP_REF = 20.0
SEDIMENT_TEMP_Q10 = 2.0

# Ambient water-column phosphate (mg/L) — elevated values corroborate ongoing
# release and raise severity.
SEDIMENT_PO4_ELEVATED = 2.0
SEDIMENT_PO4_HIGH = 4.0

# Sediment state multiplier (caller-supplied qualitative state → factor).
# Organic-rich, previously-blooming sediment has a larger mobile-P pool.
SEDIMENT_STATE_FACTOR: Dict[str, float] = {
    "mineral": 0.7,        # sandy / low organic
    "normal": 1.0,         # default if unknown
    "organic": 1.3,        # organic-rich
    "post_bloom": 1.5,     # large fresh labile-P pool after a die-off
}

# Score → category bands (0..1 internal-loading score).
SEDIMENT_BANDS: Tuple[Tuple[float, str], ...] = (
    (0.25, "LOW"),
    (0.50, "MODERATE"),
    (0.75, "HIGH"),
    (1.01, "SEVERE"),
)


# ════════════════════════════════════════════════════════════════════════════
# ENGINE 3 — RESIDENCE TIME
# ════════════════════════════════════════════════════════════════════════════
# Hydraulic residence (flushing) time τ = V / Q_out (days), with volume in m³
# and flow in m³/day. Recirculation re-uses water internally and does not flush
# nutrients out, so it reduces *net* flushing. Long residence promotes
# stratification, nutrient accumulation and bloom development.

# Recirculation discount: fraction of recirculated flow that counts as NON-
# flushing (1.0 = pure internal loop, removes nothing). CALIBRATE.
RESIDENCE_RECIRC_DISCOUNT = 1.0

# Residence-time risk bands (days). Many shallow eutrophic-lagoon studies place
# bloom-favouring stagnation in the weeks-to-months range.
RESIDENCE_BANDS: Tuple[Tuple[float, str], ...] = (
    (7.0, "LOW"),         # < 1 week: well flushed
    (30.0, "MODERATE"),   # 1 week–1 month
    (90.0, "HIGH"),       # 1–3 months: accumulation
    (float("inf"), "SEVERE"),  # > 3 months: stagnant
)

# Risk score saturates at this residence time (days) → score 1.0.
RESIDENCE_RISK_SATURATION = 120.0


# ════════════════════════════════════════════════════════════════════════════
# ENGINE 4 — BLOOM FORECAST
# ════════════════════════════════════════════════════════════════════════════
# Explainable weighted-driver model. Each driver is normalised to a 0..1
# favourability for cyanobacterial/algal bloom, then combined with documented
# weights. No black box: the per-driver contributions are returned.

# Driver weights (must sum to ~1.0). Rationale in bloom_forecast.py docstrings.
BLOOM_WEIGHTS: Dict[str, float] = {
    "temperature":     0.22,   # cyano growth optimum is warm
    "phosphate":       0.20,   # P commonly co-limiting; internal loading feeds it
    "ammonia":         0.15,   # reduced N preferred by cyanobacteria
    "dissolved_oxygen":0.10,   # low DO = stress + reinforces internal loading
    "residence_time":  0.18,   # stagnation lets biomass accumulate
    "salinity":        0.07,   # many bloom cyano prefer lower salinity
    "internal_loading":0.08,   # sediment P feedback
}

# Temperature favourability (°C): cyanobacteria optimum ~28–35°C in this setting.
BLOOM_TEMP_MIN = 18.0          # below: negligible
BLOOM_TEMP_OPT_LOW = 28.0
BLOOM_TEMP_OPT_HIGH = 35.0

# Phosphate favourability (mg/L) — saturating.
BLOOM_PO4_HALF_SAT = 2.0       # mg/L at which favourability = 0.5

# Ammonia favourability (mg/L) — saturating.
BLOOM_NH3_HALF_SAT = 2.5

# Salinity favourability (PSU) — bloom-formers here favour the fresher lens.
BLOOM_SAL_LOW = 35.0           # ≤ this: most favourable
BLOOM_SAL_HIGH = 60.0          # ≥ this: hypersaline suppression

# Historical-bloom prior: each prior bloom at the site raises baseline
# susceptibility by this much (capped).
BLOOM_HISTORY_WEIGHT = 0.05
BLOOM_HISTORY_CAP = 0.25

# Probability → severity bands.
BLOOM_SEVERITY_BANDS: Tuple[Tuple[float, str], ...] = (
    (0.25, "MINIMAL"),
    (0.50, "MODERATE"),
    (0.75, "SIGNIFICANT"),
    (1.01, "SEVERE"),
)

# Recovery-time model: base days to clear a bloom once triggered, scaled by
# severity and lengthened by residence time (poor flushing = slow recovery).
BLOOM_RECOVERY_BASE_DAYS = 7.0
BLOOM_RECOVERY_SEVERITY_DAYS = 21.0   # added at severity 1.0
BLOOM_RECOVERY_RESIDENCE_FACTOR = 0.15  # extra days per residence-day


# ════════════════════════════════════════════════════════════════════════════
# ENGINE 6 — ALGAE COMMUNITY / TYPE
# ════════════════════════════════════════════════════════════════════════════
# Predicts the FAVOURED phytoplankton group and the ecological succession stage
# from the water-quality drivers we already collect — no lab species ID needed.
# Borrows the ecological reasoning (cyanobacteria competitive advantage +
# succession) as an IDEA; the numbers below are ours and CALIBRATE per site.
# The measured phycocyanin:chlorophyll-a ratio is used only as an observational
# anchor (cyanobacteria pigment proxy), never as a required input.

COMMUNITY_GROUPS: Tuple[str, ...] = ("cyanobacteria", "green_algae", "diatoms", "dinoflagellates")

# ── Cyanobacteria competitive advantage (0–1) ──
# Cyanobacteria win when it is warm, N:P is low (reduced-N favours N-fixers) and
# DO is low (they tolerate it). Weights sum to 1.0.
CYANO_ADV_WEIGHTS: Dict[str, float] = {
    "temperature":      0.40,
    "n_p_ratio":        0.35,
    "dissolved_oxygen": 0.25,
}
CYANO_TEMP_TRACE = 15.0        # °C below which cyano advantage ≈ 0
CYANO_TEMP_MIN   = 25.0        # advantage starts ramping above here
CYANO_TEMP_FULL  = 30.0        # full thermal advantage at/above here
CYANO_NP_FULL    = 5.0         # N:P ≤ this → full advantage (strong N limitation)
CYANO_NP_MOD     = 10.0        # N:P between FULL and MOD → ramps down
CYANO_NP_REDFIELD = 16.0       # ~Redfield; above here → no N-limitation advantage
CYANO_DO_FULL    = 2.0         # DO ≤ this mg/L → full low-oxygen advantage
CYANO_DO_NONE    = 5.0         # DO ≥ this mg/L → no low-oxygen advantage

# ── Trophic state from chlorophyll-a (µg/L), Carlson-style bands ──
TROPHIC_CHLA_BANDS: Tuple[Tuple[float, str], ...] = (
    (2.0,  "oligotrophic"),
    (8.0,  "mesotrophic"),
    (25.0, "eutrophic"),
    (1e9,  "hypereutrophic"),
)

# ── Phycocyanin:chlorophyll-a pigment marker (both µg/L → dimensionless) ──
# The direct MEASURED signal of cyanobacteria dominance. Below LOW → no cyano
# pigment signal; above HIGH → biomass is strongly cyanobacteria.
PHYCO_CHLA_LOW  = 0.8
PHYCO_CHLA_HIGH = 3.0
# How much the measured pigment anchor is trusted vs the driver model (0–1).
COMMUNITY_PIGMENT_WEIGHT = 0.5

# ── Per-group driver preferences (each factor a 0–1 favourability) ──
# Diatoms: cooler, well-oxygenated/mixed, N-replete (higher N:P), lower trophic.
# Green algae: the transitional "greening" middle — moderate everything.
# Dinoflagellates: warm + more saline + stratified (low DO), but NOT N-limited.
GREEN_TEMP_LOW, GREEN_TEMP_HIGH = 18.0, 30.0
DIATOM_DO_GOOD = 6.0           # DO ≥ this favours diatoms (well-mixed)
DINO_SAL_LOW, DINO_SAL_HIGH = 45.0, 60.0   # dinoflagellates favoured in the saltier lens

# ── Ecological succession thresholds ──
SUCCESSION_COLLAPSE_DO    = 1.5   # DO below this mg/L → post-bloom collapse
SUCCESSION_ACTIVE_PROB    = 0.70  # bloom probability at/above → active bloom
SUCCESSION_CYANO_PROB     = 0.45  # cyano-favoured risk zone
SUCCESSION_GREEN_PROB     = 0.25  # greening

# ── Lab-test recommendation triggers ──
# When conditions favour cyanobacteria (the toxin-formers), recommend the SaaS
# request a confirmatory phytoplankton ID + cyanotoxin lab test.
CYANO_LAB_TEST_ADVANTAGE = 0.55   # cyano advantage at/above → recommend a test
PHYCO_CHLA_LAB_TEST      = 1.5    # measured pigment ratio at/above → recommend a test

# ── Data-request items ──
# Parameters REQUIRED to make the algae-community prediction. If a reading is
# missing any of these, they belong in the data request (measure them).
COMMUNITY_REQUIRED_INPUTS: Dict[str, str] = {
    "temperature":      "Water temperature (°C)",
    "dissolved_oxygen": "Dissolved oxygen (mg/L)",
    "ammonia":          "Ammonia as N (mg/L)",
    "phosphate":        "Phosphate (mg/L)",
    "salinity":         "Salinity (PSU)",
    "chla":             "Chlorophyll-a (µg/L)",
    "phycocyanin":      "Phycocyanin (µg/L)",
}
# Parameters we do not currently capture that would STRENGTHEN the algae call.
COMMUNITY_ENHANCING_INPUTS: Dict[str, str] = {
    "nitrate": "Nitrate/nitrite as N (mg/L) — gives a true total-N:P instead of the ammonia-only proxy",
    "orp":     "ORP / redox potential (mV) — sediment low-oxygen & internal-loading signal",
}
# Confirmatory lab tests recommended when cyanobacteria are favoured.
COMMUNITY_CONFIRMATORY_TESTS: Tuple[str, ...] = (
    "Phytoplankton identification / cell count",
    "Cyanotoxin screen (e.g. microcystin ELISA)",
)


# ════════════════════════════════════════════════════════════════════════════
# ENGINE 5 — DIGITAL TWIN
# ════════════════════════════════════════════════════════════════════════════
# Scenario interventions and how they propagate through the chain. Each
# intervention maps to multiplicative/additive effects on engine inputs, plus
# a realistic time-to-effect. CALIBRATE against site response data.

@dataclass(frozen=True)
class Intervention:
    key: str
    label: str
    time_to_effect_days: float
    description: str


DIGITAL_TWIN_INTERVENTIONS: Dict[str, Intervention] = {
    "reduce_phosphate": Intervention(
        "reduce_phosphate", "Reduce external phosphate load",
        time_to_effect_days=21,
        description="Source control / P-binding; lowers water-column phosphate."),
    "increase_circulation": Intervention(
        "increase_circulation", "Increase circulation / aeration",
        time_to_effect_days=7,
        description="Raises DO and ORP, shortens residence time, suppresses internal loading."),
    "remove_sludge": Intervention(
        "remove_sludge", "Dredge / remove sludge",
        time_to_effect_days=45,
        description="Removes the mobile-P sediment pool; cuts internal loading at source."),
    "reduce_residence_time": Intervention(
        "reduce_residence_time", "Increase flushing / exchange",
        time_to_effect_days=3,
        description="More outflow exchange; flushes nutrients and biomass."),
}


# ════════════════════════════════════════════════════════════════════════════
# PREDICTIVE MONITORING — forecast confidence + validation + sampling economics
# ════════════════════════════════════════════════════════════════════════════
# Commercial value proposition: let operators sample fewer lagoons less often,
# while the model predicts the rest with a STATED confidence band that widens
# the longer it has been since a real sample. Every real sample validates the
# model (predicted-vs-actual), building the track record that earns the right
# to stretch the interval — but NEVER below the regulatory floor.

# Parameters the predictor/validator track (key bloom & compliance indicators).
# Each maps to a WaterReading attribute. Typical seasonal spread (1 std, in the
# parameter's own units) is a literature/baseline estimate — CALIBRATE per site.
PREDICTED_PARAMETERS: dict[str, dict] = {
    "chla":        {"attr": "chla",        "label": "Chlorophyll-a", "unit": "µg/L", "season_std": 8.0},
    "do":          {"attr": "do",          "label": "Dissolved Oxygen", "unit": "mg/L", "season_std": 0.8},
    "phosphate":   {"attr": "phosphate",   "label": "Phosphate", "unit": "mg/L", "season_std": 0.7},
    "ammonia":     {"attr": "ammonia",     "label": "Ammonia", "unit": "mg/L", "season_std": 0.6},
    "phycocyanin": {"attr": "phycocyanin", "label": "Phycocyanin", "unit": "µg/L", "season_std": 60.0},
}

# Confidence band half-width = Z * season_std * decay_factor.
# Z=1.96 → nominal 95% band when the model is well-calibrated.
PREDICT_BAND_Z = 1.96

# Confidence decay: uncertainty grows with months since the last real sample.
# band_multiplier = 1 + DECAY_PER_MONTH * months_since_sample (capped).
PREDICT_DECAY_PER_MONTH = 0.18
PREDICT_DECAY_CAP = 3.0

# Extrapolated (un-sampled, inferred from sentinel) lagoons start wider.
PREDICT_SENTINEL_PENALTY = 1.4   # band multiplier when value is extrapolated

# Reported confidence % from the band multiplier (tighter band → higher %).
PREDICT_CONF_MAX = 95.0
PREDICT_CONF_MIN = 40.0

# ── Regulatory floor (Compliance mandates a minimum sampling cadence) ──
# The optimizer may stretch intervals UP TO this floor but never beyond it.
COMPLIANCE_MIN_SAMPLING_DAYS = 90        # every lagoon physically sampled ≥ quarterly
Compliance_SENTINEL_SAMPLING_DAYS = 30   # designated sentinel lagoons sampled monthly

# ── Sampling economics (for the ROI / savings view) ──
SAMPLING_COST_AED = 2000.0          # cost of one full Compliance lab analysis (AED). CALIBRATE.


# ════════════════════════════════════════════════════════════════════════════
# DRIVER / FORCING LAYER  (INTERNAL — never surfaced client-facing)
# ════════════════════════════════════════════════════════════════════════════
# External forcings (weather + operator inputs) drive the causal chain. Because
# weather is available continuously without sampling the lagoon, the model can
# predict lagoon state from drivers and only needs real samples to validate /
# calibrate the driver→state mapping. This is core IP — keep out of any
# client-facing label or chart.

# Dubai site coordinates for the meteorological feed.
DUBAI_LAT = 25.20
DUBAI_LON = 55.27

# Dubai monthly climatology normals (index 0 = January). Used as the offline
# baseline and the fallback when the live feed is unavailable. Defensible
# regional normals — CALIBRATE to the specific site if local met data exists.
CLIMATOLOGY = {
    # mean air temperature (°C)
    "air_temp":  [19, 20, 23.5, 28, 33, 35, 37, 37, 34, 30, 25, 21],
    # shortwave solar (kWh/m²/day)
    "solar":     [4.2, 5.0, 5.8, 6.5, 7.0, 7.2, 7.0, 6.8, 6.2, 5.5, 4.5, 4.0],
    # wind speed (m/s)
    "wind":      [4.0, 4.1, 4.3, 4.4, 4.5, 4.6, 4.5, 4.4, 4.2, 4.0, 3.9, 3.9],
    # relative humidity (%)
    "humidity":  [65, 64, 62, 58, 55, 53, 55, 57, 60, 62, 64, 66],
    # rainfall (mm/month)
    "rainfall":  [18, 25, 20, 8, 1, 0, 0, 0, 0, 1, 3, 12],
}

# Driver → state transfer coefficients (transparent, calibratable).
# Water temperature tracks air temperature plus a solar surplus.
WATERTEMP_AIR_COEF = 0.82           # water temp sensitivity to air temp
WATERTEMP_SOLAR_COEF = 0.9          # °C added per kWh/m²/day above winter baseline
WATERTEMP_SOLAR_REF = 4.0           # winter solar baseline (kWh/m²/day)
WATERTEMP_OFFSET = 4.0              # shallow warm-lagoon offset (°C)

# Evaporation (Priestley-Taylor) constants.
PT_ALPHA = 1.26                     # Priestley-Taylor coefficient (open water)
PT_PSYCHROMETRIC = 0.066            # γ (kPa/°C)
PT_LATENT_HEAT = 2.45               # λ (MJ/kg)
PT_NET_RAD_FRACTION = 0.80          # Rn ≈ fraction of incoming shortwave (water)
SOLAR_KWH_TO_MJ = 3.6               # 1 kWh/m²/day = 3.6 MJ/m²/day

# Evaporative concentration: salinity rises as evaporation removes freshwater.
# Δsalinity ≈ SALINITY_EVAP_COEF × (evap_mm_day) over the residence window.
SALINITY_EVAP_COEF = 0.18           # PSU per mm/day of net evaporation. CALIBRATE.
SALINITY_BASELINE_PSU = 42.0        # inflow / winter baseline salinity


# ════════════════════════════════════════════════════════════════════════════
# CALIBRATION / DATA ASSIMILATION  (INTERNAL — never surfaced client-facing)
# ════════════════════════════════════════════════════════════════════════════
# Bayesian correction of the process model against real samples. We infer a
# multiplicative bias factor θ per parameter (θ=1 → model unbiased) in log-space
# with a conjugate-Gaussian update: exact, fast, works from zero observations
# (posterior = prior) and tightens with each sample. This is the lightweight
# data-assimilation engine; tinyDA's delayed-acceptance MCMC is the drop-in
# heavy engine for the nonlinear multi-parameter regime once data is plentiful.

# Prior: a priori the process model could be off by ~±65% in scale.
CALIB_PRIOR_LOG_STD = 0.5
# Per-observation noise (measurement + spatial representativeness), log-space.
CALIB_OBS_LOG_STD = 0.20
# Predictive log-std → confidence% mapping (tighter posterior → higher %).
CALIB_CONF_MAX = 96.0
CALIB_CONF_MIN = 35.0
CALIB_CONF_STD_FLOOR = 0.12         # predictive std at/below → max confidence
CALIB_CONF_STD_CEIL = 0.60          # predictive std at/above → min confidence


# ════════════════════════════════════════════════════════════════════════════
# ADAPTIVE SAMPLING OPTIMIZER  (output IS client-facing: recommendation + savings)
# ════════════════════════════════════════════════════════════════════════════
# Confidence below this → a real sample is recommended (uncertainty-driven).
ADAPTIVE_CONF_THRESHOLD = 80.0
# A lagoon flagged high operational risk is always sampled regardless of conf.
ADAPTIVE_RISK_FORCE = "SEVERE"
