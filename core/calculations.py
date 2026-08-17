"""Pure computation — compliance checks, bloom probability, margins.

Every function is deterministic: same inputs → same outputs.
No Streamlit, no IO, no side effects.
"""
import math
from typing import Dict, List

from .constants import COMPLIANCE_LIMITS, ComplianceLimit
from .models import ComplianceResult, WaterReading


# ── Compliance ──

def check_compliance(key: str, value: float | None) -> ComplianceResult:
    """Check a single parameter against its compliance limit.

    `value` may be None: `insert_reading` accepts a partial `fields` dict, so a
    reading can legitimately carry only some of the parameters. Such a
    parameter gets a result with `measured=False` and no verdict — it is
    neither a pass nor a breach, and the caller must not read it as either.
    """
    lim = COMPLIANCE_LIMITS[key]
    if value is None:
        # Not measured. `compliant=False` here is a placeholder the summary
        # excludes, never a compliance claim — see compliance_summary, which
        # counts these separately and refuses to call the reading COMPLIANT.
        return ComplianceResult(
            parameter_key=key,
            parameter_name=lim.parameter,
            value=None,
            unit=lim.unit,
            limit_display=lim.display,
            compliant=False,
            margin_pct=0.0,
            risk_level="UNKNOWN",
            measured=False,
        )

    compliant = True
    margin_pct = 0.0

    if lim.min_val is not None and lim.max_val is not None:
        # Range check (pH)
        compliant = lim.min_val <= value <= lim.max_val
        range_size = lim.max_val - lim.min_val
        margin_pct = min(value - lim.min_val, lim.max_val - value) / range_size * 100
    elif lim.min_val is not None:
        # Lower bound (DO)
        compliant = value > lim.min_val
        margin_pct = (value - lim.min_val) / lim.min_val * 100
    elif lim.max_val is not None:
        # Upper bound (TSS, COD, etc.)
        compliant = value < lim.max_val
        margin_pct = (lim.max_val - value) / lim.max_val * 100

    if margin_pct > 30:
        risk = "LOW"
    elif margin_pct > 10:
        risk = "MODERATE"
    else:
        risk = "HIGH"

    return ComplianceResult(
        parameter_key=key,
        parameter_name=lim.parameter,
        value=value,
        unit=lim.unit,
        limit_display=lim.display,
        compliant=compliant,
        margin_pct=round(margin_pct, 1),
        risk_level=risk,
    )


def check_all_compliance(reading: WaterReading) -> List[ComplianceResult]:
    """Check all Compliance parameters for a single reading."""
    params = reading.as_dict()
    return [check_compliance(k, v) for k, v in params.items()]


def compliance_summary(results: List[ComplianceResult]) -> Dict:
    """Aggregate compliance results into summary stats.

    Unmeasured parameters are their own bucket and are excluded from the
    pass/fail arithmetic. They are NOT counted as failures — no laboratory
    claimed a breach — and a reading missing any parameter is reported as
    INCOMPLETE rather than COMPLIANT.

    That last part is the point. Averaging over only the parameters that
    happen to be present would report a reading with one measured value out of
    ten as "100% COMPLIANT", which is a compliance claim nobody made, on
    regulated data. This follows the rule already stated for certificate
    verdicts in db/queries.py's _compliance_kpi: INCOMPLETE is its own bucket.
    """
    measured = [r for r in results if r.measured]
    missing = [r for r in results if not r.measured]

    total = len(results)
    passing = sum(1 for r in measured if r.compliant)
    failing = [r for r in measured if not r.compliant]

    if missing:
        overall = "INCOMPLETE"
    elif measured and passing == len(measured):
        overall = "COMPLIANT"
    elif not measured:
        # Nothing was measured at all — not a pass by any reading of it.
        overall = "INCOMPLETE"
    else:
        overall = "NON-COMPLIANT"

    return {
        "total": total,
        "measured_count": len(measured),
        "passing": passing,
        "failing_count": len(failing),
        "failing_params": [r.parameter_name for r in failing],
        "missing_count": len(missing),
        "missing_params": [r.parameter_name for r in missing],
        # Percentage of what was actually measured. Read it alongside
        # missing_count or it flatters an incomplete reading.
        "compliance_pct": round(passing / len(measured) * 100, 1) if measured else 0,
        "overall_status": overall,
        "min_margin": min((r.margin_pct for r in measured), default=0),
    }


# ── Bloom Probability ──

def bloom_probability(chla: float, threshold: float = 30, steepness: float = 0.15) -> float:
    """Sigmoid-calibrated bloom probability (0–100%)."""
    return round(100 / (1 + math.exp(-steepness * (chla - threshold))), 1)


def species_classification(phycocyanin: float, chla: float) -> str:
    """Determine dominant species regime from sensor ratio."""
    if chla < 0.1:
        return "No bloom"
    ratio = phycocyanin / chla
    if ratio > 0.5:
        return "Cyanobacteria dominant"
    return "Other (dinoflagellates / diatoms / green)"


# ── Margin & Trend Helpers ──

def trend_arrow(current: float, previous: float, tolerance: float = 0.02) -> str:
    """Return trend indicator comparing current to previous."""
    if previous == 0:
        return "→"
    pct_change = (current - previous) / abs(previous)
    if pct_change > tolerance:
        return "↑"
    if pct_change < -tolerance:
        return "↓"
    return "→"


def do_saturation(temp_c: float) -> float:
    """Approximate DO saturation (mg/L) at a given water temperature (°C).
    Simplified Benson-Krause relationship for freshwater at sea level.
    """
    return round(14.62 - 0.3898 * temp_c + 0.006969 * temp_c**2 - 0.00005897 * temp_c**3, 1)


def capacity_loss(total_depth: float, sludge_depth: float) -> float:
    """Calculate sludge capacity loss percentage."""
    if total_depth <= 0:
        return 0
    return round((sludge_depth / total_depth) * 100, 1)


def monthly_compliance_rate(compliant_months: int, total_months: int = 12) -> float:
    """Annualised compliance rate."""
    if total_months == 0:
        return 0
    return round(compliant_months / total_months * 100, 1)
