"""Result dataclasses for the scientific engines.

Every result type carries an explicit `reasoning` list so that no output is a
bare number — the operator can always see *why* (Architecture.md: "Explainable",
"No hidden AI decisions").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class NutrientAttribution:
    """Engine 1 — relative nutrient source contributions."""
    sources_pct: Dict[str, float]        # source_key -> % contribution (sums ~100)
    dominant_source: str
    confidence_pct: float                # 0–100
    reasoning: List[str] = field(default_factory=list)


@dataclass
class SedimentLoadingResult:
    """Engine 2 — Fe-P internal loading risk."""
    level: str                           # LOW / MODERATE / HIGH / SEVERE
    score: float                         # 0–1 internal-loading score
    estimated_release: str               # qualitative P-release statement
    drivers: Dict[str, float] = field(default_factory=dict)   # named sub-scores
    reasoning: List[str] = field(default_factory=list)


@dataclass
class ResidenceTimeResult:
    """Engine 3 — hydraulic residence + flushing."""
    residence_time_days: float
    flushing_efficiency_pct: float       # 0–100
    risk_score: float                    # 0–1
    risk_level: str                      # LOW / MODERATE / HIGH / SEVERE
    reasoning: List[str] = field(default_factory=list)


@dataclass
class BloomForecast:
    """Engine 4 — bloom probability / severity / recovery."""
    probability_pct: float               # 0–100
    severity: str                        # MINIMAL / MODERATE / SIGNIFICANT / SEVERE
    severity_score: float                # 0–1
    recovery_time_days: float
    drivers: Dict[str, float] = field(default_factory=dict)   # per-driver contribution (0–1)
    reasoning: List[str] = field(default_factory=list)


@dataclass
class CommunityForecast:
    """Engine 6 — likely phytoplankton community / algae type.

    Predicts which algae group is favoured (and the ecological succession stage)
    from the water-quality drivers alone — no lab species ID required. The
    measured phycocyanin:chlorophyll-a ratio is used only as an observational
    anchor (a cyanobacteria pigment proxy), never as a required input.
    """
    dominant_group: str                        # cyanobacteria / green_algae / diatoms / dinoflagellates
    group_probabilities: Dict[str, float]      # group -> 0–1 (sums ~1)
    succession_stage: str                      # stable_diatoms → … → post_bloom_collapse
    cyano_advantage: float                     # 0–1 competitive advantage of cyanobacteria
    trophic_state: str                         # oligotrophic / mesotrophic / eutrophic / hypereutrophic
    n_p_ratio: Optional[float]                 # ammonia:phosphate (reduced-N proxy)
    phyco_chla_ratio: Optional[float]          # measured cyanobacteria pigment marker
    observed_signal: str                       # what the pigment says + agreement with the prediction
    confidence_pct: float                      # 0–100
    lab_test_recommended: bool = False         # SaaS should request a confirmatory lab test
    lab_test_reason: str = ""                  # what test to run and why (empty when not recommended)
    missing_inputs: List[str] = field(default_factory=list)      # required drivers absent from the reading
    enhancing_inputs: List[str] = field(default_factory=list)    # params not captured that would strengthen the call
    recommended_tests: List[str] = field(default_factory=list)   # confirmatory lab tests (when cyano-favoured)
    reasoning: List[str] = field(default_factory=list)


@dataclass
class TwinScenarioResult:
    """Engine 5 — what-if scenario outcome."""
    scenario: str
    baseline_bloom_pct: float
    projected_bloom_pct: float
    expected_bloom_reduction_pct: float  # positive = improvement
    timeline_days: float
    recommendation: str
    reasoning: List[str] = field(default_factory=list)


@dataclass
class Prediction:
    """A model forecast for one parameter at one lagoon/month, with a band."""
    site: str
    year: int
    month: int
    parameter: str               # key in config.PREDICTED_PARAMETERS
    predicted: float
    band_low: float
    band_high: float
    confidence_pct: float        # 0–100, reflects band width / decay
    months_since_sample: float
    extrapolated: bool           # inferred from sentinels vs own trend
    reasoning: List[str] = field(default_factory=list)


@dataclass
class ValidationRecord:
    """Outcome of checking one prediction against the real sampled value."""
    site: str
    year: int
    month: int
    parameter: str
    predicted: float
    actual: float
    band_low: float
    band_high: float
    within_band: bool
    abs_error: float
    pct_error: float             # |actual-predicted| / |actual| * 100
    verdict: str                 # ON-TRACK / DRIFT


@dataclass
class ValidationStats:
    """Aggregate accuracy across many validations."""
    n: int
    within_band_rate_pct: float  # % of predictions whose actual fell in-band
    mean_abs_error: float
    mean_pct_error: float
    per_parameter: Dict[str, dict] = field(default_factory=dict)
    per_site: Dict[str, dict] = field(default_factory=dict)
