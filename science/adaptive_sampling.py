"""Adaptive Sampling Optimizer.

This is the client-facing payoff of the whole stack. Given each lagoon's
calibrated prediction confidence, days since its last real sample, and risk
state, it answers the questions the client pays for:

  • Which lagoons must be sampled this cycle?
  • Which can be safely skipped (model confident + within regulatory cadence)?
  • What does that save versus sampling everything?
  • If we sample one more, which lagoon most reduces portfolio uncertainty?

It NEVER goes below the DECCA regulatory floor: any lagoon overdue against the
mandated cadence is always sampled. The confidence numbers it consumes are
produced by the (hidden) driver model + calibration layer; this module only
sees confidence in, recommendation out.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from . import config


@dataclass
class LagoonStatus:
    """Per-lagoon input to the optimizer."""
    site: str
    confidence_pct: float
    days_since_sample: float
    risk_level: Optional[str] = None          # e.g. bloom severity / op risk
    headline: str = ""                        # short predicted-state summary


@dataclass
class SamplingRecommendation:
    site: str
    action: str                               # "SAMPLE" / "SKIP"
    reason: str                               # regulatory / risk / uncertainty / confident
    confidence_pct: float
    days_since_sample: float
    headline: str = ""


@dataclass
class PortfolioPlan:
    n_lagoons: int
    n_sample: int
    n_skip: int
    samples_saved_this_cycle: int
    cost_saved_aed: float
    annual_cost_saved_aed: float
    mean_confidence_pct: float
    next_best_to_sample: Optional[str]
    recommendations: List[SamplingRecommendation] = field(default_factory=list)
    reasoning: List[str] = field(default_factory=list)


def recommend_one(status: LagoonStatus,
                  floor_days: float = config.DECCA_MIN_SAMPLING_DAYS) -> SamplingRecommendation:
    """Decide SAMPLE/SKIP for a single lagoon, honouring the regulatory floor."""
    s = status
    if s.days_since_sample >= floor_days:
        return SamplingRecommendation(s.site, "SAMPLE", "Regulatory floor — mandated cadence due",
                                      s.confidence_pct, s.days_since_sample, s.headline)
    if s.risk_level and s.risk_level.upper() == config.ADAPTIVE_RISK_FORCE:
        return SamplingRecommendation(s.site, "SAMPLE", "High operational risk",
                                      s.confidence_pct, s.days_since_sample, s.headline)
    if s.confidence_pct < config.ADAPTIVE_CONF_THRESHOLD:
        return SamplingRecommendation(s.site, "SAMPLE", "Confidence below threshold",
                                      s.confidence_pct, s.days_since_sample, s.headline)
    return SamplingRecommendation(s.site, "SKIP", "Model confident & within cadence",
                                  s.confidence_pct, s.days_since_sample, s.headline)


def optimize_portfolio(
    statuses: List[LagoonStatus],
    floor_days: float = config.DECCA_MIN_SAMPLING_DAYS,
    cost_per_sample: float = config.SAMPLING_COST_AED,
    cycles_per_year: int = 12,
) -> PortfolioPlan:
    """Produce the portfolio sampling plan + savings versus sampling everything."""
    recs = [recommend_one(s, floor_days) for s in statuses]
    n = len(statuses)
    n_sample = sum(1 for r in recs if r.action == "SAMPLE")
    n_skip = n - n_sample

    cost_saved = n_skip * cost_per_sample
    annual_saved = cost_saved * cycles_per_year
    mean_conf = round(sum(s.confidence_pct for s in statuses) / n, 1) if n else 0.0

    # Next best to sample among those currently SKIP: the one whose sampling most
    # reduces portfolio uncertainty — lowest confidence (tie-break: most overdue).
    skip_candidates = [r for r in recs if r.action == "SKIP"]
    next_best = None
    if skip_candidates:
        nb = min(skip_candidates, key=lambda r: (r.confidence_pct, -r.days_since_sample))
        next_best = nb.site

    reasoning = [
        f"{n_sample} of {n} lagoons need sampling this cycle; {n_skip} can be skipped.",
        f"Skipping {n_skip} saves {cost_saved:,.0f} AED/cycle "
        f"(~{annual_saved:,.0f} AED/year at {cycles_per_year} cycles).",
        f"Portfolio mean confidence {mean_conf:.0f}%.",
    ]
    if next_best:
        reasoning.append(f"If one extra sample is taken, prioritise {next_best} "
                         "(lowest confidence) to most reduce portfolio uncertainty.")

    return PortfolioPlan(
        n_lagoons=n, n_sample=n_sample, n_skip=n_skip,
        samples_saved_this_cycle=n_skip, cost_saved_aed=round(cost_saved, 0),
        annual_cost_saved_aed=round(annual_saved, 0), mean_confidence_pct=mean_conf,
        next_best_to_sample=next_best, recommendations=recs, reasoning=reasoning,
    )
