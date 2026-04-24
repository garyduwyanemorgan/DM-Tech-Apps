"""Alert level evaluation and escalation logic.

Pure computation — no UI. Determines current alert level from sensor readings
and applies escalation / de-escalation rules.
"""
from typing import List, Optional, Tuple

from .constants import AlertLevel
from .models import AlertState, WaterReading


def evaluate_alert_level(reading: WaterReading) -> AlertState:
    """Determine current alert level from a water quality reading.

    Escalation is automatic and fast; the *caller* is responsible
    for applying de-escalation hold periods.
    """
    level = AlertLevel.GREEN
    reasons: List[str] = []

    chla = reading.chla
    do = reading.do
    phyco = reading.phycocyanin
    temp = reading.water_temp

    # ── Level 4 triggers (any one is sufficient) ──
    if chla > 75:
        level = AlertLevel.CRITICAL
        reasons.append(f"Chl-a {chla} µg/L > 75")
    if do < 2:
        level = AlertLevel.CRITICAL
        reasons.append(f"DO {do} mg/L < 2 (hypoxia)")
    # Toxin detection would be an external input

    # ── Level 3 triggers (if not already 4) ──
    if level < AlertLevel.WARNING:
        if chla > 30:
            level = AlertLevel.WARNING
            reasons.append(f"Chl-a {chla} µg/L > 30")
        if do < 3:
            level = AlertLevel.WARNING
            reasons.append(f"DO {do} mg/L < 3")
        if phyco > 200:
            level = AlertLevel.WARNING
            reasons.append(f"Phycocyanin {phyco} µg/L > 200")

    # ── Level 2 triggers ──
    if level < AlertLevel.WATCH:
        if 10 <= chla <= 30:
            level = AlertLevel.WATCH
            reasons.append(f"Chl-a {chla} µg/L in 10–30 range")
        if do < 4:
            level = AlertLevel.WATCH
            reasons.append(f"DO {do} mg/L < 4")
        if phyco > 50:
            level = AlertLevel.WATCH
            reasons.append(f"Phycocyanin {phyco} µg/L > 50")
        if temp > 28:
            level = AlertLevel.WATCH
            reasons.append(f"Water temp {temp}°C > 28")

    # ── DECCA compliance override ──
    decca_breach = _check_decca_breach(reading)
    if decca_breach and level < AlertLevel.WARNING:
        level = AlertLevel.WARNING
        reasons.append(f"DECCA breach: {decca_breach}")

    # ── Species classification ──
    if reading.chla > 0.1:
        ratio = reading.phycocyanin / reading.chla
        species = "Cyanobacteria" if ratio > 0.5 else "Other (dino/diatom/green)"
    else:
        species = "No bloom"

    # ── Bloom probability (sigmoid) ──
    import math
    bloom_prob = round(100 / (1 + math.exp(-0.15 * (chla - 30))), 1)

    return AlertState(
        level=level,
        bloom_probability=bloom_prob,
        dominant_species=species,
        top_drivers=reasons[:5],
        escalation_reason=reasons[0] if reasons else None,
    )


def _check_decca_breach(r: WaterReading) -> Optional[str]:
    """Return the name of the first breached DECCA parameter, or None."""
    if not (6.0 <= r.ph <= 9.0):
        return f"pH {r.ph}"
    if r.do <= 4.0:
        return f"DO {r.do} mg/L"
    if r.tss >= 50:
        return f"TSS {r.tss} mg/L"
    if r.turbidity >= 75:
        return f"Turbidity {r.turbidity} NTU"
    if r.cod >= 50:
        return f"COD {r.cod} mg/L"
    if r.ammonia >= 5.0:
        return f"Ammonia {r.ammonia} mg/L"
    if r.phosphate >= 5.0:
        return f"Phosphate {r.phosphate} mg/L"
    if r.oil_grease >= 10:
        return f"O&G {r.oil_grease} mg/L"
    if r.ecoli >= 200:
        return f"E. coli {r.ecoli} CFU"
    if r.total_coliforms >= 1000:
        return f"Coliforms {r.total_coliforms} CFU"
    return None


# ── De-escalation rules (hold periods) ──

DE_ESCALATION_RULES = {
    (4, 3): {"condition": "Chl-a < 30 for 48 continuous hours", "hold_hours": 48},
    (3, 2): {"condition": "Chl-a < 10 for 72 continuous hours", "hold_hours": 72},
    (2, 1): {"condition": "All parameters green for 7 days",    "hold_hours": 168},
}

ESCALATION_OVERRIDES = [
    {"trigger": "Any DECCA threshold breach",  "min_level": 3, "response": "Immediate"},
    {"trigger": "Toxin detection (any level)", "min_level": 4, "response": "Immediate"},
    {"trigger": "DO < 2 mg/L for > 2 hours",  "min_level": 4, "response": "Immediate"},
]

SPECIAL_EVENTS = [
    {"event": "Dust Storm Forecast (48hr)", "response": "Pre-emptive Level 2",
     "action": "Nutrient competition dose"},
    {"event": "TSE Quality Failure",        "response": "Immediate Level 3",
     "action": "Emergency nutrient binding + aeration boost"},
    {"event": "Sudden Bloom Crash (>50% Chl-a drop in 24hr)",
     "response": "Emergency protocol",
     "action": "Emergency aeration + enzyme dose"},
]
