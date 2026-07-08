"""Predictive monitoring — forecast a parameter with a confidence band.

Commercial core: predict what a sample WOULD read, with an honest uncertainty
band that widens the longer it's been since a real sample (and wider still for
lagoons inferred from sentinels rather than sampled directly). When a real
sample is eventually taken, science.validation scores this prediction — that
track record is what justifies sampling fewer lagoons, less often, above the
regulatory floor.

v1 predictor is a transparent **seasonal + persistence baseline**:
  - seasonal expectation from the monthly baseline curve (data.sample_data),
  - nudged toward the lagoon's own last real reading (persistence),
  - band = Z · seasonal_std · decay(months_since_sample) · sentinel_penalty.

It is deliberately simple and fully explainable. The point of v1 is the
validation loop that measures how good it actually is and calibrates it.
"""
from __future__ import annotations

from typing import Optional

from . import config
from .models import Prediction


def _seasonal_expectation(parameter: str, month: int) -> float:
    """Baseline seasonal value for a parameter in a given month (1–12)."""
    from data.sample_data import get_monthly_table
    table = get_monthly_table()
    attr = config.PREDICTED_PARAMETERS[parameter]["attr"]
    key = "coliforms" if attr == "total_coliforms" else attr
    series = table.get(key)
    if not series:
        raise ValueError(f"No seasonal baseline for parameter '{parameter}'")
    return float(series[month - 1])


def _decay_multiplier(months_since_sample: float) -> float:
    m = 1.0 + config.PREDICT_DECAY_PER_MONTH * max(0.0, months_since_sample)
    return min(m, config.PREDICT_DECAY_CAP)


def _confidence_from_multiplier(mult: float) -> float:
    """Wider band (bigger multiplier) → lower reported confidence %."""
    # mult 1.0 → max confidence; mult at decay cap*sentinel → min confidence.
    worst = config.PREDICT_DECAY_CAP * config.PREDICT_SENTINEL_PENALTY
    frac = (mult - 1.0) / max(worst - 1.0, 1e-6)
    conf = config.PREDICT_CONF_MAX - frac * (config.PREDICT_CONF_MAX - config.PREDICT_CONF_MIN)
    return round(max(config.PREDICT_CONF_MIN, min(conf, config.PREDICT_CONF_MAX)), 1)


def predict_parameter(
    site: str,
    year: int,
    month: int,
    parameter: str,
    last_value: Optional[float] = None,
    months_since_sample: float = 1.0,
    extrapolated: bool = False,
    persistence_weight: float = 0.4,
) -> Prediction:
    """Forecast one parameter for a lagoon/month with a confidence band.

    Args:
        site, year, month: target lagoon and period.
        parameter:         key in config.PREDICTED_PARAMETERS.
        last_value:        the lagoon's most recent real reading for this
                           parameter, if any (anchors persistence).
        months_since_sample: months since that last real sample (drives decay).
        extrapolated:      True if inferred from sentinel lagoons (wider band).
        persistence_weight: 0–1 blend of last_value vs seasonal expectation.

    Returns:
        Prediction with value, band, confidence and reasoning.
    """
    if parameter not in config.PREDICTED_PARAMETERS:
        raise ValueError(f"Unknown parameter '{parameter}'. "
                         f"Valid: {list(config.PREDICTED_PARAMETERS)}")

    meta = config.PREDICTED_PARAMETERS[parameter]
    reasoning: list[str] = []

    seasonal = _seasonal_expectation(parameter, month)
    reasoning.append(f"Seasonal baseline for {meta['label']} in month {month}: "
                     f"{seasonal:.2f} {meta['unit']}.")

    if last_value is not None:
        w = max(0.0, min(persistence_weight, 1.0))
        predicted = w * last_value + (1 - w) * seasonal
        reasoning.append(f"Blended with last real reading {last_value:.2f} "
                         f"(persistence weight {w:.0%}) → {predicted:.2f}.")
    else:
        predicted = seasonal
        reasoning.append("No prior reading for this lagoon — using seasonal baseline alone.")

    decay = _decay_multiplier(months_since_sample)
    mult = decay
    reasoning.append(f"{months_since_sample:.0f} month(s) since last sample → "
                     f"band ×{decay:.2f} (decay).")
    if extrapolated:
        mult *= config.PREDICT_SENTINEL_PENALTY
        reasoning.append(f"Lagoon inferred from sentinels → band ×"
                         f"{config.PREDICT_SENTINEL_PENALTY:g} (extrapolation penalty).")

    half = config.PREDICT_BAND_Z * meta["season_std"] * mult
    low = max(0.0, predicted - half)
    high = predicted + half
    conf = _confidence_from_multiplier(mult)
    reasoning.append(f"95%-style band {low:.2f}–{high:.2f} {meta['unit']} "
                     f"(±{half:.2f}); reported confidence {conf:.0f}%.")

    return Prediction(
        site=site, year=year, month=month, parameter=parameter,
        predicted=round(predicted, 3), band_low=round(low, 3), band_high=round(high, 3),
        confidence_pct=conf, months_since_sample=months_since_sample,
        extrapolated=extrapolated, reasoning=reasoning,
    )


# ════════════════════════════════════════════════════════════════════════════
# DRIVER-FORCED PREDICTION  (INTERNAL — driver detail never surfaced to clients)
# ════════════════════════════════════════════════════════════════════════════
# Instead of a bare seasonal guess, modulate the seasonal expectation by how the
# actual forcings (weather + inputs) deviate from the climatological normal for
# the month. The driver-derived physical state (water temp, salinity, evaporation)
# runs through the chain engines to perturb each predicted parameter. The
# Prediction.reasoning cites the drivers for the developer — it must NOT be shown
# client-facing.

