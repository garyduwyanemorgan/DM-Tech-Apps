"""Portfolio assessment orchestrator.

Ties the hidden stack (drivers → driver-forced predictor → calibration) together
per lagoon and emits ONLY client-safe outputs: a predicted headline, a single
confidence number, days since last sample, and a risk level. The UI consumes
these — it never touches drivers/calibration directly, so nothing leaks.

assess_lagoon():
  - predicts the key parameters for the target month from the (hidden) drivers,
  - calibrates each against the lagoon's own past samples (Bayesian),
  - rolls them into one confidence and a plain-language headline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from . import config
from .calibration import assimilate, apply_calibration
from .predictor import predict_from_drivers

# Parameters we predict for the portfolio view (bloom-relevant first).
_PORTFOLIO_PARAMS = ["chla", "do", "phosphate"]
_DEFAULT_RESIDENCE_DAYS = 45.0


@dataclass
class LagoonAssessment:
    site: str
    headline: str
    confidence_pct: float
    days_since_sample: float
    risk_level: str
    extrapolated: bool
    predictions: Dict[str, dict] = field(default_factory=dict)   # param -> {value,low,high,conf}


def _days_since(last_dt, year: int, month: int) -> float:
    target = date(year, month, 15)
    if last_dt is None:
        return 9999.0
    return max(0.0, (target - last_dt.date()).days)


def assess_lagoon(site: str, readings: list, year: int, month: int) -> LagoonAssessment:
    """Assess one lagoon for the target month from the hidden driver+calibration
    stack. `readings` is the lagoon's WaterReading history (may be empty)."""
    from .drivers import get_drivers
    drivers = get_drivers(year, month, use_live=False)   # climatology: fast, offline-safe

    # Most recent real sample → persistence anchor + recency.
    last = max(readings, key=lambda r: r.timestamp) if readings else None
    days_since = _days_since(last.timestamp if last else None, year, month)
    months_since = max(1.0, days_since / 30.0)
    extrapolated = last is None

    predictions: Dict[str, dict] = {}
    confidences: List[float] = []

    for param in _PORTFOLIO_PARAMS:
        attr = config.PREDICTED_PARAMETERS[param]["attr"]
        # Build calibration pairs by re-predicting each past sample's month.
        pairs = []
        for r in readings:
            mp = predict_from_drivers(site, r.timestamp.year, r.timestamp.month, param,
                                      get_drivers(r.timestamp.year, r.timestamp.month, use_live=False),
                                      residence_days=_DEFAULT_RESIDENCE_DAYS).predicted
            pairs.append((mp, getattr(r, attr)))
        cal = assimilate(param, pairs)

        last_val = getattr(last, attr) if last else None
        model = predict_from_drivers(site, year, month, param, drivers,
                                     residence_days=_DEFAULT_RESIDENCE_DAYS,
                                     last_value=last_val, months_since_sample=months_since,
                                     extrapolated=extrapolated)
        cp = apply_calibration(cal, model.predicted)
        predictions[param] = {
            "value": cp.value, "low": cp.band_low, "high": cp.band_high,
            "confidence": cp.confidence_pct, "unit": config.PREDICTED_PARAMETERS[param]["unit"],
            "label": config.PREDICTED_PARAMETERS[param]["label"],
        }
        confidences.append(cp.confidence_pct)

    confidence = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

    # Risk + headline from the predicted bloom-relevant state.
    from .bloom_forecast import forecast_bloom
    chla = predictions["chla"]["value"]
    do = predictions["do"]["value"]
    phos = predictions["phosphate"]["value"]
    # crude salinity/temp via drivers for the bloom call (hidden)
    from .drivers import derived_state
    st = derived_state(drivers, _DEFAULT_RESIDENCE_DAYS)
    bloom = forecast_bloom(temperature=st["water_temp_c"], phosphate=phos, ammonia=2.0,
                           dissolved_oxygen=do, salinity=st["salinity_psu"],
                           residence_time_days=_DEFAULT_RESIDENCE_DAYS,
                           internal_loading_score=0.4)
    risk = bloom.severity
    headline = f"Chl-a ~{chla:.0f} µg/L · bloom risk {risk.title()}"

    return LagoonAssessment(
        site=site, headline=headline, confidence_pct=confidence,
        days_since_sample=days_since, risk_level=risk, extrapolated=extrapolated,
        predictions=predictions,
    )
