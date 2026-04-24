"""Sludge & Sediment Management — capacity tracking and treatment."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data.sample_data import get_sludge_zones
from ui.components import page_header, section_header, metric_card, callout


def render():
    page_header(
        "SLUDGE & SEDIMENT MANAGEMENT",
        "Capacity Tracking, Composition & Internal Nutrient Loading",
        icon="🪣",
    )

    zones = get_sludge_zones()

    # ── Capacity Tracker ──
    section_header("Lagoon Capacity Tracker")

    rows = []
    for z in zones:
        rows.append({
            "Zone": z.zone_name,
            "Total Depth (ft)": z.total_depth_ft,
            "Sludge Depth (ft)": z.sludge_depth_ft,
            "Effective Depth (ft)": z.effective_depth_ft,
            "Capacity Loss %": f"{z.capacity_loss_pct:.1f}%",
            "Status": z.status,
        })
    df = pd.DataFrame(rows)

    status_colors = {"OK": "#C6EFCE", "WARNING": "#FFEB9C", "CRITICAL": "#FFC7CE"}

    def color_status(val):
        bg = status_colors.get(str(val), "")
        return f"background-color: {bg}; font-weight: bold" if bg else ""

    styled = df.style.map(color_status, subset=["Status"]).set_properties(**{"text-align": "center"}).hide(axis="index")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Visual chart ──
    fig = go.Figure()
    names = [z.zone_name for z in zones]
    fig.add_trace(go.Bar(
        x=names, y=[z.effective_depth_ft for z in zones],
        name="Effective Depth", marker_color="#4472C4",
    ))
    fig.add_trace(go.Bar(
        x=names, y=[z.sludge_depth_ft for z in zones],
        name="Sludge Depth", marker_color="#e74c3c",
    ))
    fig.update_layout(
        barmode="stack", height=350, template="plotly_white",
        yaxis_title="Depth (ft)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(t=50, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── KPI row ──
    avg_loss = sum(z.capacity_loss_pct for z in zones) / len(zones)
    critical = sum(1 for z in zones if z.status == "CRITICAL")
    cols = st.columns(3)
    with cols[0]:
        metric_card("Avg Capacity Loss", f"{avg_loss:.1f}%",
                     "#e74c3c" if avg_loss > 25 else "#f39c12" if avg_loss > 15 else "#27ae60")
    with cols[1]:
        metric_card("Critical Zones", str(critical),
                     "#e74c3c" if critical > 0 else "#27ae60")
    with cols[2]:
        metric_card("Bio-Digestible Fraction", "~66%", "#27ae60",
                     "Treatable with enzyme cocktail")

    # ── Sludge Composition ──
    section_header("Sludge Composition")

    col1, col2 = st.columns([1, 1])
    with col1:
        fig2 = go.Figure(go.Pie(
            labels=["Dead algae + bacteria", "Organic detritus", "Sand / silt", "Minerals"],
            values=[40, 26, 17, 17],
            marker_colors=["#e74c3c", "#f39c12", "#95a5a6", "#7f8c8d"],
            hole=0.4,
            textinfo="label+percent",
        ))
        fig2.update_layout(height=350, margin=dict(t=20, b=20), showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    with col2:
        comp_data = pd.DataFrame([
            {"Component": "Dead algae + bacteria", "Percentage": "~40%", "Digestible": "YES", "Treatment": "Cellulase + protease + lipase"},
            {"Component": "Organic detritus", "Percentage": "~26%", "Digestible": "YES", "Treatment": "Enzyme cocktail + bacteria"},
            {"Component": "Sand / silt", "Percentage": "~17%", "Digestible": "NO", "Treatment": "Physical removal only"},
            {"Component": "Minerals", "Percentage": "~17%", "Digestible": "NO", "Treatment": "Physical removal only"},
        ])
        st.dataframe(comp_data, use_container_width=True, hide_index=True)

    # ── Internal Nutrient Loading ──
    section_header("Internal Nutrient Loading — Risk Assessment")

    risks = [
        {"Condition": "Bottom DO < 2 mg/L", "Mechanism": "Fe³⁺ → Fe²⁺ releases bound PO₄",
         "P Contribution": "30–60% of total P", "Prevention": "Bottom aeration to keep DO > 2"},
        {"Condition": "Water Temp > 30°C", "Mechanism": "Accelerated sediment P release",
         "P Contribution": "Proportional to temp", "Prevention": "Manage via aeration (can't control temp)"},
        {"Condition": "Sludge Depth > 3 ft", "Mechanism": "Large nutrient reservoir in water contact",
         "P Contribution": "Can feed blooms for years", "Prevention": "Enzyme bio-dredging + physical removal"},
        {"Condition": "Sediment DOM release", "Mechanism": "Dissolved organic matter stimulates algae",
         "P Contribution": "Difficult to quantify", "Prevention": "Sludge reduction programme"},
    ]
    df_risk = pd.DataFrame(risks)
    st.dataframe(df_risk, use_container_width=True, hide_index=True)

    callout(
        "<strong>The Internal Loading Trap:</strong> Even with zero external nutrient inputs, "
        "sludge can feed blooms for years. At 33°C, sediment P release accelerates dramatically. "
        "Sludge management is not optional — it's a prerequisite for long-term control.",
        "danger",
    )
