"""Lagoon DECCA — MCP server.

Exposes the pure `core/` compliance + alert logic and the Supabase data
layer as agent tools, so field teams can log readings and query compliance
by *talking* to Claude instead of using a web form.

Run (stdio, for Claude Desktop / Cursor):
    cd dashboard
    SUPABASE_URL=...  SUPABASE_KEY=...  python agent_server.py

Optional: set FAH_SITE=Emaar to lock this server to a single site so a
field team can only write to their own lagoon.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

# Make core/, db/, data/ importable regardless of the working directory
# Claude Desktop / Cursor launch this script from (it won't cd here).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

from core.alert_engine import evaluate_alert_level
from core.calculations import check_all_compliance, compliance_summary
from core.constants import (
    ALERT_LABELS,
    MONTH_NAMES,
    TREATMENT_ACTIONS,
    AlertLevel,
)
from core.models import WaterReading

mcp = FastMCP("lagoon-decca")

# Optional single-site lock for a field team's install.
LOCKED_SITE = os.environ.get("FAH_SITE")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_reading(
    ph: float, do: float, tss: float, turbidity: float, cod: float,
    ammonia: float, phosphate: float, oil_grease: float, ecoli: float,
    total_coliforms: float, chla: float, phycocyanin: float,
    salinity: float, water_temp: float, when: datetime | None = None,
) -> WaterReading:
    return WaterReading(
        timestamp=when or datetime.now(),
        ph=ph, do=do, tss=tss, turbidity=turbidity, cod=cod,
        ammonia=ammonia, phosphate=phosphate, oil_grease=oil_grease,
        ecoli=ecoli, total_coliforms=total_coliforms, chla=chla,
        phycocyanin=phycocyanin, salinity=salinity, water_temp=water_temp,
    )


def _assess(reading: WaterReading) -> dict:
    """Run compliance + alert engine, return a structured assessment."""
    results = check_all_compliance(reading)
    summary = compliance_summary(results)
    alert = evaluate_alert_level(reading)
    level = AlertLevel(alert.level)
    tx = TREATMENT_ACTIONS[level]
    return {
        "compliance": {
            "overall_status": summary["overall_status"],
            "compliance_pct": summary["compliance_pct"],
            "failing_params": summary["failing_params"],
            "min_margin_pct": summary["min_margin"],
            "per_parameter": [
                {
                    "parameter": r.parameter_name,
                    "value": r.value,
                    "unit": r.unit,
                    "limit": r.limit_display,
                    "compliant": r.compliant,
                    "margin_pct": r.margin_pct,
                    "risk": r.risk_level,
                }
                for r in results
            ],
        },
        "alert": {
            "level": int(level),
            "label": ALERT_LABELS[level],
            "bloom_probability_pct": alert.bloom_probability,
            "dominant_species": alert.dominant_species,
            "drivers": alert.top_drivers,
        },
        "treatment_response": {
            "enzyme": tx.enzyme,
            "aeration": tx.aeration,
            "ultrasound": tx.ultrasound,
            "monitoring": tx.monitoring,
            "do_not": tx.do_not,
        },
    }


def _resolve_site(site: str | None) -> str:
    if LOCKED_SITE:
        return LOCKED_SITE
    if not site:
        raise ValueError(
            "No site given. Provide `site`, or set FAH_SITE to lock this server."
        )
    return site


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_sites() -> dict:
    """List the lagoon sites this server can write to."""
    if LOCKED_SITE:
        return {"sites": [LOCKED_SITE], "locked": True}
    try:
        from db.queries import get_site_names
        names = get_site_names()
    except Exception:
        names = []
    return {"sites": names, "locked": False}


@mcp.tool()
def assess_reading(
    ph: float, do: float, tss: float, turbidity: float, cod: float,
    ammonia: float, phosphate: float, oil_grease: float, ecoli: float,
    total_coliforms: float, chla: float, phycocyanin: float,
    salinity: float, water_temp: float,
) -> dict:
    """Check a set of water-quality values against DECCA limits and the alert
    engine WITHOUT saving. Returns compliance status, alert level, and the
    recommended treatment response. Use this to sanity-check before logging.

    Units: ph (pH), do/tss/cod/ammonia/phosphate/oil_grease (mg/L),
    turbidity (NTU), ecoli/total_coliforms (CFU/100mL),
    chla/phycocyanin (µg/L), salinity (PSU), water_temp (°C).
    """
    reading = _build_reading(
        ph, do, tss, turbidity, cod, ammonia, phosphate, oil_grease,
        ecoli, total_coliforms, chla, phycocyanin, salinity, water_temp,
    )
    return _assess(reading)


@mcp.tool()
def log_reading(
    year: int, month: int,
    ph: float, do: float, tss: float, turbidity: float, cod: float,
    ammonia: float, phosphate: float, oil_grease: float, ecoli: float,
    total_coliforms: float, chla: float, phycocyanin: float,
    salinity: float, water_temp: float,
    site: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Save a monthly water-quality reading for a site to the database, then
    return the DECCA compliance assessment + alert level + treatment response.

    `month` is 1–12. Set `overwrite=True` to replace an existing reading for
    the same site/year/month. If the server is locked to a site via FAH_SITE,
    the `site` argument is ignored.
    """
    resolved = _resolve_site(site)
    if not (1 <= month <= 12):
        raise ValueError("month must be 1–12")

    reading = _build_reading(
        ph, do, tss, turbidity, cod, ammonia, phosphate, oil_grease,
        ecoli, total_coliforms, chla, phycocyanin, salinity, water_temp,
        when=datetime(year, month, 15),
    )
    assessment = _assess(reading)

    fields = {
        "ph": ph, "do_mgl": do, "tss_mgl": tss, "turbidity_ntu": turbidity,
        "cod_mgl": cod, "ammonia_mgl": ammonia, "phosphate_mgl": phosphate,
        "oil_grease_mgl": oil_grease, "ecoli_cfu": ecoli,
        "total_coliforms_cfu": total_coliforms, "chla_ugl": chla,
        "phycocyanin_ugl": phycocyanin, "salinity_psu": salinity,
        "water_temp_c": water_temp,
    }
    from db.queries import insert_reading
    ok, msg = insert_reading(resolved, year, month, fields, upsert=overwrite)

    return {
        "saved": ok,
        "message": msg,
        "site": resolved,
        "period": f"{MONTH_NAMES[month - 1]} {year}",
        "assessment": assessment,
    }


