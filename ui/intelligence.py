"""Lagoon Intelligence — the v2 scientific decision-support page.

Surfaces the science engines (science/) for Compliance and operators: runs the full
diagnostic chain on the selected reading and renders bloom forecast, nutrient
source attribution, Fe-P internal loading, hydraulic residence time, and a
ranked list of digital-twin interventions — each with the reasoning shown
(Architecture.md: "Explainable", "No hidden AI decisions").
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.constants import MONTH_NAMES
from data.provider import get_monthly_readings, is_live
from science.diagnose import diagnose
from science.graph import build_lagoon_graph
from science.config import NUTRIENT_SIGNATURES
from ui.components import page_header, section_header, metric_card, callout
from ui.graph_component import render_lagoon_graph


# Colour scale shared with the rest of the dashboard.
_SEVERITY_COLOR = {
    "MINIMAL": "#27ae60", "MODERATE": "#f39c12",
    "SIGNIFICANT": "#e67e22", "SEVERE": "#e74c3c",
}
_LEVEL_COLOR = {
    "LOW": "#27ae60", "MODERATE": "#f39c12", "HIGH": "#e67e22", "SEVERE": "#e74c3c",
    "UNKNOWN": "#95a5a6",
}


def render():
    page_header(
        "LAGOON INTELLIGENCE",
        "Scientific decision support — why is the lagoon at risk, and what to do",
        icon="🧠",
    )

    site = st.session_state.get("active_site")
    live = is_live()
    if site and live:
        callout(f"Live diagnosis for <strong>{site}</strong> using submitted readings.", "success")
    else:
        callout("Using <strong>sample data</strong> — select a site with submitted readings "
                "in the sidebar for a live diagnosis.", "warning")

    readings = get_monthly_readings()

    # ── Inputs: which reading + the hydraulics the chemistry can't supply ──
    section_header("Diagnostic Inputs")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        month_name = st.selectbox("Reading month", MONTH_NAMES, index=7)  # default Aug (peak)
        month_idx = MONTH_NAMES.index(month_name)
    with c2:
        volume = st.number_input("Lagoon volume (m³)", min_value=0, value=250000, step=10000,
                                 help="Enables residence-time and intervention modelling.")
    with c3:
        inflow = st.number_input("Inflow (m³/day)", min_value=0, value=1800, step=100)
    with c4:
        outflow = st.number_input("Outflow (m³/day)", min_value=0, value=1800, step=100)

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        sediment_state = st.selectbox("Sediment state", ["mineral", "normal", "organic", "post_bloom"], index=1)
    with c6:
        orp_known = st.checkbox("ORP probe available", value=False)
    with c7:
        orp = st.number_input("ORP (mV)", value=150, step=10, disabled=not orp_known) if True else 0
    with c8:
        hist = st.number_input("Prior blooms at site", min_value=0, value=1, step=1)

    cx1, cx2, cx3 = st.columns(3)
    with cx1:
        tse_high = st.checkbox("High TSE inflow", value=True)
    with cx2:
        rainfall = st.checkbox("Recent rainfall", value=False)
    with cx3:
        dust = st.checkbox("Recent dust event", value=False)

    r = readings[month_idx]

    # ── Run the full chain ──
    result = diagnose(
        temperature=r.water_temp, phosphate=r.phosphate, ammonia=r.ammonia,
        dissolved_oxygen=r.do, salinity=r.salinity,
        volume_m3=volume, inflow_m3_day=inflow, outflow_m3_day=outflow,
        orp=(orp if orp_known else None), sediment_state=sediment_state,
        recent_rainfall=rainfall, dust_event=dust, tse_inflow_high=tse_high,
        salinity_baseline=45.0, historical_bloom_count=int(hist),
        include_interventions=True,
    )
    s = result["summary"]

    # ── Headline KPIs ──
    section_header(f"Diagnosis — {month_name} ({'live' if (site and live) else 'sample'})")
    k = st.columns(4)
    with k[0]:
        metric_card("Bloom Probability", f"{s['bloom_probability_pct']:.0f}%",
                     _SEVERITY_COLOR.get(s["bloom_severity"], "#1B3A5C"), s["bloom_severity"])
    with k[1]:
        src = s["dominant_nutrient_source"]
        src_name = NUTRIENT_SIGNATURES[src].name if src in NUTRIENT_SIGNATURES else src
        metric_card("Dominant Nutrient Source", src_name, "#2E5D8A",
                     f"{s['nutrient_confidence_pct']:.0f}% confidence")
    with k[2]:
        metric_card("Internal Loading (Fe-P)", s["internal_loading_level"],
                     _LEVEL_COLOR.get(s["internal_loading_level"], "#1B3A5C"))
    with k[3]:
        metric_card("Residence Risk", s["residence_risk"],
                     _LEVEL_COLOR.get(s["residence_risk"], "#1B3A5C"),
                     f"Recovery ≈ {s['recovery_time_days']:.0f} days")

    # ── Causal graph (Obsidian-style force-directed network) ──
    section_header("Causal Graph — Live Lagoon Network")
    st.caption("Node size = magnitude · colour = risk · drag nodes to explore · hover for the reasoning. "
               "Follows the scientific chain: sources → hydraulics → sediment → bloom → operational risk.")
    graph = build_lagoon_graph(result)
    render_lagoon_graph(graph, height=560)

    # ── Bloom drivers + nutrient pie ──
    left, right = st.columns([1, 1])

    with left:
        section_header("Bloom Drivers")
        bf = result["bloom_forecast"]
        drivers = bf["drivers"]
        dlabels = {
            "temperature": "Temperature", "phosphate": "Phosphate", "ammonia": "Ammonia",
            "dissolved_oxygen": "Low DO", "residence_time": "Residence", "salinity": "Salinity",
            "internal_loading": "Internal Loading",
        }
        names = [dlabels.get(k, k) for k in drivers]
        vals = [drivers[k] for k in drivers]
        fig = go.Figure(go.Bar(
            x=vals, y=names, orientation="h",
            marker_color=["#e74c3c" if v >= 0.66 else "#f39c12" if v >= 0.33 else "#27ae60" for v in vals],
            text=[f"{v:.2f}" for v in vals], textposition="auto",
        ))
        fig.update_layout(height=320, template="plotly_white",
                          xaxis_title="Favourability (0–1)", xaxis_range=[0, 1],
                          margin=dict(t=10, b=40, l=10, r=10))
        st.plotly_chart(fig, width='stretch')

    with right:
        section_header("Nutrient Source Attribution")
        na = result["nutrient_attribution"]
        pct = na["sources_pct"]
        labels = [NUTRIENT_SIGNATURES[k].name if k in NUTRIENT_SIGNATURES else k for k in pct]
        fig2 = go.Figure(go.Pie(
            labels=labels, values=list(pct.values()), hole=0.45,
            textinfo="label+percent", textposition="outside",
            marker_colors=["#e74c3c", "#9b59b6", "#f39c12", "#3498db", "#95a5a6"],
        ))
        fig2.update_layout(height=320, showlegend=False, margin=dict(t=20, b=20, l=10, r=10))
        st.plotly_chart(fig2, width='stretch')
        st.caption(f"Confidence {na['confidence_pct']:.0f}% — indicative apportionment. "
                   "Confirm with inflow sampling for legal-grade attribution.")

    # ── Recommended interventions (digital twin) ──
    section_header("Recommended Interventions — Digital Twin")
    interventions = result.get("recommended_interventions", [])
    if interventions:
        rows = []
        for iv in interventions:
            rows.append({
                "Intervention": iv["scenario"],
                "Bloom Now": f"{iv['baseline_bloom_pct']:.0f}%",
                "After": f"{iv['projected_bloom_pct']:.0f}%",
                "Reduction": f"{iv['expected_bloom_reduction_pct']:+.1f} pts",
                "Time to Effect": f"{iv['timeline_days']:.0f} days",
                "Verdict": iv["recommendation"].split(" — ")[0],
            })
        df = pd.DataFrame(rows)

        def color_verdict(val):
            v = str(val)
            if "RECOMMENDED" in v:       return "background-color: #C6EFCE; color: #006100; font-weight: bold"
            if "WORTH" in v:             return "background-color: #FFEB9C; color: #856404; font-weight: bold"
            if "MARGINAL" in v:          return "background-color: #FDEBD0; color: #7E5109"
            return "background-color: #FFC7CE; color: #9C0006"

        styled = df.style.map(color_verdict, subset=["Verdict"]).hide(axis="index")
        st.dataframe(styled, width='stretch', hide_index=True)

        best = interventions[0]
        if best["expected_bloom_reduction_pct"] >= 15:
            callout(f"<strong>Top action:</strong> {best['scenario']} — projected "
                    f"{best['expected_bloom_reduction_pct']:.0f} pt bloom reduction in "
                    f"~{best['timeline_days']:.0f} days.", "success")
        else:
            callout("<strong>No single intervention is decisive here</strong> — this lagoon "
                    "needs a combined programme. Stack the top measures; the twin models each "
                    "in isolation.", "warning")

    # ── Full reasoning (explainability) ──
    section_header("Scientific Reasoning")
    with st.expander("Bloom forecast — how this was computed"):
        for line in result["bloom_forecast"]["reasoning"]:
            st.markdown(f"- {line}")
    with st.expander("Internal sediment loading (Fe-P)"):
        for line in result["internal_loading"]["reasoning"]:
            st.markdown(f"- {line}")
    with st.expander("Nutrient source attribution"):
        for line in result["nutrient_attribution"]["reasoning"]:
            st.markdown(f"- {line}")
    if result.get("residence_time"):
        with st.expander("Hydraulic residence time"):
            for line in result["residence_time"]["reasoning"]:
                st.markdown(f"- {line}")

    callout(
        "Diagnostic model is directionally validated against regional conditions; "
        "parameters are refined with site-specific data as it accumulates.", "info")
