"""Engine 2 — Internal Sediment Loading (Fe-P redox coupling).

Chain link: Sediment Interactions + Fe-P Coupling.

Scientific basis (Mortimer 1941; Boström et al. 1988): phosphate is held at the
oxidised sediment surface bound to ferric iron oxyhydroxides. When the
sediment-water interface turns reducing, Fe(III) is reduced to soluble Fe(II)
and the bound phosphate is released into the water column:

        Fe(OOH)~PO4  +  e⁻   →   Fe²⁺  +  PO4³⁻

Release risk therefore rises as:
  • dissolved oxygen falls (oxic → hypoxic → anoxic),
  • redox potential ORP falls below ~ +200 mV (Mortimer's critical boundary),
  • temperature rises (Q10≈2 microbial O2 demand deepens hypoxia),
  • the mobile-P sediment pool is larger (organic / post-bloom sediment),
  • ambient water-column phosphate is already elevated (corroborating release).

Inputs DO, temperature and phosphate come from the standard WaterReading.
ORP and sediment_state are optional richer inputs; when ORP is absent it is
estimated from DO and confidence is noted. Output is a LOW/MODERATE/HIGH/SEVERE
category with the contributing sub-scores. All thresholds from config.py.
"""
from __future__ import annotations

from typing import Optional

from . import config
from .models import SedimentLoadingResult


def _do_subscore(do: float) -> tuple[float, str]:
    """0 (P retained) → 1 (P released) from dissolved oxygen."""
    if do >= config.SEDIMENT_DO_OXIC:
        return 0.0, f"DO {do:.1f} mg/L oxic (≥{config.SEDIMENT_DO_OXIC:g}) — Fe oxidised, P retained."
    if do <= config.SEDIMENT_DO_ANOXIC:
        return 1.0, f"DO {do:.1f} mg/L anoxic (≤{config.SEDIMENT_DO_ANOXIC:g}) — strong P release."
    # Linear ramp across the hypoxic band.
    frac = (config.SEDIMENT_DO_OXIC - do) / (config.SEDIMENT_DO_OXIC - config.SEDIMENT_DO_ANOXIC)
    return frac, f"DO {do:.1f} mg/L hypoxic — partial P release (sub-score {frac:.2f})."


def _orp_subscore(orp: float) -> tuple[float, str]:
    """0 (P retained) → 1 (P released) from redox potential (mV)."""
    if orp >= config.SEDIMENT_ORP_OXIC:
        return 0.0, f"ORP {orp:.0f} mV oxidising (≥{config.SEDIMENT_ORP_OXIC:g}) — P retained."
    if orp <= config.SEDIMENT_ORP_REDUCING:
        return 1.0, f"ORP {orp:.0f} mV reducing (≤{config.SEDIMENT_ORP_REDUCING:g}) — active P release."
    frac = (config.SEDIMENT_ORP_OXIC - orp) / (config.SEDIMENT_ORP_OXIC - config.SEDIMENT_ORP_REDUCING)
    return frac, f"ORP {orp:.0f} mV transitional — partial P release (sub-score {frac:.2f})."


def _estimate_orp_from_do(do: float) -> float:
    """Rough ORP proxy when no probe data: map DO oxic→reducing onto the ORP ladder."""
    do_frac, _ = _do_subscore(do)        # 0 oxic → 1 anoxic
    # Invert onto ORP range [reducing .. oxic].
    return config.SEDIMENT_ORP_OXIC - do_frac * (config.SEDIMENT_ORP_OXIC - config.SEDIMENT_ORP_REDUCING)


def _temp_factor(temp_c: float) -> tuple[float, str]:
    """Q10 acceleration multiplier relative to the reference temperature."""
    factor = config.SEDIMENT_TEMP_Q10 ** ((temp_c - config.SEDIMENT_TEMP_REF) / 10.0)
    return factor, (f"Temperature {temp_c:.0f}°C → ×{factor:.2f} microbial O2-demand "
                    f"(Q10={config.SEDIMENT_TEMP_Q10:g}, ref {config.SEDIMENT_TEMP_REF:g}°C).")


def _po4_corroboration(phosphate: float) -> tuple[float, str]:
    """Elevated ambient PO4 raises severity (0..0.2 additive corroboration)."""
    if phosphate >= config.SEDIMENT_PO4_HIGH:
        return 0.20, f"Water-column PO4 {phosphate:.1f} mg/L high — corroborates active release."
    if phosphate >= config.SEDIMENT_PO4_ELEVATED:
        return 0.10, f"Water-column PO4 {phosphate:.1f} mg/L elevated."
    return 0.0, f"Water-column PO4 {phosphate:.1f} mg/L not elevated."


def _band(score: float) -> str:
    for threshold, label in config.SEDIMENT_BANDS:
        if score < threshold:
            return label
    return config.SEDIMENT_BANDS[-1][1]


def assess_internal_loading(
    do: float,
    temperature: float,
    phosphate: float,
    orp: Optional[float] = None,
    sediment_state: str = "normal",
) -> SedimentLoadingResult:
    """Assess Fe-P internal phosphorus loading risk.

    Args:
        do:             Near-bottom dissolved oxygen (mg/L).
        temperature:    Water temperature (°C).
        phosphate:      Water-column phosphate (mg/L).
        orp:            Redox potential (mV). If None, estimated from DO.
        sediment_state: One of config.SEDIMENT_STATE_FACTOR keys.

    Returns:
        SedimentLoadingResult with LOW/MODERATE/HIGH/SEVERE and sub-scores.
    """
    reasoning: list[str] = []

    do_score, do_msg = _do_subscore(do)
    reasoning.append(do_msg)

    if orp is None:
        orp = _estimate_orp_from_do(do)
        reasoning.append(f"ORP not supplied — estimated {orp:.0f} mV from DO (lower confidence).")
    orp_score, orp_msg = _orp_subscore(orp)
    reasoning.append(orp_msg)

    # Redox driver = the more reducing of the two independent indicators.
    redox_score = max(do_score, orp_score)

    temp_factor, temp_msg = _temp_factor(temperature)
    reasoning.append(temp_msg)

    state_factor = config.SEDIMENT_STATE_FACTOR.get(
        sediment_state, config.SEDIMENT_STATE_FACTOR["normal"])
    reasoning.append(
        f"Sediment state '{sediment_state}' → ×{state_factor:g} mobile-P pool.")

    po4_add, po4_msg = _po4_corroboration(phosphate)
    reasoning.append(po4_msg)

    # Combine: redox is the master switch; temperature & sediment state amplify;
    # phosphate corroborates. Clamp to [0,1].
    score = redox_score * temp_factor * state_factor + po4_add
    score = max(0.0, min(score, 1.0))

    level = _band(score)
    release = {
        "LOW": "Negligible internal P release — sediment retaining phosphate.",
        "MODERATE": "Intermittent internal P release likely under calm/warm spells.",
        "HIGH": "Sustained internal P release feeding the water column.",
        "SEVERE": "Strong internal P release — sediment is a dominant nutrient source.",
    }[level]
    reasoning.append(
        f"Combined internal-loading score {score:.2f} → {level}. {release}")

    return SedimentLoadingResult(
        level=level,
        score=round(score, 3),
        estimated_release=release,
        drivers={
            "redox": round(redox_score, 3),
            "temperature_factor": round(temp_factor, 3),
            "sediment_state_factor": round(state_factor, 3),
            "phosphate_corroboration": round(po4_add, 3),
        },
        reasoning=reasoning,
    )