@mcp.tool()
def get_site_status(site: str | None = None, year: int = 2026) -> dict:
    """Return all stored readings for a site this year, each with its DECCA
    compliance status and alert level. Use this to answer 'is <site>
    compliant?' or 'what's the trend at <site>?'.
    """
    resolved = _resolve_site(site)
    from db.queries import get_readings_for_site
    readings = get_readings_for_site(resolved, year=year)
    if not readings:
        return {"site": resolved, "year": year, "readings": [],
                "note": "No readings stored yet for this site/year."}
    months = []
    for r in readings:
        a = _assess(r)
        months.append({
            "month": MONTH_NAMES[r.timestamp.month - 1],
            "compliance": a["compliance"]["overall_status"],
            "compliance_pct": a["compliance"]["compliance_pct"],
            "alert_level": a["alert"]["level"],
            "alert_label": a["alert"]["label"],
            "failing_params": a["compliance"]["failing_params"],
        })
    return {"site": resolved, "year": year, "readings": months}


@mcp.tool()
def get_treatment_protocol(alert_level: int) -> dict:
    """Return the treatment protocol (enzyme / aeration / ultrasound /
    monitoring) for a given alert level (1=GREEN, 2=WATCH, 3=WARNING,
    4=CRITICAL).
    """
    if alert_level not in (1, 2, 3, 4):
        raise ValueError("alert_level must be 1, 2, 3, or 4")
    level = AlertLevel(alert_level)
    tx = TREATMENT_ACTIONS[level]
    return {
        "alert_level": alert_level,
        "label": ALERT_LABELS[level],
        "enzyme": tx.enzyme,
        "aeration": tx.aeration,
        "ultrasound": tx.ultrasound,
        "monitoring": tx.monitoring,
        "do_not": tx.do_not,
    }


