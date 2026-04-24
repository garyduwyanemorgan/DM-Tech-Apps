"""Generate realistic Dubai lagoon sample data for the dashboard.

All values follow seasonal patterns documented in the management system:
- Temp: 22°C (Jan) → 33°C (Jul-Sep) → 24°C (Dec)
- DO inversely correlated with temp
- Chl-a: low winter, peak summer
- Salinity: 42 winter → 55 summer
"""
from datetime import date, datetime
from typing import List

from core.models import SludgeZone, WaterReading

# ── Monthly baseline data (index 0 = January) ──

_MONTHLY = {
    "ph":          [7.6, 7.5, 7.4, 7.3, 7.2, 7.1, 7.0, 7.0, 7.1, 7.2, 7.4, 7.5],
    "do":          [7.2, 7.0, 6.5, 6.0, 5.5, 4.8, 4.5, 4.3, 4.5, 5.2, 6.2, 7.0],
    "tss":         [15,  16,  18,  22,  28,  32,  38,  40,  36,  28,  20,  16],
    "turbidity":   [12,  13,  15,  18,  22,  28,  32,  35,  30,  22,  16,  13],
    "cod":         [20,  22,  25,  28,  32,  36,  40,  42,  38,  30,  24,  21],
    "ammonia":     [1.2, 1.3, 1.5, 1.8, 2.2, 2.8, 3.2, 3.5, 3.0, 2.2, 1.6, 1.3],
    "phosphate":   [1.5, 1.6, 1.8, 2.2, 2.8, 3.2, 3.8, 4.0, 3.5, 2.5, 1.8, 1.5],
    "oil_grease":  [2.0, 2.1, 2.5, 2.8, 3.2, 3.8, 4.5, 4.8, 4.0, 3.0, 2.5, 2.0],
    "ecoli":       [30,  32,  38,  45,  55,  72,  85,  90,  75,  52,  38,  30],
    "coliforms":   [120, 130, 155, 180, 220, 280, 350, 380, 300, 210, 160, 130],
    "chla":        [5,   6,   10,  15,  22,  30,  42,  45,  35,  18,  10,  6],
    "phycocyanin": [15,  18,  35,  55,  95,  180, 320, 350, 250, 80,  30,  18],
    "salinity":    [42,  43,  44,  46,  48,  50,  53,  55,  54,  50,  46,  43],
    "water_temp":  [22,  23,  26,  29,  31,  33,  33,  33,  32,  29,  25,  24],
}

_SOLAR_IRRADIANCE = [4.2, 5.0, 5.8, 6.5, 7.0, 7.2, 7.0, 6.8, 6.2, 5.5, 4.5, 4.0]


def get_monthly_readings(year: int = 2026) -> List[WaterReading]:
    """Return 12 WaterReading objects, one per month."""
    readings = []
    for m in range(12):
        readings.append(WaterReading(
            timestamp=datetime(year, m + 1, 15),
            ph=_MONTHLY["ph"][m],
            do=_MONTHLY["do"][m],
            tss=_MONTHLY["tss"][m],
            turbidity=_MONTHLY["turbidity"][m],
            cod=_MONTHLY["cod"][m],
            ammonia=_MONTHLY["ammonia"][m],
            phosphate=_MONTHLY["phosphate"][m],
            oil_grease=_MONTHLY["oil_grease"][m],
            ecoli=_MONTHLY["ecoli"][m],
            total_coliforms=_MONTHLY["coliforms"][m],
            chla=_MONTHLY["chla"][m],
            phycocyanin=_MONTHLY["phycocyanin"][m],
            salinity=_MONTHLY["salinity"][m],
            water_temp=_MONTHLY["water_temp"][m],
        ))
    return readings


def get_current_reading(month_index: int = 2) -> WaterReading:
    """Return a single 'current' reading (default: March)."""
    return get_monthly_readings()[month_index]


def get_monthly_table() -> dict:
    """Return raw monthly dict for direct table rendering."""
    return _MONTHLY


def get_solar_irradiance() -> List[float]:
    return list(_SOLAR_IRRADIANCE)


def get_sludge_zones() -> List[SludgeZone]:
    return [
        SludgeZone("Zone A — Inlet",        10, 2.5, date(2026, 1, 15)),
        SludgeZone("Zone B — Central",       10, 1.8, date(2026, 1, 15)),
        SludgeZone("Zone C — Deep Basin",    12, 3.2, date(2026, 1, 15)),
        SludgeZone("Zone D — Shallow Edge",   6, 2.0, date(2026, 1, 15)),
        SludgeZone("Zone E — Outlet",         8, 1.5, date(2026, 1, 15)),
    ]


# ── Temperature vs species dominance ──

