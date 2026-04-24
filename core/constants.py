"""DECCA/DM regulatory limits, alert thresholds, and reference data.

All values sourced from Dubai_Lagoon_Algae_Management_System.md.
Zero UI dependencies — pure data.
"""
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, List, Tuple

# ── DECCA/DM Water Quality Standards ──

@dataclass(frozen=True)
class DECCALimit:
    parameter: str
    unit: str
    min_val: float | None  # None = no lower bound
    max_val: float | None  # None = no upper bound
    display: str            # Human-readable limit string

DECCA_LIMITS: Dict[str, DECCALimit] = {
    "ph":               DECCALimit("pH",                  "pH Units",   6.0,  9.0,  "6.0 – 9.0"),
    "do":               DECCALimit("Dissolved Oxygen",    "mg/L",       4.0,  None, "> 4.0"),
    "tss":              DECCALimit("TSS",                 "mg/L",       None, 50,   "< 50"),
    "turbidity":        DECCALimit("Turbidity",           "NTU",        None, 75,   "< 75"),
    "cod":              DECCALimit("COD",                 "mg/L",       None, 50,   "< 50"),
    "ammonia":          DECCALimit("Ammonia (as N)",      "mg/L",       None, 5.0,  "< 5.0"),
    "phosphate":        DECCALimit("Total Phosphate",     "mg/L",       None, 5.0,  "< 5.0"),
    "oil_grease":       DECCALimit("Oils & Grease",       "mg/L",       None, 10,   "< 10"),
    "ecoli":            DECCALimit("E. coli",             "CFU/100mL",  None, 200,  "< 200"),
    "total_coliforms":  DECCALimit("Total Coliforms",     "CFU/100mL",  None, 1000, "< 1000"),
}

# ── Alert Levels ──

class AlertLevel(IntEnum):
    GREEN    = 1
    WATCH    = 2
    WARNING  = 3
    CRITICAL = 4

ALERT_COLORS = {
    AlertLevel.GREEN:    "#27ae60",
    AlertLevel.WATCH:    "#f39c12",
    AlertLevel.WARNING:  "#e67e22",
    AlertLevel.CRITICAL: "#e74c3c",
}

ALERT_LABELS = {
    AlertLevel.GREEN:    "Level 1 — GREEN",
    AlertLevel.WATCH:    "Level 2 — WATCH",
    AlertLevel.WARNING:  "Level 3 — WARNING",
    AlertLevel.CRITICAL: "Level 4 — CRITICAL",
}

@dataclass(frozen=True)
class AlertThresholds:
    bloom_prob_range: Tuple[float, float]
    chla_trigger: str
    do_trigger: str
    phycocyanin_trigger: str
    temp_trigger: str
    monitoring_freq: str
    client_reporting: str

ALERT_THRESHOLDS: Dict[AlertLevel, AlertThresholds] = {
    AlertLevel.GREEN: AlertThresholds(
        (0, 25), "< 10 µg/L", "> 5 mg/L", "< 50 µg/L", "< 27°C",
        "Weekly", "Weekly report"),
    AlertLevel.WATCH: AlertThresholds(
        (25, 50), "10–30 rising", "< 4 mg/L", "> 50 µg/L", "> 28°C",
        "Daily", "Daily dashboard"),
    AlertLevel.WARNING: AlertThresholds(
        (50, 75), "> 30 µg/L", "< 3 mg/L", "> 200 µg/L", "Any",
        "Hourly", "Real-time alerts"),
    AlertLevel.CRITICAL: AlertThresholds(
        (75, 100), "> 75 µg/L", "< 2 mg/L", "Visible mat", "Any",
        "10-min", "Immediate alert"),
}

# ── Treatment Actions ──

@dataclass(frozen=True)
class TreatmentAction:
    enzyme: str
    aeration: str
    ultrasound: str
    monitoring: str
    do_not: str

