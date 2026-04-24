"""Seasonal Treatment Calendar — annual treatment planning."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.constants import SEASONAL_PHASES, MONTH_NAMES
from data.sample_data import TREATMENT_CALENDAR
from ui.components import page_header, section_header, callout


def render():
    page_header(
        "SEASONAL TREATMENT CALENDAR",
        "Annual Plan — Four-Phase Treatment Cycle",
        icon="📅",
    )

    # ── Phase timeline visual ──
    section_header("Annual Phase Overview")

    fig = go.Figure()
    for phase in SEASONAL_PHASES:
        start_m = phase.months[0]
        end_m = phase.months[-1]
        fig.add_trace(go.Bar(
            x=[end_m - start_m + 1],
            y=[0],
            base=[start_m - 0.5],
            orientation="h",
            name=phase.name,
            marker_color=phase.color,
            text=f"{phase.name}<br>{phase.objective}",
            textposition="inside",
            textfont=dict(color="white", size=12),
            hoverinfo="text",
        ))

    fig.update_layout(
        height=120,
        showlegend=False,
        xaxis=dict(
            tickmode="array",
            tickvals=list(range(1, 13)),
            ticktext=[m[:3] for m in MONTH_NAMES],
            range=[0.5, 12.5],
        ),
        yaxis=dict(visible=False),
        margin=dict(t=10, b=30, l=10, r=10),
        template="plotly_white",
        barmode="overlay",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Monthly detail table ──
    section_header("Monthly Treatment Details")

    df = pd.DataFrame(TREATMENT_CALENDAR)
    df.columns = ["Month", "Phase", "Enzyme Dosing", "Aeration Level", "Ultrasound Mode", "Risk Level"]

    phase_colors = {p.name: p.color for p in SEASONAL_PHASES}

    def color_phase(val):
        for pname, color in phase_colors.items():
            if pname in str(val):
                return f"background-color: {color}; color: white; font-weight: bold"
        return ""

    risk_colors = {
        "Low": "#C6EFCE", "Rising": "#FFEB9C", "Moderate": "#FFEB9C",
        "High": "#F4B084", "HIGH": "#F4B084", "VERY HIGH": "#FFC7CE",
        "CRITICAL": "#FF0000",
    }

    def color_risk(val):
        bg = risk_colors.get(str(val), "")
        if str(val) == "CRITICAL":
            return f"background-color: {bg}; color: white; font-weight: bold"
        return f"background-color: {bg}" if bg else ""

    styled = (
        df.style
        .map(color_phase, subset=["Phase"])
        .map(color_risk, subset=["Risk Level"])
        .set_properties(**{"text-align": "left"})
        .hide(axis="index")
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=460)

    # ── Phase summary cards ──
    section_header("Phase Summary")

    for phase in SEASONAL_PHASES:
        month_range = f"{MONTH_NAMES[phase.months[0]-1][:3]}–{MONTH_NAMES[phase.months[-1]-1][:3]}"
        st.markdown(
            f"""<div style="border-left: 5px solid {phase.color}; padding: 0.8rem 1.2rem;
            margin: 0.5rem 0; background: white; border-radius: 0 8px 8px 0;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);">
            <h4 style="color: {phase.color}; margin: 0;">{phase.name}
            <span style="font-size: 0.85rem; color: #666; font-weight: normal;">({month_range})</span></h4>
            <p style="margin: 0.3rem 0 0 0; color: #444;">{phase.objective}</p>
            </div>""",
            unsafe_allow_html=True,
        )

    callout(
        "<strong>CRITICAL RULE (Phase 3):</strong> NEVER deploy algicide during peak season. "
        "A bloom crash releases massive BOD → DO crash → worse than managed decline.",
        "danger",
    )
