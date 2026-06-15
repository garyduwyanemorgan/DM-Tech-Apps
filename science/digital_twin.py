"""Engine 5 — Digital Twin (scenario simulation).

Chain link: Operational Risk — orchestrates Engines 1–4.

Given a baseline lagoon state and a management intervention, the twin re-runs
the scientific chain with the intervention applied and reports the expected
change in bloom probability, the timeline to that effect, and a recommendation.

Supported interventions (config.DIGITAL_TWIN_INTERVENTIONS):
  reduce_phosphate       — lower water-column phosphate (source control / binding)
  increase_circulation   — raise DO/ORP, shorten residence, suppress internal loading
  remove_sludge          — remove the mobile-P sediment pool (cut internal loading)
  reduce_residence_time  — increase flushing/exchange

Each intervention maps to explicit, documented effects on the engine inputs.
Nothing is hidden: the reasoning records exactly what was changed.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from . import config
from .bloom_forecast import forecast_bloom
from .residence_time import compute_residence_time
from .sediment_loading import assess_internal_loading
from .models import TwinScenarioResult


@dataclass
class LagoonState:
    """Baseline state the twin simulates from."""
    temperature: float
    phosphate: float
    ammonia: float
    dissolved_oxygen: float
    salinity: float
    # Hydraulics (optional — enables residence-time effects)
    volume_m3: float = 0.0
    inflow_m3_day: float = 0.0
    outflow_m3_day: float = 0.0
    recirculation_m3_day: float = 0.0
    # Sediment
    orp: Optional[float] = None
    sediment_state: str = "normal"
    historical_bloom_count: int = 0


def _evaluate(state: LagoonState) -> tuple[float, float, float]:
    """Run the chain for a state → (bloom_pct, residence_days, internal_score)."""
    if state.volume_m3 > 0 and state.outflow_m3_day > 0:
        rt = compute_residence_time(
            state.volume_m3, state.inflow_m3_day,
            state.outflow_m3_day, state.recirculation_m3_day)
        residence = rt.residence_time_days
        if residence == float("inf"):
            residence = config.RESIDENCE_RISK_SATURATION
    else:
        residence = 0.0

    sed = assess_internal_loading(
        do=state.dissolved_oxygen, temperature=state.temperature,
        phosphate=state.phosphate, orp=state.orp,
        sediment_state=state.sediment_state)

    bloom = forecast_bloom(
        temperature=state.temperature, phosphate=state.phosphate,
        ammonia=state.ammonia, dissolved_oxygen=state.dissolved_oxygen,
        salinity=state.salinity, residence_time_days=residence,
        internal_loading_score=sed.score,
        historical_bloom_count=state.historical_bloom_count)

    return bloom.probability_pct, residence, sed.score


def _apply(state: LagoonState, intervention: str, magnitude: float) -> tuple[LagoonState, list[str]]:
    """Return a new state with the intervention applied + reasoning."""
    notes: list[str] = []
    s = replace(state)

    if intervention == "reduce_phosphate":
        new_p = state.phosphate * (1.0 - magnitude)
        s = replace(s, phosphate=new_p)
        notes.append(f"Phosphate reduced {magnitude*100:.0f}%: "
                     f"{state.phosphate:.2f} → {new_p:.2f} mg/L.")

    elif intervention == "increase_circulation":
        # Aeration raises DO toward saturation and ORP; recirculation does not
        # flush, but mixing shortens effective residence modestly.
        # ORP must be raised relative to the BASELINE effective ORP (estimated
        # from DO when no probe), so aeration can only oxidise — never reduce.
        from .sediment_loading import _estimate_orp_from_do
        base_orp = state.orp if state.orp is not None else _estimate_orp_from_do(state.dissolved_oxygen)
        new_do = min(state.dissolved_oxygen + magnitude * config.SEDIMENT_DO_OXIC, 9.0)
        new_orp = base_orp + magnitude * config.SEDIMENT_ORP_OXIC
        new_outflow = state.outflow_m3_day * (1.0 + magnitude * 0.3)
        s = replace(s, dissolved_oxygen=new_do, orp=new_orp, outflow_m3_day=new_outflow)
        notes.append(f"Circulation/aeration +{magnitude*100:.0f}%: DO "
                     f"{state.dissolved_oxygen:.1f}→{new_do:.1f} mg/L, ORP raised, "
                     "internal loading suppressed.")

    elif intervention == "remove_sludge":
        # Dredging removes the mobile-P pool → sediment state improves and the
        # internal-loading contribution drops at source.
        order = ["post_bloom", "organic", "normal", "mineral"]
        idx = order.index(state.sediment_state) if state.sediment_state in order else 2
        new_state = order[min(idx + 1, len(order) - 1)]
        # A heavy dredge also draws down standing phosphate fed by the sediment.
        new_p = state.phosphate * (1.0 - 0.3 * magnitude)
        s = replace(s, sediment_state=new_state, phosphate=new_p)
        notes.append(f"Sludge removal: sediment '{state.sediment_state}'→'{new_state}', "
                     f"phosphate {state.phosphate:.2f}→{new_p:.2f} mg/L.")

    elif intervention == "reduce_residence_time":
        new_outflow = state.outflow_m3_day * (1.0 + magnitude)
        s = replace(s, outflow_m3_day=new_outflow)
        notes.append(f"Flushing/exchange +{magnitude*100:.0f}%: outflow "
                     f"{state.outflow_m3_day:,.0f}→{new_outflow:,.0f} m³·day⁻¹.")

    else:
        raise ValueError(f"Unknown intervention '{intervention}'. "
                         f"Valid: {list(config.DIGITAL_TWIN_INTERVENTIONS)}")

    return s, notes


def simulate(
    state: LagoonState,
    intervention: str,
    magnitude: float = 0.5,
) -> TwinScenarioResult:
    """Simulate a single intervention against the baseline state.

    Args:
        state:        Baseline LagoonState.
        intervention: One of config.DIGITAL_TWIN_INTERVENTIONS keys.
        magnitude:    Strength 0–1 (e.g. 0.5 = "reduce phosphate by 50%").

    Returns:
        TwinScenarioResult with baseline vs projected bloom %, reduction,
        timeline and a recommendation.
    """
    if intervention not in config.DIGITAL_TWIN_INTERVENTIONS:
        raise ValueError(f"Unknown intervention '{intervention}'. "
                         f"Valid: {list(config.DIGITAL_TWIN_INTERVENTIONS)}")
    magnitude = max(0.0, min(magnitude, 1.0))
    spec = config.DIGITAL_TWIN_INTERVENTIONS[intervention]

    baseline_bloom, base_rt, base_sed = _evaluate(state)
    new_state, notes = _apply(state, intervention, magnitude)
    projected_bloom, proj_rt, proj_sed = _evaluate(new_state)

    reduction = baseline_bloom - projected_bloom

    reasoning: list[str] = [f"Intervention: {spec.label} (magnitude {magnitude*100:.0f}%)."]
    reasoning.extend(notes)
    reasoning.append(
        f"Bloom probability {baseline_bloom:.0f}% → {projected_bloom:.0f}% "
        f"({'−' if reduction >= 0 else '+'}{abs(reduction):.0f} pts).")
    if base_rt or proj_rt:
        reasoning.append(f"Residence time {base_rt:.0f} → {proj_rt:.0f} days.")
    reasoning.append(f"Internal loading score {base_sed:.2f} → {proj_sed:.2f}.")
    reasoning.append(f"Expected time to effect ≈ {spec.time_to_effect_days:.0f} days. {spec.description}")

    if reduction >= 15:
        rec = f"RECOMMENDED — {spec.label} should materially cut bloom risk."
    elif reduction >= 5:
        rec = f"WORTH CONSIDERING — {spec.label} gives a moderate improvement."
    elif reduction > 0:
        rec = f"MARGINAL — {spec.label} helps only slightly here; combine with other measures."
    else:
        rec = f"NOT EFFECTIVE ALONE — {spec.label} does not reduce bloom risk in this state."
    reasoning.append(rec)

    return TwinScenarioResult(
        scenario=f"{spec.label} ({magnitude*100:.0f}%)",
        baseline_bloom_pct=round(baseline_bloom, 1),
        projected_bloom_pct=round(projected_bloom, 1),
        expected_bloom_reduction_pct=round(reduction, 1),
        timeline_days=spec.time_to_effect_days,
        recommendation=rec,
        reasoning=reasoning,
    )


def compare_interventions(state: LagoonState, magnitude: float = 0.5) -> list[TwinScenarioResult]:
    """Run every supported intervention and return results sorted best-first."""
    results = [simulate(state, key, magnitude) for key in config.DIGITAL_TWIN_INTERVENTIONS]
    return sorted(results, key=lambda r: r.expected_bloom_reduction_pct, reverse=True)