TEMP_SPECIES_DOMINANCE = [
    {"month": "January",   "temp": 22, "cyano": "Far below",   "chloro": "Below",        "diatom": "Near optimum", "dominant": "Diatoms"},
    {"month": "February",  "temp": 23, "cyano": "Far below",   "chloro": "Below",        "diatom": "Near optimum", "dominant": "Diatoms"},
    {"month": "March",     "temp": 26, "cyano": "Below",       "chloro": "Near optimum", "diatom": "Above",        "dominant": "Chlorophytes / Diatoms"},
    {"month": "April",     "temp": 29, "cyano": "Near",        "chloro": "Above",        "diatom": "Above",        "dominant": "Chlorophytes → Cyano"},
    {"month": "May",       "temp": 31, "cyano": "AT OPTIMUM",  "chloro": "Above",        "diatom": "Far above",    "dominant": "Cyanobacteria"},
    {"month": "June",      "temp": 33, "cyano": "AT OPTIMUM",  "chloro": "Far above",    "diatom": "Far above",    "dominant": "Cyanobacteria"},
    {"month": "July",      "temp": 33, "cyano": "AT OPTIMUM",  "chloro": "Far above",    "diatom": "Far above",    "dominant": "Cyanobacteria"},
    {"month": "August",    "temp": 33, "cyano": "AT OPTIMUM",  "chloro": "Far above",    "diatom": "Far above",    "dominant": "Cyanobacteria"},
    {"month": "September", "temp": 32, "cyano": "Near",        "chloro": "Above",        "diatom": "Far above",    "dominant": "Cyanobacteria"},
    {"month": "October",   "temp": 29, "cyano": "Near",        "chloro": "Above",        "diatom": "Above",        "dominant": "Mixed → Chlorophytes"},
    {"month": "November",  "temp": 25, "cyano": "Below",       "chloro": "Near optimum", "diatom": "Near optimum", "dominant": "Chlorophytes / Diatoms"},
    {"month": "December",  "temp": 24, "cyano": "Far below",   "chloro": "Below",        "diatom": "AT OPTIMUM",   "dominant": "Diatoms"},
]

# ── Seasonal treatment calendar ──

TREATMENT_CALENDAR = [
    {"month": "January",   "phase": "Phase 1: Pre-load", "enzyme": "Higher initial dosing; Pelletised sludge", "aeration": "Low-intensity continuous", "ultrasound": "Preventive mode", "risk": "Low"},
    {"month": "February",  "phase": "Phase 1: Pre-load", "enzyme": "Continue elevated dosing", "aeration": "Low-intensity continuous", "ultrasound": "Preventive mode", "risk": "Low"},
    {"month": "March",     "phase": "Phase 1: Pre-load", "enzyme": "Final pre-load push", "aeration": "Increase to moderate", "ultrasound": "Begin adaptive freq", "risk": "Rising"},
    {"month": "April",     "phase": "Phase 2: Ramp",     "enzyme": "Shift to maintenance dosing", "aeration": "Moderate; Night boost begins", "ultrasound": "Cyano-targeted if needed", "risk": "Moderate"},
    {"month": "May",       "phase": "Phase 2: Ramp",     "enzyme": "Maintenance; Increase if Chl-a >15", "aeration": "75% capacity", "ultrasound": "Increase freq rotation", "risk": "High"},
    {"month": "June",      "phase": "Phase 3: Peak",     "enzyme": "Fortnightly species-specific blend", "aeration": "100% continuous", "ultrasound": "Maximum interactive", "risk": "VERY HIGH"},
    {"month": "July",      "phase": "Phase 3: Peak",     "enzyme": "Fortnightly protease-heavy for cyano", "aeration": "100% + emergency standby", "ultrasound": "Maximum all units", "risk": "CRITICAL"},
    {"month": "August",    "phase": "Phase 3: Peak",     "enzyme": "Fortnightly full-spectrum if Chl-a >30", "aeration": "100% + destratification", "ultrasound": "Maximum adaptive", "risk": "CRITICAL"},
    {"month": "September", "phase": "Phase 3: Peak",     "enzyme": "Continue fortnightly; Begin tapering", "aeration": "100%; Crash monitoring", "ultrasound": "Maximum; Watch for crash", "risk": "HIGH"},
    {"month": "October",   "phase": "Phase 4: Recovery",  "enzyme": "Reduce frequency; Residual biomass", "aeration": "Reduce to 75%", "ultrasound": "Step down to moderate", "risk": "Moderate"},
    {"month": "November",  "phase": "Phase 4: Recovery",  "enzyme": "Monthly maintenance; Sludge-targeted", "aeration": "Reduce to moderate", "ultrasound": "Preventive mode", "risk": "Low"},
    {"month": "December",  "phase": "Phase 4: Recovery",  "enzyme": "Monthly maintenance; Plan next year", "aeration": "Low-intensity continuous", "ultrasound": "Preventive; System maintenance", "risk": "Low"},
]
