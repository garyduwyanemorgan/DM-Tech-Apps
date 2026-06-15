"""Walk-forward backtest — the accuracy track record.

For each historical sample, predict it using ONLY the earlier samples
(expanding-window, out-of-sample), then score predicted-vs-actual. This turns
existing history into an honest, prospective-style accuracy record without
waiting months for new samples — the evidence that the model can be trusted to
skip sampling.

Pure: readings in → ValidationRecords / ValidationStats out.
"""
from __future__ import annotations

from typing import List

from . import config
from .calibration import assimilate, apply_calibration
from .predictor import predict_from_drivers
from .validation import validate, aggregate
from .models import ValidationRecord, ValidationStats

_PARAMS = ["chla", "do", "phosphate"]
_RESIDENCE = 45.0


def _model_pred(site: str, year: int, month: int, parameter: str, last_value=None) -> float:
    from .drivers import get_drivers
    return predict_from_drivers(
        site, year, month, parameter,
        get_drivers(year, month, use_live=False),
        residence_days=_RESIDENCE, last_value=last_value,
    ).predicted


def backtest_site(site: str, readings: list, parameters: List[str] = None) -> List[ValidationRecord]:
    """Walk-forward predicted-vs-actual records for one lagoon."""
    params = parameters or _PARAMS
    recs: List[ValidationRecord] = []
    ordered = sorted(readings, key=lambda r: r.timestamp)

    for i, target in enumerate(ordered):
        prior = ordered[:i]
        if not prior:
            continue   # need at least one earlier sample for out-of-sample test
        last = prior[-1]
        for p in params:
            attr = config.PREDICTED_PARAMETERS[p]["attr"]
            # Calibrate only on earlier samples (no peeking at the target).
            pairs = [(_model_pred(site, r.timestamp.year, r.timestamp.month, p),
                      getattr(r, attr)) for r in prior]
            cal = assimilate(p, pairs)
            model = _model_pred(site, target.timestamp.year, target.timestamp.month, p,
                                last_value=getattr(last, attr))
            cp = apply_calibration(cal, model)
            # Build a Prediction-shaped object for the validator.
            from .models import Prediction
            pred = Prediction(site=site, year=target.timestamp.year,
                              month=target.timestamp.month, parameter=p,
                              predicted=cp.value, band_low=cp.band_low,
                              band_high=cp.band_high, confidence_pct=cp.confidence_pct,
                              months_since_sample=1.0, extrapolated=False)
            recs.append(validate(pred, getattr(target, attr)))
    return recs


def backtest_portfolio(sites_readings: dict) -> ValidationStats:
    """Aggregate accuracy across a {site: [readings]} mapping."""
    all_recs: List[ValidationRecord] = []
    for site, readings in sites_readings.items():
        all_recs.extend(backtest_site(site, readings))
    return aggregate(all_recs)


def confidence_trajectory(site: str, readings: list, parameters: List[str] = None) -> list:
    """How model confidence for a lagoon evolves as samples accumulate.

    At each point in the sample history we compute the confidence the model
    would report given only the samples up to that point — so the curve shows
    certainty rising as the lagoon is sampled and the model is validated. A
    volatile lagoon plateaus low; a predictable one climbs high.

    Returns [{label, year, month, confidence, n}], one point per sample.
    """
    from .calibration import apply_calibration
    params = parameters or _PARAMS
    ordered = sorted(readings, key=lambda r: r.timestamp)
    traj = []
    for i, target in enumerate(ordered):
        prior = ordered[:i + 1]                    # samples available by this date
        confs = []
        for p in params:
            attr = config.PREDICTED_PARAMETERS[p]["attr"]
            pairs = [(_model_pred(site, r.timestamp.year, r.timestamp.month, p),
                      getattr(r, attr)) for r in prior]
            cal = assimilate(p, pairs)
            # Confidence depends only on the posterior, not the value queried.
            confs.append(apply_calibration(cal, 1.0).confidence_pct)
        traj.append({
            "label": f"{target.timestamp.year}-{target.timestamp.month:02d}",
            "year": target.timestamp.year, "month": target.timestamp.month,
            "confidence": round(sum(confs) / len(confs), 1), "n": len(prior),
        })
    return traj