def _bloom_index(water_temp: float, salinity: float, residence_days: float,
                 phosphate: float, ammonia: float, do: float) -> float:
    """Bloom favourability 0–1 from state — thin wrapper over the bloom engine."""
    from .bloom_forecast import forecast_bloom
    return forecast_bloom(
        temperature=water_temp, phosphate=phosphate, ammonia=ammonia,
        dissolved_oxygen=do, salinity=salinity,
        residence_time_days=residence_days).severity_score


def predict_from_drivers(
    site: str,
    year: int,
    month: int,
    parameter: str,
    drivers,                      # science.drivers.Drivers
    residence_days: float = 30.0,
    last_value: Optional[float] = None,
    months_since_sample: float = 1.0,
    extrapolated: bool = False,
) -> Prediction:
    """Driver-forced prediction: seasonal expectation perturbed by the actual
    forcings, via the derived physical state and chain engines.

    The point estimate is process-driven; the band uses the same decay machinery
    as predict_parameter and is later tightened by the calibration layer.
    """
    if parameter not in config.PREDICTED_PARAMETERS:
        raise ValueError(f"Unknown parameter '{parameter}'.")

    from .drivers import derived_state, water_temperature, _climatology
    from core.calculations import do_saturation

    meta = config.PREDICTED_PARAMETERS[parameter]
    reasoning: list[str] = []

    # Actual vs climatological driver-derived state for this month.
    state = derived_state(drivers, residence_days)
    clim = _climatology(year, month)
    clim_state = derived_state(clim, residence_days)
    wt, wt_clim = state["water_temp_c"], clim_state["water_temp_c"]
    sal, sal_clim = state["salinity_psu"], clim_state["salinity_psu"]

    seasonal = _seasonal_expectation(parameter, month)
    reasoning.append(f"Seasonal baseline {meta['label']}: {seasonal:.2f} {meta['unit']}.")
    reasoning.append(f"Driver-derived state: water {wt:.1f}°C (normal {wt_clim:.1f}), "
                     f"salinity {sal:.1f} PSU, evap {state['evaporation_mm_day']:.1f} mm/d.")

    # ── Parameter-specific driver modulation (transparent factors) ──
    factor = 1.0
    if parameter == "do":
        # DO tracks oxygen saturation, which falls as water warms.
        sat, sat_clim = do_saturation(wt), do_saturation(wt_clim)
        factor = sat / sat_clim if sat_clim else 1.0
        reasoning.append(f"DO saturation {sat:.1f} vs normal {sat_clim:.1f} → ×{factor:.2f}.")
    elif parameter in ("chla", "phycocyanin"):
        # Bloom biomass scales with bloom favourability vs the normal month.
        bi = _bloom_index(wt, sal, residence_days, seasonal_phos(month), seasonal_amm(month), seasonal_do(month))
        bi_clim = _bloom_index(wt_clim, sal_clim, residence_days,
                               seasonal_phos(month), seasonal_amm(month), seasonal_do(month))
        factor = (0.4 + bi) / (0.4 + bi_clim) if bi_clim else 1.0
        reasoning.append(f"Bloom favourability {bi:.2f} vs normal {bi_clim:.2f} → ×{factor:.2f}.")
    elif parameter == "phosphate":
        # Internal Fe-P release accelerates with warmth (Q10); plus TSE input.
        factor = config.SEDIMENT_TEMP_Q10 ** ((wt - wt_clim) / 10.0)
        if drivers.tse_phosphate_mgl and drivers.tse_inflow_m3_day:
            factor *= 1.0 + 0.1 * (drivers.tse_phosphate_mgl / max(config.SEDIMENT_PO4_ELEVATED, 1e-6))
        reasoning.append(f"Warm-driven Fe-P release + TSE input → ×{factor:.2f}.")
    elif parameter == "ammonia":
        if drivers.tse_nitrogen_mgl:
            factor = 1.0 + 0.15 * (drivers.tse_nitrogen_mgl / 5.0)
        reasoning.append(f"TSE nitrogen input → ×{factor:.2f}.")

    driven = seasonal * factor

    # Blend toward the lagoon's own last reading (persistence) if available.
    if last_value is not None:
        w = 0.35
        predicted = w * last_value + (1 - w) * driven
        reasoning.append(f"Blended with last reading {last_value:.2f} (×{w:.0%}) → {predicted:.2f}.")
    else:
        predicted = driven

    # Band: same decay machinery as the seasonal predictor.
    decay = _decay_multiplier(months_since_sample)
    mult = decay * (config.PREDICT_SENTINEL_PENALTY if extrapolated else 1.0)
    half = config.PREDICT_BAND_Z * meta["season_std"] * mult
    low, high = max(0.0, predicted - half), predicted + half
    conf = _confidence_from_multiplier(mult)
    reasoning.append(f"Prediction {predicted:.2f} {meta['unit']}, band {low:.2f}–{high:.2f}, "
                     f"confidence {conf:.0f}% (pre-calibration).")

    return Prediction(
        site=site, year=year, month=month, parameter=parameter,
        predicted=round(predicted, 3), band_low=round(low, 3), band_high=round(high, 3),
        confidence_pct=conf, months_since_sample=months_since_sample,
        extrapolated=extrapolated, reasoning=reasoning,
    )


# Small seasonal helpers reused by the driver-forced bloom modulation.
def seasonal_phos(month: int) -> float:
    return _seasonal_expectation("phosphate", month)


def seasonal_amm(month: int) -> float:
    return _seasonal_expectation("ammonia", month)


def seasonal_do(month: int) -> float:
    return _seasonal_expectation("do", month)
