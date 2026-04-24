"""Reusable Streamlit UI components — metric cards, styled tables, headers."""
import streamlit as st
import pandas as pd
from typing import List, Dict, Optional

from core.constants import ALERT_COLORS, ALERT_LABELS, AlertLevel
from core.models import ComplianceResult


# ── Page header ──

def page_header(title: str, subtitle: str = "", icon: str = ""):
    st.markdown(
        f"""<div style="background: linear-gradient(135deg, #1B3A5C 0%, #2E5D8A 100%);
        padding: 1.5rem 2rem; border-radius: 10px; margin-bottom: 1.5rem;">
        <h1 style="color: white; margin: 0; font-size: 1.8rem;">{icon} {title}</h1>
        {"<p style='color: #D6E4F0; margin: 0.3rem 0 0 0; font-size: 0.95rem;'>" + subtitle + "</p>" if subtitle else ""}
        </div>""",
        unsafe_allow_html=True,
    )


# ── KPI / Metric cards ──

def metric_card(label: str, value: str, color: str = "#1B3A5C", subtitle: str = ""):
    st.markdown(
        f"""<div style="background: white; border-left: 4px solid {color};
        padding: 1rem 1.2rem; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        min-height: 100px;">
        <p style="color: #666; font-size: 0.8rem; margin: 0; text-transform: uppercase;
        letter-spacing: 0.5px;">{label}</p>
        <p style="color: {color}; font-size: 1.6rem; font-weight: 700; margin: 0.3rem 0 0 0;">{value}</p>
        {"<p style='color: #999; font-size: 0.75rem; margin: 0.2rem 0 0 0;'>" + subtitle + "</p>" if subtitle else ""}
        </div>""",
        unsafe_allow_html=True,
    )


def alert_level_badge(level: AlertLevel):
    color = ALERT_COLORS[level]
    label = ALERT_LABELS[level]
    st.markdown(
        f"""<div style="background: {color}; color: white; padding: 0.8rem 1.2rem;
        border-radius: 8px; text-align: center; font-weight: 700; font-size: 1.3rem;
        box-shadow: 0 2px 8px {color}66;">
        {label}
        </div>""",
        unsafe_allow_html=True,
    )


# ── Compliance table ──

def compliance_table(results: List[ComplianceResult]):
    rows = []
    for r in results:
        status = "✅ PASS" if r.compliant else "❌ FAIL"
        rows.append({
            "Parameter": r.parameter_name,
            "Unit": r.unit,
            "DECCA Limit": r.limit_display,
            "Current": r.value,
            "Status": status,
            "Margin %": f"{r.margin_pct:.1f}%",
            "Risk": r.risk_level,
        })
    df = pd.DataFrame(rows)

    def color_status(val):
        if "PASS" in str(val):
            return "background-color: #C6EFCE; color: #006100; font-weight: bold"
        if "FAIL" in str(val):
            return "background-color: #FFC7CE; color: #9C0006; font-weight: bold"
        return ""

    def color_risk(val):
        colors = {"LOW": "#C6EFCE", "MODERATE": "#FFEB9C", "HIGH": "#FFC7CE"}
        bg = colors.get(val, "")
        return f"background-color: {bg}" if bg else ""

    styled = (
        df.style
        .map(color_status, subset=["Status"])
        .map(color_risk, subset=["Risk"])
        .set_properties(**{"text-align": "center"})
        .set_properties(subset=["Parameter"], **{"text-align": "left", "font-weight": "bold"})
        .hide(axis="index")
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ── Generic styled dataframe ──

def styled_table(df: pd.DataFrame, highlight_col: Optional[str] = None,
                 color_map: Optional[Dict[str, str]] = None):
    """Render a dataframe with optional conditional coloring on one column."""
    styler = df.style.set_properties(**{"text-align": "center"}).hide(axis="index")
    if highlight_col and color_map:
        def apply_color(val):
            bg = color_map.get(str(val), "")
            return f"background-color: {bg}" if bg else ""
        styler = styler.map(apply_color, subset=[highlight_col])
    st.dataframe(styler, use_container_width=True, hide_index=True)


# ── Section header ──

def section_header(title: str):
    st.markdown(
        f"""<h3 style="color: #1B3A5C; border-bottom: 2px solid #D6E4F0;
        padding-bottom: 0.4rem; margin-top: 1.5rem;">{title}</h3>""",
        unsafe_allow_html=True,
    )


# ── Info callout box ──

def callout(text: str, type: str = "info"):
    colors = {
        "info":    ("#D6E4F0", "#1B3A5C"),
        "warning": ("#FFEB9C", "#856404"),
        "danger":  ("#FFC7CE", "#721c24"),
        "success": ("#C6EFCE", "#155724"),
    }
    bg, fg = colors.get(type, colors["info"])
    st.markdown(
        f"""<div style="background: {bg}; color: {fg}; padding: 0.8rem 1.2rem;
        border-radius: 6px; margin: 0.5rem 0; font-size: 0.9rem;">{text}</div>""",
        unsafe_allow_html=True,
    )


# ── Phase color badge ──

def phase_badge(phase_name: str, color: str):
    st.markdown(
        f"""<span style="background: {color}; color: white; padding: 0.25rem 0.75rem;
        border-radius: 12px; font-size: 0.8rem; font-weight: 600;">{phase_name}</span>""",
        unsafe_allow_html=True,
    )
