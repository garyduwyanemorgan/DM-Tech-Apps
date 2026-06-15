"""Engine 3 — Hydraulic Residence Time.

Chain link: Hydraulic Transport.

Residence (flushing) time is the average time water spends in the lagoon:

        τ = V / Q_net_outflow        [days]

with volume V in m³ and flow Q in m³/day. Recirculation re-uses water inside
the lagoon and does not export nutrients, so it is discounted from the net
flushing flow. Long residence time → nutrient accumulation, stratification and
bloom development; short residence time → the lagoon is well flushed.

All thresholds come from science/config.py. Pure function, fully explainable.
"""
from __future__ import annotations

from . import config
from .models import ResidenceTimeResult


def _band(value: float, bands) -> str:
    for threshold, label in bands:
        if value < threshold:
            return label
    return bands[-1][1]


def compute_residence_time(
    volume_m3: float,
    inflow_m3_day: float,
    outflow_m3_day: float,
    recirculation_m3_day: float = 0.0,
) -> ResidenceTimeResult:
    """Compute residence time, flushing efficiency and a 0–1 risk score.

    Args:
        volume_m3:            Lagoon water volume (m³).
        inflow_m3_day:        Total inflow (m³/day).
        outflow_m3_day:       Total outflow / exchange to outside (m³/day).
        recirculation_m3_day: Internal recirculation flow (m³/day). Discounted
                              from net flushing per config.RESIDENCE_RECIRC_DISCOUNT.

    Returns:
        ResidenceTimeResult with reasoning.
    """
    reasoning: list[str] = []

    if volume_m3 <= 0:
        raise ValueError("volume_m3 must be positive")
    if inflow_m3_day < 0 or outflow_m3_day < 0 or recirculation_m3_day < 0:
        raise ValueError("flows must be non-negative")

    # Net flushing flow exports water from the system. Recirculation is internal
    # and removes nothing, so we subtract the discounted recirculation from the
    # outflow that would otherwise count as flushing.
    discounted_recirc = recirculation_m3_day * config.RESIDENCE_RECIRC_DISCOUNT
    net_flushing = max(outflow_m3_day - discounted_recirc, 0.0)

    if net_flushing <= 0:
        # No net export — effectively closed. Residence time is unbounded.
        reasoning.append(
            "No net flushing flow (outflow offset by recirculation) → "
            "lagoon is effectively closed; nutrients cannot leave.")
        return ResidenceTimeResult(
            residence_time_days=float("inf"),
            flushing_efficiency_pct=0.0,
            risk_score=1.0,
            risk_level="SEVERE",
            reasoning=reasoning,
        )

    residence = volume_m3 / net_flushing
    reasoning.append(
        f"τ = V/Q = {volume_m3:,.0f} m³ / {net_flushing:,.0f} m³·day⁻¹ "
        f"= {residence:.1f} days net flushing.")

    if recirculation_m3_day > 0:
        reasoning.append(
            f"Recirculation {recirculation_m3_day:,.0f} m³·day⁻¹ discounted "
            f"(×{config.RESIDENCE_RECIRC_DISCOUNT:g}) — internal loop does not export nutrients.")

    # Flushing efficiency: fraction of inflow that is actually exported.
    if inflow_m3_day > 0:
        flushing_eff = min(net_flushing / inflow_m3_day, 1.0) * 100.0
    else:
        flushing_eff = 0.0
    reasoning.append(
        f"Flushing efficiency = net flushing / inflow = {flushing_eff:.0f}%.")

    # Risk score saturates with residence time.
    risk = min(residence / config.RESIDENCE_RISK_SATURATION, 1.0)
    level = _band(residence, config.RESIDENCE_BANDS)
    reasoning.append(
        f"Residence {residence:.0f} d → {level} stagnation risk "
        f"(score {risk:.2f}; saturates at {config.RESIDENCE_RISK_SATURATION:g} d).")

    return ResidenceTimeResult(
        residence_time_days=round(residence, 1),
        flushing_efficiency_pct=round(flushing_eff, 1),
        risk_score=round(risk, 3),
        risk_level=level,
        reasoning=reasoning,
    )
