"""Engine 6 — Algae Community / Type.

Chain link: Bloom Formation (which community, not just how much).

Predicts the FAVOURED phytoplankton group and the ecological succession stage
from the water-quality drivers we already collect — temperature, dissolved
oxygen, the ammonia:phosphate (reduced-N:P) ratio, chlorophyll-a and salinity.
No lab species identification is required.

The measured phycocyanin:chlorophyll-a ratio is used only as an observational
*anchor* — phycocyanin is the cyanobacteria pigment, so a high ratio is direct
evidence of cyanobacterial dominance. The prediction is made from the drivers
and then reconciled with this measured signal; agreement raises confidence,
disagreement lowers it (and flags a lab test).

Design (Architecture.md): pure Python, explainable, thresholds in config.py,
no hidden decisions. This engine borrows the ecological *ideas* (cyanobacteria
competitive advantage + succession) from prior art — none of the numbers or
code are copied.
"""
from __future__ import annotations

from typing import Optional

from . import config
from .models import CommunityForecast


def _ramp(x: float, lo: float, hi: float) -> float:
    """Linear 0→1 ramp between lo and hi, clamped."""
    if hi == lo:
        return 0.0 if x < lo else 1.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def _norm(scores: dict[str, float]) -> dict[str, float]:
    """Normalise a dict of non-negative scores to sum to 1 (uniform if all zero)."""
    total = sum(scores.values())
    if total <= 0:
        n = len(scores)
        return {k: round(1.0 / n, 3) for k in scores}
    return {k: round(v / total, 3) for k, v in scores.items()}


def trophic_state(chla: float) -> str:
    """Carlson-style trophic classification from chlorophyll-a (µg/L)."""
    for ceiling, label in config.TROPHIC_CHLA_BANDS:
        if chla < ceiling:
            return label
    return config.TROPHIC_CHLA_BANDS[-1][1]


def cyanobacteria_advantage(temperature: float, n_p_ratio: Optional[float],
                            dissolved_oxygen: float) -> float:
    """Competitive advantage of cyanobacteria over other groups (0–1).

    Warm water, low N:P (reduced-N limitation favours N-fixers) and low DO all
    favour cyanobacteria. Missing N:P falls back to the temperature + DO terms.
    """
    w = config.CYANO_ADV_WEIGHTS

    temp_fav = _ramp(temperature, config.CYANO_TEMP_MIN, config.CYANO_TEMP_FULL)
    if temperature < config.CYANO_TEMP_TRACE:
        temp_fav = 0.0

    do_fav = 1.0 - _ramp(dissolved_oxygen, config.CYANO_DO_FULL, config.CYANO_DO_NONE)

    score = temp_fav * w["temperature"] + do_fav * w["dissolved_oxygen"]
    used = w["temperature"] + w["dissolved_oxygen"]

    if n_p_ratio is not None:
        # Low N:P → full advantage; above Redfield → none.
        np_fav = 1.0 - _ramp(n_p_ratio, config.CYANO_NP_FULL, config.CYANO_NP_REDFIELD)
        score += np_fav * w["n_p_ratio"]
        used += w["n_p_ratio"]

    return round(score / used if used else 0.0, 3)