TREATMENT_ACTIONS: Dict[AlertLevel, TreatmentAction] = {
    AlertLevel.GREEN: TreatmentAction(
        "Monthly maintenance dose (pelletised sludge)",
        "Low-intensity continuous; Night boost sunset–sunrise 50%",
        "Preventive mode, adaptive low-frequency",
        "Weekly manual sampling; 10-min sensor cycle",
        "—"),
    AlertLevel.WATCH: TreatmentAction(
        "Fortnightly liquid dosing; Protease-heavy if phycocyanin rising",
        "75% capacity; Night boost 2hr before sunset; Target DO ≥ 4",
        "Increase freq rotation; Cyano-targeted if phycocyanin rising",
        "2×/week manual N, P, species; Daily auto-reports",
        "—"),
    AlertLevel.WARNING: TreatmentAction(
        "Pulse dose 3× intensity; Species-specific blend; Continuous 48hr",
        "100% continuous; Emergency aerators; Destratification protocol",
        "Maximum interactive programme; All units full power",
        "Continuous auto-analysis; Hourly trends; Toxin screening",
        "DO NOT DEPLOY ALGICIDE"),
    AlertLevel.CRITICAL: TreatmentAction(
        "Daily full-spectrum cocktail; Reinoculate bacteria if DO killed population",
        "Emergency protocol; All capacity + contingency; DO must stay > 2",
        "Continue maximum; Shift to aeration if dinoflagellates",
        "10-min reporting; Toxin analysis; Independent lab verification",
        "DO NOT DEPLOY ALGICIDE"),
}

# ── Seasonal Phases ──

@dataclass(frozen=True)
class SeasonalPhase:
    name: str
    months: List[int]
    color: str
    objective: str

SEASONAL_PHASES = [
    SeasonalPhase("Phase 1: Pre-load",  [1, 2, 3],        "#5dade2", "Establish bacterial populations before heat"),
    SeasonalPhase("Phase 2: Ramp",      [4, 5],           "#f4d03f", "Transition to active bloom prevention"),
    SeasonalPhase("Phase 3: Peak",      [6, 7, 8, 9],    "#e74c3c", "Continuous bloom suppression; DECCA compliance"),
    SeasonalPhase("Phase 4: Recovery",  [10, 11, 12],     "#27ae60", "System recovery; Sludge management; Planning"),
]

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

# ── Species Data ──

@dataclass(frozen=True)
class SpeciesProfile:
    category: str
    group: str
    key_species: str
    salinity_range: str
    temp_optimum: str
    toxin_type: str
    threat_level: str
    peak_season: str
    treatment: str
    color: str

SPECIES_PROFILES = [
    SpeciesProfile("HIGH THREAT", "Dinoflagellates",
        "Cochlodinium, Chattonella, Noctiluca, Blixaea",
        "35–45 PSU", "25–33°C", "Ichthyotoxic (fish-killing)", "HIGH",
        "Year-round, peak summer", "Aeration + enzymes", "#e74c3c"),
    SpeciesProfile("HIGH THREAT", "Cyanobacteria",
        "Microcystis, Oscillatoria, Lyngbya",
        "0–15 PSU", "28–35°C", "Hepatotoxic (microcystins)", "HIGH",
        "Summer (TSE lens)", "Ultrasound + enzymes", "#c0392b"),
    SpeciesProfile("MODERATE", "Green Macroalgae",
        "Ulva, Chaetomorpha, Cladophora",
        "5–50+ PSU", "Broad", "Non-toxic (aesthetic/odour/BOD)", "MODERATE",
        "Year-round", "Enzyme removal", "#f39c12"),
    SpeciesProfile("MODERATE", "Diatoms",
        "Pseudo-nitzschia, Chaetoceros, Skeletonema",
        "35–40 PSU", "15–25°C", "Domoic acid (some)", "MODERATE",
        "Dec–Mar", "Seasonal monitoring", "#e67e22"),
    SpeciesProfile("SPECIALIST", "Hypersaline Green",
        "Dunaliella salina",
        "35–200+ PSU", "Broad", "None (indicator)", "LOW",
        "When hypersaline", "Indicator of poor exchange", "#3498db"),
    SpeciesProfile("SPECIALIST", "Benthic Cyano Mats",
        "Lyngbya, Phormidium",
        "35–60 PSU", "Broad", "Variable", "LOW",
        "Year-round (bottom)", "Sludge management", "#2980b9"),
]

# ── Nutrient Sources ──

