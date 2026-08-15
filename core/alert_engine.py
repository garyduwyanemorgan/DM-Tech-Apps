"""Alert level evaluation and escalation logic.

Pure computation — no UI. Determines current alert level from sensor readings
and applies escalation / de-escalation rules.
"""
from typing import List, Optional, Tuple

from .constants import COMPLIANCE_LIMITS, AlertLevel
from .specs import NON_COMPLIANT, judge, lagoon_spec_set
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

    # ── compliance override ──
    compliance_breach = _check_compliance_breach(reading)
    if compliance_breach and level < AlertLevel.WARNING:
        level = AlertLevel.WARNING
        reasons.append(f"Compliance breach: {compliance_breach}")

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


# The wording the old inline copy used, kept verbatim: these strings reach the
# user as an escalation reason, and consolidating the LOGIC should not quietly
# reword the OUTPUT.
# (label, unit-suffix) exactly as the inline copy printed them. The suffixes are
# NOT SpecLimit.unit: the old messages said "CFU" where the limit's unit is
# "CFU/100mL", and pH carried no unit at all where the limit says "pH Units". A
# differential run over 432 readings caught that difference — the verdicts and
# their precedence were identical, only the wording had drifted.
_BREACH_TEXT = {
    "ph":              ("pH", ""),
    "do":              ("DO", " mg/L"),
    "tss":             ("TSS", " mg/L"),
    "turbidity":       ("Turbidity", " NTU"),
    "cod":             ("COD", " mg/L"),
    "ammonia":         ("Ammonia", " mg/L"),
    "phosphate":       ("Phosphate", " mg/L"),
    "oil_grease":      ("O&G", " mg/L"),
    "ecoli":           ("E. coli", " CFU"),
    "total_coliforms": ("Coliforms", " CFU"),
}


def _check_compliance_breach(r: WaterReading) -> Optional[str]:
    """Return the name of the first breached Compliance parameter, or None.

    This used to carry its own inline copy of all ten limits — the second of the
    eight verdict implementations §5 catalogues. The copy agreed with
    core/calculations.py on every value and every operator, so retiring it changes
    no verdict; what it removes is the certainty that it would eventually stop
    agreeing.

    Judging now goes through core/specs.py, the same resolver that judges
    database-backed sets, so a limit corrected in core/constants.py reaches the
    alert engine without anybody remembering to update it here.

    Ordering is preserved deliberately: this returns the FIRST breach, and the
    escalation reason a user sees depends on which. COMPLIANCE_LIMITS is ordered,
    and iterating it keeps the previous precedence exactly.
    """
    spec = lagoon_spec_set()
    for key in COMPLIANCE_LIMITS:
        value = getattr(r, key, None)
        if value is None:
            continue
        if judge(value, spec, parameter_key=key) == NON_COMPLIANT:
            label, unit = _BREACH_TEXT.get(
                key, (spec.limits[key].parameter_label, ""))
            return f"{label} {value}{unit}"
    return None


# ── De-escalation rules (hold periods) ──

DE_ESCALATION_RULES = {
    (4, 3): {"condition": "Chl-a < 30 for 48 continuous hours", "hold_hours": 48},
    (3, 2): {"condition": "Chl-a < 10 for 72 continuous hours", "hold_hours": 72},
    (2, 1): {"condition": "All parameters green for 7 days",    "hold_hours": 168},
}

ESCALATION_OVERRIDES = [
    {"trigger": "Any Compliance threshold breach",  "min_level": 3, "response": "Immediate"},
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