def classify_community(
    temperature: Optional[float] = None,
    dissolved_oxygen: Optional[float] = None,
    ammonia: Optional[float] = None,
    phosphate: Optional[float] = None,
    chla: Optional[float] = None,
    phycocyanin: Optional[float] = None,
    salinity: Optional[float] = None,
    nitrate: Optional[float] = None,
    orp: Optional[float] = None,
    residence_time_days: float = 0.0,
    internal_loading_score: float = 0.0,
    historical_bloom_count: int = 0,
) -> CommunityForecast:
    """Predict the favoured algae group + succession stage from a reading.

    All required inputs are fields we already collect; `phycocyanin` and `chla`
    form the measured pigment anchor. `nitrate` and `orp` are optional and, when
    absent, are surfaced as data-request items that would strengthen the call.
    Any required input passed as None is reported in `missing_inputs`.
    """
    reasoning: list[str] = []

    # ── Data completeness: what is missing / would strengthen the call ──
    provided = {
        "temperature": temperature, "dissolved_oxygen": dissolved_oxygen,
        "ammonia": ammonia, "phosphate": phosphate, "salinity": salinity,
        "chla": chla, "phycocyanin": phycocyanin,
    }
    missing_inputs = [config.COMMUNITY_REQUIRED_INPUTS[k]
                      for k, v in provided.items() if v is None]
    enhancing_inputs = [config.COMMUNITY_ENHANCING_INPUTS[k]
                        for k, v in (("nitrate", nitrate), ("orp", orp)) if v is None]

    # Neutral fallbacks so the math is defined even with a partial reading; a
    # non-empty missing_inputs lowers confidence below.
    temperature = temperature if temperature is not None else 25.0
    dissolved_oxygen = dissolved_oxygen if dissolved_oxygen is not None else 5.0
    ammonia = ammonia if ammonia is not None else 0.0
    phosphate = phosphate if phosphate is not None else 0.0
    salinity = salinity if salinity is not None else 45.0
    chla = chla if chla is not None else 0.0
    phycocyanin = phycocyanin if phycocyanin is not None else 0.0

    # ── Derived signals ──
    # Use total-N (ammonia + nitrate) when nitrate is available; else ammonia proxy.
    total_n = ammonia + (nitrate or 0.0)
    n_p_ratio = round(total_n / phosphate, 2) if phosphate > 0 else None
    n_label = "total-N:P" if nitrate is not None else "N:P (ammonia proxy)"
    phyco_chla = round(phycocyanin / chla, 2) if chla > 0 else None
    troph = trophic_state(chla)
    cyano_adv = cyanobacteria_advantage(temperature, n_p_ratio, dissolved_oxygen)

    if n_p_ratio is not None:
        reasoning.append(
            f"{n_label} = {n_p_ratio} "
            f"({'low — favours cyanobacteria' if n_p_ratio < config.CYANO_NP_MOD else 'N-replete — favours greens/diatoms'}).")
    reasoning.append(f"Trophic state {troph} (chlorophyll-a {chla:g} µg/L). "
                     f"Cyanobacteria competitive advantage {cyano_adv:.2f}.")

    # ── Bloom magnitude (reuses Engine 4) drives the succession stage ──
    from .bloom_forecast import forecast_bloom
    bloom = forecast_bloom(
        temperature=temperature, phosphate=phosphate, ammonia=ammonia,
        dissolved_oxygen=dissolved_oxygen, salinity=salinity,
        residence_time_days=residence_time_days,
        internal_loading_score=internal_loading_score,
        historical_bloom_count=historical_bloom_count,
    )
    bloom_prob = bloom.severity_score   # 0–1

    # ── Per-group favourabilities (0..1), from the drivers ──
    warm = _ramp(temperature, config.GREEN_TEMP_LOW, config.GREEN_TEMP_HIGH)
    good_do = _ramp(dissolved_oxygen, config.CYANO_DO_NONE, config.DIATOM_DO_GOOD)
    # Higher N:P → nitrogen-replete → favours diatoms/greens over N-fixing cyano.
    n_replete = _ramp(n_p_ratio, config.CYANO_NP_MOD, config.CYANO_NP_REDFIELD) if n_p_ratio is not None else 0.5
    saline = _ramp(salinity, config.DINO_SAL_LOW, config.DINO_SAL_HIGH)

    model_scores = {
        # Cyanobacteria: their competitive advantage, amplified by bloom pressure.
        "cyanobacteria":   0.15 + cyano_adv * (0.6 + 0.4 * bloom_prob),
        # Green algae: the transitional middle — warm-ish, nutrient-rich, not extreme.
        "green_algae":     0.20 + 0.5 * warm * (0.5 + 0.5 * bloom_prob) * (1.0 - cyano_adv),
        # Diatoms: cool/well-mixed, N-replete, low bloom pressure = the stable baseline.
        "diatoms":         0.20 + 0.6 * good_do * n_replete * (1.0 - bloom_prob),
        # Dinoflagellates: warm + saline + stratified, but not N-limited.
        "dinoflagellates": 0.10 + 0.5 * warm * saline * n_replete,
    }
    model_probs = _norm(model_scores)

    # ── Reconcile with the measured pigment anchor (phycocyanin:chla) ──
    observed_cyano: Optional[float] = None
    if phyco_chla is not None:
        observed_cyano = _ramp(phyco_chla, config.PHYCO_CHLA_LOW, config.PHYCO_CHLA_HIGH)
        w = config.COMMUNITY_PIGMENT_WEIGHT
        blended_cyano = (1 - w) * model_probs["cyanobacteria"] + w * observed_cyano
        # Redistribute the change across the other groups proportionally.
        others = {k: v for k, v in model_probs.items() if k != "cyanobacteria"}
        rem = max(0.0, 1.0 - blended_cyano)
        others_norm = _norm(others)
        probs = {"cyanobacteria": round(blended_cyano, 3),
                 **{k: round(rem * v, 3) for k, v in others_norm.items()}}
    else:
        probs = model_probs

    probs = _norm(probs)  # tidy rounding
    dominant = max(probs, key=probs.get)
    ranked = sorted(probs.values(), reverse=True)
    margin = ranked[0] - (ranked[1] if len(ranked) > 1 else 0.0)

    reasoning.append("Group probabilities: " + ", ".join(
        f"{k} {probs[k]*100:.0f}%" for k in sorted(probs, key=probs.get, reverse=True)) + ".")

    # ── Observational agreement + confidence ──
    if observed_cyano is not None:
        agreement = 1.0 - abs(model_probs["cyanobacteria"] - observed_cyano)
        if observed_cyano >= 0.5 and dominant == "cyanobacteria":
            observed_signal = (f"Phycocyanin:chl-a {phyco_chla} confirms cyanobacteria dominance "
                               f"— prediction and pigment agree.")
        elif observed_cyano >= 0.5:
            observed_signal = (f"Phycocyanin:chl-a {phyco_chla} shows elevated cyanobacteria pigment "
                               f"despite a {dominant} driver signal — treat as cyano-suspect.")
        else:
            observed_signal = (f"Phycocyanin:chl-a {phyco_chla} is low — little cyanobacteria pigment; "
                               f"consistent with a {dominant} community.")
        confidence = 45.0 + 35.0 * agreement + 20.0 * margin
    else:
        observed_signal = "No phycocyanin/chlorophyll pair — prediction is driver-only (unanchored)."
        confidence = 40.0 + 30.0 * margin
    # Missing required inputs erode confidence (10 pts each).
    confidence -= 10.0 * len(missing_inputs)
    confidence = round(max(20.0, min(confidence, 95.0)), 1)
    reasoning.append(observed_signal)
    if missing_inputs:
        reasoning.append("Missing required input(s): " + ", ".join(missing_inputs) +
                         " — provide these for a firmer call.")

    # ── Ecological succession stage ──
    if dissolved_oxygen < config.SUCCESSION_COLLAPSE_DO:
        stage = "post_bloom_collapse"
    elif bloom_prob >= config.SUCCESSION_ACTIVE_PROB:
        stage = "active_bloom"
    elif dominant == "cyanobacteria" or cyano_adv >= 0.5 or bloom_prob >= config.SUCCESSION_CYANO_PROB:
        stage = "cyanobacteria_risk"
    elif dominant == "green_algae" or bloom_prob >= config.SUCCESSION_GREEN_PROB:
        stage = "green_algae_phase"
    else:
        stage = "stable_diatoms"
    reasoning.append(f"Succession stage: {stage} (bloom pressure {bloom_prob:.2f}, DO {dissolved_oxygen:g} mg/L).")

    # ── Confirmatory lab tests (when cyanobacteria are favoured) ──
    lab_recommend = False
    lab_reason = ""
    recommended_tests: list[str] = []
    triggers: list[str] = []
    if cyano_adv >= config.CYANO_LAB_TEST_ADVANTAGE:
        triggers.append(f"cyanobacteria advantage {cyano_adv:.2f}")
    if phyco_chla is not None and phyco_chla >= config.PHYCO_CHLA_LAB_TEST:
        triggers.append(f"elevated phycocyanin:chl-a {phyco_chla}")
    if observed_cyano is not None and observed_cyano >= 0.5 and dominant != "cyanobacteria":
        triggers.append("pigment/driver disagreement")
    if triggers:
        lab_recommend = True
        recommended_tests = list(config.COMMUNITY_CONFIRMATORY_TESTS)
        lab_reason = ("Recommend a confirmatory phytoplankton identification and cyanotoxin "
                      "(e.g. microcystin) lab test — triggered by " + "; ".join(triggers) + ".")
        reasoning.append(lab_reason)

    return CommunityForecast(
        dominant_group=dominant,
        group_probabilities=probs,
        succession_stage=stage,
        cyano_advantage=cyano_adv,
        trophic_state=troph,
        n_p_ratio=n_p_ratio,
        phyco_chla_ratio=phyco_chla,
        observed_signal=observed_signal,
        confidence_pct=confidence,
        lab_test_recommended=lab_recommend,
        lab_test_reason=lab_reason,
        missing_inputs=missing_inputs,
        enhancing_inputs=enhancing_inputs,
        recommended_tests=recommended_tests,
        reasoning=reasoning,
    )