NUTRIENT_SOURCES = [
    {"rank": 1, "source": "Treated Sewage Effluent (TSE)", "contribution": "DOMINANT",
     "controllability": "HIGH", "monitoring": "Inflow meters + lab analysis",
     "mechanism": "Residual N & P; DM standard 25 mg PO₄/L"},
    {"rank": 2, "source": "Landscape Irrigation Runoff", "contribution": "Significant",
     "controllability": "MEDIUM", "monitoring": "Drain sampling",
     "mechanism": "TSE nutrients + landscape fertiliser = double loading"},
    {"rank": 3, "source": "Greywater / Detergent Phosphates", "contribution": "Moderate",
     "controllability": "HIGH", "monitoring": "Source auditing",
     "mechanism": "Phosphate-containing detergents common in region"},
    {"rank": 4, "source": "Atmospheric Deposition (Dust)", "contribution": "Variable",
     "controllability": "NONE", "monitoring": "Met forecast; Dust index API",
     "mechanism": "Dust delivers Fe, N, P; Gulf is N-limited"},
    {"rank": 5, "source": "Internal Sediment Loading", "contribution": "30–60% of total P",
     "controllability": "MEDIUM", "monitoring": "Sediment cores; Bottom DO sensors",
     "mechanism": "Anoxic sediment releases Fe²⁺-bound PO₄"},
    {"rank": 6, "source": "Groundwater Seepage", "contribution": "Low–Moderate",
     "controllability": "LOW", "monitoring": "Piezometers",
     "mechanism": "High water table + saline groundwater seepage"},
]

# ── Enzyme & Bacteria Reference ──

ENZYME_TOOLKIT = [
    {"enzyme": "Cellulases", "target": "Algal cell walls", "ph": "4–7", "temp": "~50°C",
     "dubai_range": "Active at 30–38°C", "species": "All algae with cellulose walls"},
    {"enzyme": "Proteases", "target": "Algal proteins (~50% dry wt)", "ph": "6–9", "temp": "~37°C",
     "dubai_range": "Optimal at Dubai summer temps", "species": "Especially cyano"},
    {"enzyme": "Lipases", "target": "Fats, oils, membranes", "ph": "7–9", "temp": "30–37°C",
     "dubai_range": "Optimal at Dubai water temps", "species": "All species"},
    {"enzyme": "Amylases", "target": "Starch, glycogen", "ph": "5–8", "temp": "~37°C",
     "dubai_range": "Active in Dubai conditions", "species": "Green algae especially"},
]

BACTERIAL_CONSORTIUM = [
    {"genus": "Bacillus", "species": "B. altitudinis, B. subtilis",
     "salt_tolerance": "Up to ~2M NaCl", "role": "Broad enzyme production",
     "suitability": "HIGH", "spore_forming": True},
    {"genus": "Halomonas", "species": "H. elongata",
     "salt_tolerance": "0–5M NaCl (true halophile)", "role": "High-salinity bioremediation",
     "suitability": "ESSENTIAL for 50+ PSU", "spore_forming": False},
    {"genus": "Pseudomonas", "species": "P. aeruginosa, P. fluorescens",
     "salt_tolerance": "Moderate", "role": "Versatile organic degradation",
     "suitability": "MODERATE — lower salinity zones", "spore_forming": False},
]

# ── ML Model Reference ──

ML_MODELS = [
    {"model": "Random Forest", "range": "1–7 days", "data_need": "4+ years",
     "r2": "0.78–0.88", "advantage": "Interpretable (SHAP); handles missing data",
     "tier": 1, "role": "Near-term snapshots"},
    {"model": "XGBoost", "range": "1–7 days", "data_need": "4+ years",
     "r2": "0.92", "advantage": "Speed + accuracy; Gradient boosting",
     "tier": 1, "role": "Near-term high accuracy"},
    {"model": "LSTM", "range": "1–30 days", "data_need": "3+ years",
     "r2": "Comparable", "advantage": "Captures temporal dynamics and lag effects",
     "tier": 1, "role": "Temporal trajectory"},
]

ENSEMBLE_WEIGHTS = [
    {"horizon": "1-day", "rf": 70, "lstm": 30, "rationale": "RF excels at near-term snapshots"},
    {"horizon": "3-day", "rf": 40, "lstm": 60, "rationale": "LSTM captures emerging temporal patterns"},
    {"horizon": "7-day", "rf": 20, "lstm": 80, "rationale": "LSTM dominates for trajectory prediction"},
]
