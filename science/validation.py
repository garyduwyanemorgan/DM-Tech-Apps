"""Validation ledger — score predictions against real samples.

When a lagoon is finally sampled, each outstanding Prediction for that
lagoon/month is checked against the actual value. The record says whether the
real value fell inside the predicted band (ON-TRACK) or outside it (DRIFT),
plus the error. Aggregated over many samples this becomes the model's accuracy
track record — the evidence that justifies reduced sampling and the artefact
that calibrates the predictor.

Pure functions: a Prediction + an actual value → a ValidationRecord; a list of
records → ValidationStats.
"""
from __future__ import annotations

from statistics import mean
from typing import Dict, Iterable, List

from .models import Prediction, ValidationRecord, ValidationStats


def validate(prediction: Prediction, actual: float) -> ValidationRecord:
    """Score one prediction against the real sampled value."""
    within = prediction.band_low <= actual <= prediction.band_high
    abs_err = abs(actual - prediction.predicted)
    pct_err = (abs_err / abs(actual) * 100.0) if actual != 0 else float("inf")
    return ValidationRecord(
        site=prediction.site, year=prediction.year, month=prediction.month,
        parameter=prediction.parameter, predicted=prediction.predicted,
        actual=actual, band_low=prediction.band_low, band_high=prediction.band_high,
        within_band=within, abs_error=round(abs_err, 3),
        pct_error=round(pct_err, 1) if pct_err != float("inf") else pct_err,
        verdict="ON-TRACK" if within else "DRIFT",
    )


def aggregate(records: Iterable[ValidationRecord]) -> ValidationStats:
    """Aggregate validation records into an accuracy track record."""
    recs: List[ValidationRecord] = list(records)
    n = len(recs)
    if n == 0:
        return ValidationStats(0, 0.0, 0.0, 0.0, {}, {})

    within = sum(1 for r in recs if r.within_band)
    finite_pct = [r.pct_error for r in recs if r.pct_error != float("inf")]

    def _group(key_fn) -> Dict[str, dict]:
        groups: Dict[str, list] = {}
        for r in recs:
            groups.setdefault(key_fn(r), []).append(r)
        out = {}
        for k, rs in groups.items():
            fp = [r.pct_error for r in rs if r.pct_error != float("inf")]
            out[k] = {
                "n": len(rs),
                "within_band_rate_pct": round(sum(1 for r in rs if r.within_band) / len(rs) * 100, 1),
                "mean_abs_error": round(mean(r.abs_error for r in rs), 3),
                "mean_pct_error": round(mean(fp), 1) if fp else None,
            }
        return out

    return ValidationStats(
        n=n,
        within_band_rate_pct=round(within / n * 100, 1),
        mean_abs_error=round(mean(r.abs_error for r in recs), 3),
        mean_pct_error=round(mean(finite_pct), 1) if finite_pct else 0.0,
        per_parameter=_group(lambda r: r.parameter),
        per_site=_group(lambda r: r.site),
    )
