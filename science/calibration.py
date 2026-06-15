"""Calibration / data-assimilation layer  —  INTERNAL, never surfaced client-facing.

Corrects the process model against real samples and quantifies the remaining
uncertainty. We infer a multiplicative bias factor θ per parameter (θ = 1 means
the model is unbiased) in log-space with an exact conjugate-Gaussian Bayesian
update:

    log(observed / model_prediction)  ~  Normal(log θ, σ_obs²)
    prior  log θ  ~  Normal(0, σ_prior²)

The posterior is Gaussian (closed form) — no MCMC needed for this 1-D-per-
parameter regime. It works from zero observations (posterior = prior → wide,
low confidence) and tightens with every sample assimilated. As multi-year,
multi-parameter data accumulates and the forward model becomes nonlinear, this
is where tinyDA's delayed-acceptance MCMC drops in as the heavy engine — the
interface (assimilate → corrected prediction + confidence) is identical.

ONLY the *output* (corrected value + confidence) is allowed to surface, and
even then without naming this layer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from . import config


@dataclass
class Calibration:
    """Posterior bias-correction for one parameter."""
    parameter: str
    n_obs: int
    correction_factor: float         # θ posterior mean (exp of log-mean)
    post_log_mean: float
    post_log_std: float              # parameter uncertainty (log-space)
    obs_log_std: float = config.CALIB_OBS_LOG_STD   # data-estimated residual noise
    reasoning: List[str] = field(default_factory=list)

    def predictive_log_std(self) -> float:
        """Total predictive uncertainty for a NEW prediction (param + residual noise).
        Residual noise is estimated from how well the model actually tracks this
        lagoon's samples, so an unpredictable lagoon yields wider bands."""
        return math.sqrt(self.post_log_std ** 2 + self.obs_log_std ** 2)


@dataclass
class CalibratedPrediction:
    """A process-model prediction after assimilation."""
    parameter: str
    value: float
    band_low: float
    band_high: float
    confidence_pct: float
    n_obs: int
    correction_factor: float


def assimilate(parameter: str, pairs: Sequence[Tuple[float, float]]) -> Calibration:
    """Bayesian update of the bias factor from (model_prediction, observed) pairs.

    Args:
        parameter: parameter key (for labelling only).
        pairs:     list of (model_predicted, observed) from validated samples.

    Returns:
        Calibration posterior (= prior when pairs is empty).
    """
    reasoning: List[str] = []
    prior_var = config.CALIB_PRIOR_LOG_STD ** 2
    obs_var = config.CALIB_OBS_LOG_STD ** 2

    # Usable log-ratios (both values strictly positive).
    logs = [math.log(o / m) for m, o in pairs if m > 0 and o > 0]
    n = len(logs)

    if n == 0:
        reasoning.append("No observations yet — posterior equals prior (θ≈1, wide band).")
        return Calibration(parameter, 0, 1.0, 0.0, config.CALIB_PRIOR_LOG_STD,
                           config.CALIB_OBS_LOG_STD, reasoning)

    # First pass: posterior mean with the prior residual-noise assumption.
    precision = 1.0 / prior_var + n / obs_var
    post_var = 1.0 / precision
    post_mean = post_var * (sum(logs) / obs_var)

    # Estimate residual noise from how well the bias-corrected model tracks the
    # samples (shrunk toward the prior so small n stays conservative).
    if n >= 3:
        resid = [l - post_mean for l in logs]
        emp_var = sum(r * r for r in resid) / (n - 1)
        k = 3.0   # prior strength in pseudo-observations
        eff_obs_var = (k * obs_var + n * emp_var) / (k + n)
        # Re-solve the posterior with the data-estimated noise.
        precision = 1.0 / prior_var + n / eff_obs_var
        post_var = 1.0 / precision
        post_mean = post_var * (sum(logs) / eff_obs_var)
    else:
        eff_obs_var = obs_var

    theta = math.exp(post_mean)
    post_std = math.sqrt(post_var)
    obs_std = math.sqrt(eff_obs_var)

    reasoning.append(f"Assimilated {n} observation(s): bias factor θ={theta:.3f} "
                     f"(model {'under' if theta>1 else 'over'}-predicts by "
                     f"{abs(theta-1)*100:.0f}%).")
    reasoning.append(f"Posterior log-std {post_std:.3f} (prior {config.CALIB_PRIOR_LOG_STD:.2f}); "
                     f"residual noise {obs_std:.3f} — reflects this lagoon's predictability.")

    return Calibration(parameter, n, round(theta, 4), post_mean,
                       post_std, obs_std, reasoning)


def _confidence_from_std(pred_log_std: float) -> float:
    """Map predictive log-std → confidence %."""
    lo, hi = config.CALIB_CONF_STD_FLOOR, config.CALIB_CONF_STD_CEIL
    frac = (pred_log_std - lo) / max(hi - lo, 1e-6)
    frac = max(0.0, min(frac, 1.0))
    conf = config.CALIB_CONF_MAX - frac * (config.CALIB_CONF_MAX - config.CALIB_CONF_MIN)
    return round(conf, 1)


def apply_calibration(cal: Calibration, model_value: float) -> CalibratedPrediction:
    """Apply a calibration to a fresh process-model prediction, returning the
    corrected value, credible band and confidence."""
    value = model_value * cal.correction_factor
    pls = cal.predictive_log_std()
    # Log-normal credible band at ~95%.
    band_low = value * math.exp(-1.96 * pls)
    band_high = value * math.exp(1.96 * pls)
    conf = _confidence_from_std(pls)
    return CalibratedPrediction(
        parameter=cal.parameter, value=round(value, 3),
        band_low=round(max(0.0, band_low), 3), band_high=round(band_high, 3),
        confidence_pct=conf, n_obs=cal.n_obs,
        correction_factor=cal.correction_factor,
    )
