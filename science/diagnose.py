"""Full-chain diagnosis orchestrator.

Single entry point that runs the whole scientific chain (Engines 1–4) for a
lagoon reading and, optionally, ranks digital-twin interventions (Engine 5).
Both the FastAPI server and the MCP server call this so the science is
identical across surfaces — neither re-implements the chain.

Returns plain dicts (JSON-ready) so it can be serialised directly.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from .residence_time import compute_residence_time
from .sediment_loading import assess_internal_loading
from .nutrient_sources import attribute_nutrient_sources
from .bloom_forecast import forecast_bloom
from .digital_twin import LagoonState, compare_interventions


def diagnose(
    *,
    temperature: float,
    phosphate: float,
    ammonia: float,
    dissolved_oxygen: float,
    salinity: float,
    nitrate: float = 0.0,
    # Hydraulics (optional — enables residence time + twin)
    volume_m3: float = 0.0,
    inflow_m3_day: float = 0.0,
    outflow_m3_day: float = 0.0,
    recirculation_m3_day: float = 0.0,
    # Sediment
    orp: Optional[float] = None,
    sediment_state: str = "normal",
    # Context flags for attribution
    recent_rainfall: bool = False,
    dust_event: bool = False,
    tse_inflow_high: bool = False,
    salinity_baseline: float = 45.0,
    historical_bloom_count: int = 0,
    include_interventions: bool = True,
    intervention_magnitude: float = 0.5,
) -> dict:
    """Run the full chain and return a combined, explainable diagnosis.

    The order follows science/CONTEXT.md:
        Residence (hydraulics) → Sediment (Fe-P) → Nutrient sources
        → Bloom formation → [interventions / operational risk]
    """
    # ── Engine 3: Residence time (if hydraulics supplied) ──
    if volume_m3 > 0 and outflow_m3_day > 0:
        rt = compute_residence_time(
            volume_m3, inflow_m3_day, outflow_m3_day, recirculation_m3_day)
        residence_days = rt.residence_time_days
        residence_for_models = (residence_days if residence_days != float("inf")
                                else 9999.0)
        residence_block = asdict(rt)
        # inf is not JSON-serialisable — represent as null + flag
        if residence_days == float("inf"):
            residence_block["residence_time_days"] = None
            residence_block["closed_system"] = True
    else:
        residence_for_models = 0.0
        residence_block = None

    # ── Engine 2: Sediment Fe-P loading ──
    sed = assess_internal_loading(
        do=dissolved_oxygen, temperature=temperature,
        phosphate=phosphate, orp=orp, sediment_state=sediment_state)

    # ── Engine 1: Nutrient attribution (uses Engine 2 score as context) ──
    nut = attribute_nutrient_sources(
        phosphate=phosphate, ammonia=ammonia, nitrate=nitrate, salinity=salinity,
        recent_rainfall=recent_rainfall, dust_event=dust_event,
        tse_inflow_high=tse_inflow_high, internal_loading_score=sed.score,
        salinity_baseline=salinity_baseline)

    # ── Engine 4: Bloom formation (uses Engines 2 & 3) ──
    bloom = forecast_bloom(
        temperature=temperature, phosphate=phosphate, ammonia=ammonia,
        dissolved_oxygen=dissolved_oxygen, salinity=salinity,
        residence_time_days=residence_for_models,
        internal_loading_score=sed.score,
        historical_bloom_count=historical_bloom_count)

    result: dict = {
        "summary": {
            "bloom_probability_pct": bloom.probability_pct,
            "bloom_severity":        bloom.severity,
            "dominant_nutrient_source": nut.dominant_source,
            "nutrient_confidence_pct":  nut.confidence_pct,
            "internal_loading_level":   sed.level,
            "residence_risk":  residence_block["risk_level"] if residence_block else "UNKNOWN",
            "recovery_time_days": bloom.recovery_time_days,
        },
        "nutrient_attribution": asdict(nut),
        "internal_loading":     asdict(sed),
        "residence_time":       residence_block,
        "bloom_forecast":       asdict(bloom),
    }

    # ── Engine 5: rank interventions (needs hydraulics for full effect) ──
    if include_interventions:
        state = LagoonState(
            temperature=temperature, phosphate=phosphate, ammonia=ammonia,
            dissolved_oxygen=dissolved_oxygen, salinity=salinity,
            volume_m3=volume_m3, inflow_m3_day=inflow_m3_day,
            outflow_m3_day=outflow_m3_day, recirculation_m3_day=recirculation_m3_day,
            orp=orp, sediment_state=sediment_state,
            historical_bloom_count=historical_bloom_count)
        ranked = compare_interventions(state, magnitude=intervention_magnitude)
        result["recommended_interventions"] = [asdict(r) for r in ranked]

    return result