# ── Science engine tools (v2) — additive; existing tools unchanged ───────────

@mcp.tool()
def diagnose_lagoon(
    temperature: float, phosphate: float, ammonia: float,
    dissolved_oxygen: float, salinity: float,
    nitrate: float = 0.0,
    volume_m3: float = 0.0, inflow_m3_day: float = 0.0,
    outflow_m3_day: float = 0.0, recirculation_m3_day: float = 0.0,
    orp: float | None = None, sediment_state: str = "normal",
    recent_rainfall: bool = False, dust_event: bool = False,
    tse_inflow_high: bool = False, salinity_baseline: float = 45.0,
    historical_bloom_count: int = 0,
) -> dict:
    """Run the full scientific chain and explain WHY a lagoon is at risk.

    Returns nutrient source attribution, Fe-P internal sediment loading,
    hydraulic residence time, bloom forecast (probability/severity/recovery),
    and a ranked list of management interventions — each with reasoning.

    Provide hydraulics (volume_m3, inflow/outflow) to enable residence-time
    and intervention ranking. sediment_state: mineral/normal/organic/post_bloom.
    Use this to answer 'why is my lagoon turning green and what should I do?'.
    """
    from science.diagnose import diagnose
    return diagnose(
        temperature=temperature, phosphate=phosphate, ammonia=ammonia,
        dissolved_oxygen=dissolved_oxygen, salinity=salinity, nitrate=nitrate,
        volume_m3=volume_m3, inflow_m3_day=inflow_m3_day,
        outflow_m3_day=outflow_m3_day, recirculation_m3_day=recirculation_m3_day,
        orp=orp, sediment_state=sediment_state, recent_rainfall=recent_rainfall,
        dust_event=dust_event, tse_inflow_high=tse_inflow_high,
        salinity_baseline=salinity_baseline,
        historical_bloom_count=historical_bloom_count,
        include_interventions=True,
    )


@mcp.tool()
def simulate_intervention(
    intervention: str,
    temperature: float, phosphate: float, ammonia: float,
    dissolved_oxygen: float, salinity: float,
    volume_m3: float = 0.0, inflow_m3_day: float = 0.0,
    outflow_m3_day: float = 0.0, recirculation_m3_day: float = 0.0,
    orp: float | None = None, sediment_state: str = "normal",
    historical_bloom_count: int = 0, magnitude: float = 0.5,
) -> dict:
    """Digital twin — simulate ONE management intervention and predict its
    effect on bloom probability + timeline.

    intervention: reduce_phosphate | increase_circulation | remove_sludge |
                  reduce_residence_time
    magnitude: 0–1 strength (e.g. 0.5 = 'reduce phosphate by 50%').
    """
    from science.digital_twin import LagoonState, simulate
    from dataclasses import asdict
    state = LagoonState(
        temperature=temperature, phosphate=phosphate, ammonia=ammonia,
        dissolved_oxygen=dissolved_oxygen, salinity=salinity,
        volume_m3=volume_m3, inflow_m3_day=inflow_m3_day,
        outflow_m3_day=outflow_m3_day, recirculation_m3_day=recirculation_m3_day,
        orp=orp, sediment_state=sediment_state,
        historical_bloom_count=historical_bloom_count,
    )
    return asdict(simulate(state, intervention, magnitude))


if __name__ == "__main__":
    mcp.run()
