"""Engine 1 — Nutrient Source Attribution.

Chain link: Nutrient Sources (head of the chain).

Estimates the relative contribution of five nutrient sources to the observed
lagoon nutrient load:

    TSE · Internal Loading · Runoff · Groundwater · Atmospheric

Method — explainable signature matching (NOT isotopic fingerprinting):
each source has a characteristic chemical signature in config.NUTRIENT_SIGNATURES
(N:P ratio, ammonia affinity, episodic vs continuous, salinity association).
We score how well the observed reading matches each signature, optionally
sharpened by context flags (recent rainfall, dust event, measured TSE inflow,
internal-loading risk from Engine 2), then normalise to percentages.

Confidence reflects (a) how distinct the winning match is and (b) how much
corroborating context was supplied. Without isotopes, confidence is capped
(config.NUTRIENT_MAX_CONFIDENCE).

This is a transparent prior-estimate to *prioritise investigation*, not a
legal source apportionment. Every contribution is accompanied by its reasoning.
"""
from __future__ import annotations

from typing import Dict, Optional

from . import config
from .models import NutrientAttribution


def _np_ratio(total_n: float, total_p: float) -> Optional[float]:
    if total_p <= 0:
        return None
    return total_n / total_p


def _signature_match(
    sig,
    np_ratio: Optional[float],
    ammonia_frac: float,
    salinity_norm: float,
) -> float:
    """Score 0..1 how well an observed reading matches one source signature."""
    score = 0.0
    weight = 0.0

    # N:P ratio proximity (log-distance — ratios span orders of magnitude).
    if np_ratio is not None and np_ratio > 0:
        import math
        d = abs(math.log10(np_ratio) - math.log10(sig.np_ratio))
        score += max(0.0, 1.0 - d)        # d=0 perfect, d≥1 decade off → 0
        weight += 1.0

    # Ammonia affinity: high reduced-N fraction matches high-affinity sources.
    score += 1.0 - abs(ammonia_frac - sig.ammonia_affinity)
    weight += 1.0

    # Salinity association: freshening (-1) ↔ saline (+1).
    score += 1.0 - abs(salinity_norm - sig.salinity_sign) / 2.0
    weight += 1.0

    return score / weight if weight else 0.0


def attribute_nutrient_sources(
    phosphate: float,
    ammonia: float,
    nitrate: float = 0.0,
    salinity: float = 45.0,
    *,
    recent_rainfall: bool = False,
    dust_event: bool = False,
    tse_inflow_high: bool = False,
    internal_loading_score: Optional[float] = None,
    salinity_baseline: float = 45.0,
) -> NutrientAttribution:
    """Attribute the nutrient load across the five sources.

    Args:
        phosphate:   Total phosphate (mg/L).
        ammonia:     Ammonia as N (mg/L).
        nitrate:     Nitrate as N (mg/L) if available; improves N:P.
        salinity:    Observed salinity (PSU).
        recent_rainfall:  Context flag — rain in the preceding days.
        dust_event:       Context flag — recent dust/sandstorm.
        tse_inflow_high:  Context flag — measured high TSE inflow.
        internal_loading_score: Engine 2 score (0–1) if available.
        salinity_baseline: Site's typical salinity (PSU) for freshening/saline sign.

    Returns:
        NutrientAttribution with source %, dominant source, confidence, reasoning.
    """
    reasoning: list[str] = []

    total_n = ammonia + nitrate
    total_p = phosphate
    np_ratio = _np_ratio(total_n, total_p)
    if np_ratio is not None:
        reasoning.append(f"Observed N:P ≈ {np_ratio:.1f} (N={total_n:.1f}, P={total_p:.1f} mg/L).")
    else:
        reasoning.append("Phosphate ~0 — N:P undefined; leaning on other signals.")

    ammonia_frac = ammonia / total_n if total_n > 0 else 0.0

    # Normalise salinity to [-1 freshening .. +1 saline] vs the site baseline.
    sal_norm = max(-1.0, min(1.0, (salinity - salinity_baseline) / max(salinity_baseline, 1e-6) * 3.0))
    reasoning.append(
        f"Salinity {salinity:.0f} PSU vs baseline {salinity_baseline:.0f} → "
        f"{'freshening' if sal_norm < -0.1 else 'saline' if sal_norm > 0.1 else 'neutral'} signal.")

    # ── Chemistry match per source ──
    raw: Dict[str, float] = {}
    for key, sig in config.NUTRIENT_SIGNATURES.items():
        raw[key] = _signature_match(sig, np_ratio, ammonia_frac, sal_norm)

    # ── Context adjustments ──
    ctx = config.NUTRIENT_CONTEXT_WEIGHT
    context_used = False
    if tse_inflow_high:
        raw["TSE"] += ctx; context_used = True
        reasoning.append("Context: high TSE inflow measured → boosts TSE attribution.")
    if recent_rainfall:
        raw["runoff"] += ctx; context_used = True
        reasoning.append("Context: recent rainfall → boosts runoff attribution.")
    if dust_event:
        raw["atmospheric"] += ctx; context_used = True
        reasoning.append("Context: dust event → boosts atmospheric attribution.")
    if internal_loading_score is not None:
        raw["internal_loading"] += ctx * internal_loading_score; context_used = True
        reasoning.append(
            f"Context: Engine-2 internal-loading score {internal_loading_score:.2f} "
            "→ boosts internal-loading attribution.")

    # ── Normalise to percentages ──
    total = sum(raw.values())
    if total <= 0:
        # Degenerate — distribute evenly.
        n = len(raw)
        pct = {k: round(100.0 / n, 1) for k in raw}
        return NutrientAttribution(
            sources_pct=pct, dominant_source="undetermined",
            confidence_pct=config.NUTRIENT_MIN_CONFIDENCE,
            reasoning=reasoning + ["No discriminating signal — even split, low confidence."])

    pct = {k: round(v / total * 100.0, 1) for k, v in raw.items()}
    dominant = max(pct, key=pct.get)

    # ── Confidence: distinctness of winner × context bonus ──
    sorted_vals = sorted(pct.values(), reverse=True)
    margin = (sorted_vals[0] - sorted_vals[1]) / 100.0 if len(sorted_vals) > 1 else 0.0
    base_conf = config.NUTRIENT_MIN_CONFIDENCE + margin * (
        config.NUTRIENT_MAX_CONFIDENCE - config.NUTRIENT_MIN_CONFIDENCE)
    if context_used:
        base_conf = min(base_conf + 8.0, config.NUTRIENT_MAX_CONFIDENCE)
    confidence = round(min(base_conf, config.NUTRIENT_MAX_CONFIDENCE), 1)

    reasoning.append(
        f"Dominant source: {config.NUTRIENT_SIGNATURES[dominant].name} "
        f"({pct[dominant]}%), margin {margin*100:.0f}pts → confidence {confidence}% "
        "(capped — isotopic confirmation would raise this).")

    return NutrientAttribution(
        sources_pct=pct,
        dominant_source=dominant,
        confidence_pct=confidence,
        reasoning=reasoning,
    )
