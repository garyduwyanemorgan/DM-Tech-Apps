"""Lagoon DECCA — FastAPI HTTP server.

Exposes the same compliance + alert logic as the MCP server but over
HTTP, so Sakhile's Vonage/n8n voice pipeline can call it with a simple
HTTP Request node.

Run locally:
    cd dashboard
    SUPABASE_URL=... SUPABASE_KEY=... python -m uvicorn api_server:app --reload --port 8000

Production (background):
    uvicorn api_server:app --host 0.0.0.0 --port 8000

Endpoints:
    GET  /health                   — liveness check
    GET  /sites                    — list configured sites
    POST /assess                   — check readings, no save
    POST /log                      — save reading + return assessment
    GET  /status/{site}            — all readings for a site this year
    GET  /tools                    — OpenAPI-style tool schemas (for Claude tool use in n8n)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Optional

# Make core/, db/, data/ importable regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

from core.alert_engine import evaluate_alert_level
from core.calculations import check_all_compliance, compliance_summary
from core.constants import ALERT_LABELS, MONTH_NAMES, TREATMENT_ACTIONS, AlertLevel
from core.models import WaterReading

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Lagoon DECCA API",
    description="Water quality compliance + alert engine for Dubai lagoon field teams.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten to n8n host in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Optional API key auth (set API_KEY env var to enable) ────────────────────

_API_KEY = os.environ.get("API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _check_key(key: str | None = Security(api_key_header)):
    if _API_KEY and key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ReadingFields(BaseModel):
    ph:               float = Field(..., description="pH units (DECCA: 6.0–9.0)")
    do:               float = Field(..., description="Dissolved oxygen mg/L (DECCA: >4.0)")
    tss:              float = Field(..., description="Total suspended solids mg/L (DECCA: <50)")
    turbidity:        float = Field(..., description="Turbidity NTU (DECCA: <75)")
    cod:              float = Field(..., description="Chemical oxygen demand mg/L (DECCA: <50)")
    ammonia:          float = Field(..., description="Ammonia as N mg/L (DECCA: <5.0)")
    phosphate:        float = Field(..., description="Total phosphate mg/L (DECCA: <5.0)")
    oil_grease:       float = Field(..., description="Oils & grease mg/L (DECCA: <10)")
    ecoli:            float = Field(..., description="E. coli CFU/100mL (DECCA: <200)")
    total_coliforms:  float = Field(..., description="Total coliforms CFU/100mL (DECCA: <1000)")
    chla:             float = Field(..., description="Chlorophyll-a µg/L (bloom watch >10)")
    phycocyanin:      float = Field(..., description="Phycocyanin µg/L (cyano watch >50)")
    salinity:         float = Field(..., description="Salinity PSU (typical 40–60)")
    water_temp:       float = Field(..., description="Water temperature °C (typical 22–33)")


class AssessRequest(ReadingFields):
    pass


class LogRequest(ReadingFields):
    site:      str           = Field(..., description="Site name, e.g. 'Emaar'")
    year:      int           = Field(..., description="Reading year, e.g. 2026")
    month:     int           = Field(..., ge=1, le=12, description="Reading month 1–12")
    overwrite: bool          = Field(False, description="Replace existing reading for same site/month")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_reading(f: ReadingFields, when: datetime | None = None) -> WaterReading:
    return WaterReading(
        timestamp=when or datetime.now(),
        ph=f.ph, do=f.do, tss=f.tss, turbidity=f.turbidity,
        cod=f.cod, ammonia=f.ammonia, phosphate=f.phosphate,
        oil_grease=f.oil_grease, ecoli=f.ecoli,
        total_coliforms=f.total_coliforms, chla=f.chla,
        phycocyanin=f.phycocyanin, salinity=f.salinity, water_temp=f.water_temp,
    )


def _assess(reading: WaterReading) -> dict:
    results = check_all_compliance(reading)
    summary = compliance_summary(results)
    alert   = evaluate_alert_level(reading)
    level   = AlertLevel(alert.level)
    tx      = TREATMENT_ACTIONS[level]
    return {
        "compliance": {
            "overall_status":  summary["overall_status"],
            "compliance_pct":  summary["compliance_pct"],
            "failing_params":  summary["failing_params"],
            "min_margin_pct":  summary["min_margin"],
            "per_parameter": [
                {
                    "parameter": r.parameter_name,
                    "value":     r.value,
                    "unit":      r.unit,
                    "limit":     r.limit_display,
                    "compliant": r.compliant,
                    "margin_pct":r.margin_pct,
                    "risk":      r.risk_level,
                }
                for r in results
            ],
        },
        "alert": {
            "level":                int(level),
            "label":                ALERT_LABELS[level],
            "bloom_probability_pct":alert.bloom_probability,
            "dominant_species":     alert.dominant_species,
            "drivers":              alert.top_drivers,
        },
        "treatment_response": {
            "enzyme":     tx.enzyme,
            "aeration":   tx.aeration,
            "ultrasound": tx.ultrasound,
            "monitoring": tx.monitoring,
            "do_not":     tx.do_not,
        },
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    """Liveness check. Returns ok when the server is running."""
    return {"status": "ok", "service": "lagoon-decca-api"}


@app.get("/sites", tags=["System"])
def list_sites():
    """Return configured site names (from Supabase secrets / env)."""
    try:
        from db.queries import get_site_names
        sites = get_site_names()
    except Exception:
        sites = []
    return {"sites": sites}


@app.post("/assess", tags=["Compliance"])
def assess(body: AssessRequest, _=Security(_check_key)):
    """Check a set of readings against DECCA limits and the alert engine.
    Does NOT save to the database — use this to validate before logging,
    or when a field team just wants a quick compliance check.
    """
    reading = _build_reading(body)
    return _assess(reading)


@app.post("/log", tags=["Compliance"])
def log_reading(body: LogRequest, _=Security(_check_key)):
    """Save a monthly reading for a site, then return the full DECCA
    compliance assessment, alert level, and treatment response.
    This is the primary endpoint for Sakhile's n8n voice pipeline.
    """
    if not (1 <= body.month <= 12):
        raise HTTPException(status_code=422, detail="month must be 1–12")

    reading = _build_reading(body, when=datetime(body.year, body.month, 15))
    assessment = _assess(reading)

    fields = {
        "ph": body.ph, "do_mgl": body.do, "tss_mgl": body.tss,
        "turbidity_ntu": body.turbidity, "cod_mgl": body.cod,
        "ammonia_mgl": body.ammonia, "phosphate_mgl": body.phosphate,
        "oil_grease_mgl": body.oil_grease, "ecoli_cfu": body.ecoli,
        "total_coliforms_cfu": body.total_coliforms, "chla_ugl": body.chla,
        "phycocyanin_ugl": body.phycocyanin, "salinity_psu": body.salinity,
        "water_temp_c": body.water_temp,
    }

    try:
        from db.queries import insert_reading
        ok, msg = insert_reading(body.site, body.year, body.month, fields, upsert=body.overwrite)
    except Exception as exc:
        ok, msg = False, str(exc)

    return {
        "saved":      ok,
        "message":    msg,
        "site":       body.site,
        "period":     f"{MONTH_NAMES[body.month - 1]} {body.year}",
        "assessment": assessment,
    }


@app.get("/status/{site}", tags=["Compliance"])
def site_status(site: str, year: int = 2026, _=Security(_check_key)):
    """Return all stored readings for a site in a given year, each with
    its compliance status and alert level. Use this in n8n to answer
    'is Emaar compliant this year?' after logging.
    """
    try:
        from db.queries import get_readings_for_site
        readings = get_readings_for_site(site, year=year)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not readings:
        return {"site": site, "year": year, "readings": [],
                "note": "No readings stored yet."}

    months = []
    for r in readings:
        a = _assess(r)
        months.append({
            "month":           MONTH_NAMES[r.timestamp.month - 1],
            "compliance":      a["compliance"]["overall_status"],
            "compliance_pct":  a["compliance"]["compliance_pct"],
            "alert_level":     a["alert"]["level"],
            "alert_label":     a["alert"]["label"],
            "failing_params":  a["compliance"]["failing_params"],
        })

    return {"site": site, "year": year, "readings": months}


@app.get("/tools", tags=["System"])
def tool_schemas():
    """Return OpenAPI-style tool definitions for use with Claude API
    tool use in n8n. Pass these as the `tools` array in the Anthropic
    Messages API call so Claude knows what our endpoints accept.
    """
    return {
        "tools": [
            {
                "name": "assess_reading",
                "description": "Check water quality values against DECCA limits. No save.",
                "endpoint": "POST /assess",
                "input_schema": AssessRequest.model_json_schema(),
            },
            {
                "name": "log_reading",
                "description": "Save a monthly reading and return DECCA compliance + alert level.",
                "endpoint": "POST /log",
                "input_schema": LogRequest.model_json_schema(),
            },
            {
                "name": "get_site_status",
                "description": "Get all readings for a site this year with compliance status.",
                "endpoint": "GET /status/{site}",
            },
            {
                "name": "diagnose_lagoon",
                "description": "Run the full scientific chain: nutrient source, internal loading, residence time, bloom forecast + interventions.",
                "endpoint": "POST /science/diagnose",
            },
            {
                "name": "simulate_intervention",
                "description": "Digital twin: simulate a management intervention and predict bloom reduction.",
                "endpoint": "POST /science/simulate",
            },
        ]
    }


# ════════════════════════════════════════════════════════════════════════════
# SCIENCE ENGINES (v2) — additive endpoints. v1 routes above are unchanged.
# ════════════════════════════════════════════════════════════════════════════

class DiagnoseRequest(BaseModel):
    # Core chemistry (from a WaterReading)
    temperature:      float = Field(..., description="Water temperature °C")
    phosphate:        float = Field(..., description="Phosphate mg/L")
    ammonia:          float = Field(..., description="Ammonia as N mg/L")
    dissolved_oxygen: float = Field(..., description="DO mg/L")
    salinity:         float = Field(..., description="Salinity PSU")
    nitrate:          float = Field(0.0, description="Nitrate as N mg/L (optional)")
    # Hydraulics (optional — enables residence time + interventions)
    volume_m3:            float = Field(0.0, description="Lagoon volume m³")
    inflow_m3_day:        float = Field(0.0, description="Inflow m³/day")
    outflow_m3_day:       float = Field(0.0, description="Outflow m³/day")
    recirculation_m3_day: float = Field(0.0, description="Recirculation m³/day")
    # Sediment
    orp:            Optional[float] = Field(None, description="Redox potential mV (optional)")
    sediment_state: str = Field("normal", description="mineral / normal / organic / post_bloom")
    # Context flags
    recent_rainfall:  bool  = Field(False, description="Recent rainfall")
    dust_event:       bool  = Field(False, description="Recent dust/sandstorm")
    tse_inflow_high:  bool  = Field(False, description="Measured high TSE inflow")
    salinity_baseline:float = Field(45.0, description="Site baseline salinity PSU")
    historical_bloom_count: int = Field(0, description="Prior blooms at the site")
    include_interventions:  bool  = Field(True, description="Rank digital-twin interventions")
    intervention_magnitude: float = Field(0.5, description="Intervention strength 0–1")


class SimulateRequest(DiagnoseRequest):
    intervention: str = Field(..., description="reduce_phosphate / increase_circulation / remove_sludge / reduce_residence_time")


@app.post("/science/diagnose", tags=["Science"])
def science_diagnose(body: DiagnoseRequest, _=Security(_check_key)):
    """Run the full scientific chain for a reading and return an explainable
    diagnosis: nutrient source attribution, Fe-P internal loading, residence
    time, bloom forecast, and (optionally) a ranked list of interventions.

    Answers the operator question 'why is my lagoon turning green, and what
    should I do?'.
    """
    from science.diagnose import diagnose
    return diagnose(**body.model_dump())


@app.post("/science/simulate", tags=["Science"])
def science_simulate(body: SimulateRequest, _=Security(_check_key)):
    """Digital twin — simulate a single management intervention against the
    given state and predict the bloom-probability change and timeline.
    """
    from science.digital_twin import LagoonState, simulate
    from dataclasses import asdict
    data = body.model_dump()
    intervention = data.pop("intervention")
    magnitude = data.get("intervention_magnitude", 0.5)
    state = LagoonState(
        temperature=data["temperature"], phosphate=data["phosphate"],
        ammonia=data["ammonia"], dissolved_oxygen=data["dissolved_oxygen"],
        salinity=data["salinity"], volume_m3=data["volume_m3"],
        inflow_m3_day=data["inflow_m3_day"], outflow_m3_day=data["outflow_m3_day"],
        recirculation_m3_day=data["recirculation_m3_day"], orp=data["orp"],
        sediment_state=data["sediment_state"],
        historical_bloom_count=data["historical_bloom_count"],
    )
    try:
        return asdict(simulate(state, intervention, magnitude))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/science/interventions", tags=["Science"])
def science_interventions():
    """List the digital-twin interventions the simulator supports."""
    from science.config import DIGITAL_TWIN_INTERVENTIONS
    return {
        "interventions": [
            {"key": iv.key, "label": iv.label,
             "time_to_effect_days": iv.time_to_effect_days,
             "description": iv.description}
            for iv in DIGITAL_TWIN_INTERVENTIONS.values()
        ]
    }
