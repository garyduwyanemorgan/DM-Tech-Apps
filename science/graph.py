"""Causal graph builder — turns a diagnosis into a network for visualisation.

Maps a science.diagnose() result onto the causal chain from CONTEXT.md:

    Nutrient Sources → Hydraulic Transport → Sediment / Fe-P
        → Bloom Formation → Operational Risk

…and decorates it with the *live* diagnosis: node size scales with magnitude,
node colour with risk, and tooltips carry the reasoning. Pure function — emits
JSON-ready {nodes, edges} dicts that a vis-network front-end renders.
"""
from __future__ import annotations

from typing import Dict, List

from .config import NUTRIENT_SIGNATURES

# Risk → colour ramp shared with the rest of the dashboard.
_GREEN, _AMBER, _ORANGE, _RED, _GREY = "#27ae60", "#f39c12", "#e67e22", "#e74c3c", "#7f8c8d"

_LEVEL_COLOR = {
    "LOW": _GREEN, "MODERATE": _AMBER, "HIGH": _ORANGE, "SEVERE": _RED,
    "MINIMAL": _GREEN, "SIGNIFICANT": _ORANGE, "UNKNOWN": _GREY,
}


def _score_color(score: float) -> str:
    """0..1 → green→amber→orange→red."""
    if score < 0.25:
        return _GREEN
    if score < 0.5:
        return _AMBER
    if score < 0.75:
        return _ORANGE
    return _RED


def _size(base: float, score: float, lo: float = 14, hi: float = 46) -> float:
    return round(lo + (hi - lo) * max(0.0, min(score, 1.0)), 1)


def build_lagoon_graph(result: dict) -> Dict[str, List[dict]]:
    """Build {nodes, edges} for vis-network from a diagnose() result."""
    nodes: List[dict] = []
    edges: List[dict] = []

    summary = result["summary"]
    bloom = result["bloom_forecast"]
    sed = result["internal_loading"]
    nut = result["nutrient_attribution"]
    rt = result.get("residence_time")

    def node(nid, label, color, size, group, title):
        nodes.append({
            "id": nid, "label": label, "color": color, "size": size,
            "group": group, "title": title,
        })

    def edge(a, b, width=2, dashes=False, color="#5a6b7a"):
        edges.append({"from": a, "to": b, "width": width, "dashes": dashes, "color": color})

    # ── Spine: the causal chain stages ──
    bloom_score = bloom["severity_score"]
    node("bloom", f"Bloom Risk\n{summary['bloom_probability_pct']:.0f}%",
         _score_color(bloom_score), _size(0, bloom_score, 26, 56), "stage",
         f"Bloom probability {summary['bloom_probability_pct']:.0f}% — {summary['bloom_severity']}")

    op_color = _score_color(bloom_score)
    node("risk", "Operational Risk", op_color, _size(0, bloom_score, 22, 48), "risk",
         f"Recovery ≈ {summary['recovery_time_days']:.0f} days")
    edge("bloom", "risk", width=4, color=op_color)

    sed_score = sed["score"]
    node("sediment", f"Sediment Fe-P\n{sed['level']}",
         _LEVEL_COLOR.get(sed["level"], _GREY), _size(0, sed_score, 20, 46), "stage",
         sed["estimated_release"])
    edge("sediment", "bloom", width=2 + 4 * sed_score, color=_score_color(sed_score))

    node("nutrient", "Nutrient Load", "#2E5D8A", 30, "stage",
         f"Dominant: {summary['dominant_nutrient_source']} "
         f"({summary['nutrient_confidence_pct']:.0f}% confidence)")
    edge("nutrient", "bloom", width=3, color="#5a6b7a")
    # Internal loading feeds the nutrient pool back into the chain.
    edge("sediment", "nutrient", width=2 + 3 * sed_score, dashes=True, color=_ORANGE)

    if rt:
        rt_level = rt["risk_level"]
        rt_score = rt["risk_score"]
        rt_days = rt["residence_time_days"]
        days_lbl = "closed" if rt_days is None else f"{rt_days:.0f} d"
        node("residence", f"Residence\n{days_lbl}",
             _LEVEL_COLOR.get(rt_level, _GREY), _size(0, rt_score, 18, 44), "stage",
             f"Residence {days_lbl} — {rt_level} stagnation risk")
        edge("residence", "bloom", width=2 + 4 * rt_score, color=_score_color(rt_score))
        edge("residence", "sediment", width=2, dashes=True, color="#5a6b7a")

    # ── Nutrient sources (sized by attribution %) ──
    for key, pct in nut["sources_pct"].items():
        frac = pct / 100.0
        name = NUTRIENT_SIGNATURES[key].name if key in NUTRIENT_SIGNATURES else key
        is_dom = key == summary["dominant_nutrient_source"]
        node(f"src_{key}", f"{name}\n{pct:.0f}%",
             "#9b59b6" if is_dom else "#b8a3cf", _size(0, frac, 12, 34), "source",
             f"{name}: {pct:.0f}% of estimated load")
        edge(f"src_{key}", "nutrient", width=1 + 4 * frac, color="#7d6699")

    # ── Bloom drivers (sized by favourability) ──
    dlabels = {
        "temperature": "Temperature", "phosphate": "Phosphate", "ammonia": "Ammonia",
        "dissolved_oxygen": "Low DO", "residence_time": "Residence", "salinity": "Salinity",
        "internal_loading": "Internal Loading",
    }
    for key, fav in bloom["drivers"].items():
        # Residence & internal loading already have spine nodes — link those instead.
        if key == "residence_time" and rt:
            continue
        if key == "internal_loading":
            continue
        label = dlabels.get(key, key)
        node(f"drv_{key}", label, _score_color(fav), _size(0, fav, 10, 30), "driver",
             f"{label} bloom favourability {fav:.2f}")
        edge(f"drv_{key}", "bloom", width=1 + 3 * fav, color=_score_color(fav))

    # ── Top interventions (green, dashed, hang off the chain) ──
    target_map = {
        "reduce_phosphate": "nutrient", "remove_sludge": "sediment",
        "increase_circulation": "sediment", "reduce_residence_time": "residence",
    }
    for iv in (result.get("recommended_interventions") or [])[:3]:
        red = iv["expected_bloom_reduction_pct"]
        key = iv["scenario"].split(" (")[0]
        # Map by recommendation effectiveness colour.
        col = _GREEN if red >= 15 else _AMBER if red >= 5 else "#95a5a6"
        iid = f"iv_{abs(hash(iv['scenario'])) % 100000}"
        node(iid, f"⚙ {key}", col, _size(0, min(red / 30, 1), 12, 26), "intervention",
             f"{iv['scenario']}: {red:+.1f} pts in ~{iv['timeline_days']:.0f} days")
        tgt = next((v for k, v in target_map.items() if k in iv["scenario"].lower().replace(" ", "_")), "bloom")
        if tgt == "residence" and not rt:
            tgt = "bloom"
        edge(iid, tgt, width=2, dashes=True, color=col)

    return {"nodes": nodes, "edges": edges}
