"""Engine 4 — Bloom Forecasting.

Chain link: Bloom Formation.

An explainable, weighted-driver model. Each environmental driver is mapped to a
0–1 "bloom favourability", combined with documented weights (config.BLOOM_WEIGHTS),
and returned together with the per-driver contributions so the forecast is never
a black box.

Drivers and rationale:
  • temperature      — cyanobacteria optimum ~28–35°C here; growth collapses cold.
  • phosphate        — frequently co-limiting; saturating response.
  • ammonia          — reduced N is the preferred N source for many bloom-formers.
  • dissolved oxygen — low DO signals stress and reinforces internal P loading.
  • residence time   — stagnation lets biomass accumulate (Engine 3 output).
  • salinity         — bloom cyanobacteria favour the fresher TSE lens.
  • internal loading — sediment P feedback (Engine 2 output).

Outputs: bloom probability (%), severity band, and an estimated recovery time
that lengthens with severity and poor flushing.
"""
from __future__ import annotations

from typing import Optional

from . import config
from .models import BloomForecast


def _ramp(x: float, lo: float, hi: float) -> float:
    """Linear 0→1 ramp between lo and hi, clamped."""
    if hi == lo:
        return 0.0 if x < lo else 1.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def _temp_favourability(temp_c: float) -> float:
    """Cold→0, optimum band→1, with mild fall-off below the optimum."""
    if temp_c <= config.BLOOM_TEMP_MIN:
        return 0.0
    if temp_c >= config.BLOOM_TEMP_OPT_LOW:
        return 1.0
    return _ramp(temp_c, config.BLOOM_TEMP_MIN, config.BLOOM_TEMP_OPT_LOW)


def _saturating(x: float, half_sat: float) -> float:
    """Michaelis-Menten style saturating favourability (0..1)."""
    if x <= 0:
        return 0.0
    return x / (x + half_sat)


def _do_favourability(do: float) -> float:
    """Low DO is bloom-favourable (stress + internal loading). Invert DO."""
    # Map DO 0 mg/L → 1.0 favourable, DO ≥ oxic threshold → low.
    return max(0.0, min(1.0, (config.SEDIMENT_DO_OXIC - do) / config.SEDIMENT_DO_OXIC))


def _salinity_favourability(sal: float) -> float:
    """Fresher → favourable; hypersaline → suppressed."""
    if sal <= config.BLOOM_SAL_LOW:
        return 1.0
    if sal >= config.BLOOM_SAL_HIGH:
        return 0.1
    return 1.0 - _ramp(sal, config.BLOOM_SAL_LOW, config.BLOOM_SAL_HIGH) * 0.9


def _severity_band(prob: float) -> str:
    for threshold, label in config.BLOOM_SEVERITY_BANDS:
        if prob < threshold:
            return label
    return config.BLOOM_SEVERITY_BANDS[-1][1]


def forecast_bloom(
    temperature: float,
    phosphate: float,
    ammonia: float,
    dissolved_oxygen: float,
    salinity: float,
    residence_time_days: float = 0.0,
    internal_loading_score: float = 0.0,
    historical_bloom_count: int = 0,
) -> BloomForecast:
    """Forecast bloom probability, severity and recovery time.

    Args:
        temperature:         Water temperature (°C).
        phosphate:           Phosphate (mg/L).
        ammonia:             Ammonia as N (mg/L).
        dissolved_oxygen:    DO (mg/L).
        salinity:            Salinity (PSU).
        residence_time_days: From Engine 3 (0 if unknown).
        internal_loading_score: From Engine 2 (0–1).
        historical_bloom_count: Prior blooms recorded at the site.

    Returns:
        BloomForecast with per-driver contributions and reasoning.
    """
    reasoning: list[str] = []

    # ── Per-driver favourabilities (0..1) ──
    fav = {
        "temperature":      _temp_favourability(temperature),
        "phosphate":        _saturating(phosphate, config.BLOOM_PO4_HALF_SAT),
        "ammonia":          _saturating(ammonia, config.BLOOM_NH3_HALF_SAT),
        "dissolved_oxygen": _do_favourability(dissolved_oxygen),
        "residence_time":   min(residence_time_days / config.RESIDENCE_RISK_SATURATION, 1.0),
        "salinity":         _salinity_favourability(salinity),
        "internal_loading": max(0.0, min(internal_loading_score, 1.0)),
    }

    # ── Weighted combination ──
    contributions = {k: fav[k] * config.BLOOM_WEIGHTS[k] for k in fav}
    base_prob = sum(contributions.values())   # 0..1 (weights sum ~1)

    # ── Historical susceptibility prior ──
    history_bonus = min(
        historical_bloom_count * config.BLOOM_HISTORY_WEIGHT,
        config.BLOOM_HISTORY_CAP)
    prob = max(0.0, min(base_prob + history_bonus, 1.0))

    # Narrate the top contributing drivers.
    top = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)[:3]
    reasoning.append(
        "Top bloom drivers: " + ", ".join(
            f"{k} ({fav[k]:.2f}×w{config.BLOOM_WEIGHTS[k]:.2f})" for k, _ in top) + ".")
    if history_bonus > 0:
        reasoning.append(
            f"Historical prior: {historical_bloom_count} prior bloom(s) "
            f"→ +{history_bonus:.2f} susceptibility.")
    reasoning.append(f"Combined bloom probability {prob*100:.0f}%.")

    severity = _severity_band(prob)

    # ── Recovery time: base + severity term + residence penalty ──
    recovery = (config.BLOOM_RECOVERY_BASE_DAYS
                + prob * config.BLOOM_RECOVERY_SEVERITY_DAYS
                + residence_time_days * config.BLOOM_RECOVERY_RESIDENCE_FACTOR)
    reasoning.append(
        f"Severity {severity}; estimated recovery ≈ {recovery:.0f} days "
        f"(base {config.BLOOM_RECOVERY_BASE_DAYS:g} + severity + flushing penalty).")

    return BloomForecast(
        probability_pct=round(prob * 100.0, 1),
        severity=severity,
        severity_score=round(prob, 3),
        recovery_time_days=round(recovery, 1),
        drivers={k: round(v, 3) for k, v in fav.items()},
        reasoning=reasoning,
    )
