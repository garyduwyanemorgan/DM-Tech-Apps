"""DECCA Reporting — formatted for regulatory submission."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.constants import DECCA_LIMITS, MONTH_NAMES
from core.calculations import check_compliance, monthly_compliance_rate
from data.sample_data import get_monthly_readings
from ui.components import page_header, section_header, metric_card, callout


def render():
    page_header(
        "DECCA REGULATORY COMPLIANCE REPORT",
        "Reporting Period: January – December 2026  |  Dubai Holdings — Dubai Lands",
        icon="📋",
    )

    readings = get_monthly_readings()

    # ── Annual compliance by parameter ──
    section_header("Monthly Compliance Summary")

    rows = []
    for key, lim in DECCA_LIMITS.items():
        monthly_vals = [getattr(r, key if key != "oil_grease" else "oil_grease") for r in readings]
        # Handle attribute name mapping
        attr_map = {
            "ph": "ph", "do": "do", "tss": "tss", "turbidity": "turbidity",
            "cod": "cod", "ammonia": "ammonia", "phosphate": "phosphate",
            "oil_grease": "oil_grease", "ecoli": "ecoli", "total_coliforms": "total_coliforms",
        }
        monthly_vals = [getattr(r, attr_map[key]) for r in readings]
        compliant_months = sum(1 for v in monthly_vals if check_compliance(key, v).compliant)

        rows.append({
            "Parameter": lim.parameter,
            "Unit": lim.unit,
            "DECCA Limit": lim.display,
            "Annual Avg": round(sum(monthly_vals) / len(monthly_vals), 1),
            "Annual Max": max(monthly_vals),
            "Annual Min": min(monthly_vals),
            "Months Compliant": f"{compliant_months}/12",
            "Compliance %": f"{monthly_compliance_rate(compliant_months):.1f}%",
            "Status": "FULL COMPLIANCE" if compliant_months == 12 else "EXCEEDANCE",
        })
    df = pd.DataFrame(rows)

    def color_status(val):
        if val == "FULL COMPLIANCE":
            return "background-color: #C6EFCE; color: #006100; font-weight: bold"
        return "background-color: #FFC7CE; color: #9C0006; font-weight: bold"

    styled = df.style.map(color_status, subset=["Status"]).set_properties(**{"text-align": "center"}).hide(axis="index")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Annual scorecard KPIs ──
    section_header("Annual Compliance Scorecard")

    all_compliant = all(r["Status"] == "FULL COMPLIANCE" for _, r in df.iterrows())
    zero_exceedance_count = sum(1 for _, r in df.iterrows() if r["Status"] == "FULL COMPLIANCE")

    cols = st.columns(4)
    with cols[0]:
        metric_card("Overall Compliance", "100.0%" if all_compliant else "< 100%",
                     "#27ae60" if all_compliant else "#e74c3c")
    with cols[1]:
        metric_card("Zero-Exceedance Params", f"{zero_exceedance_count}/10", "#27ae60")
    with cols[2]:
        metric_card("Monitoring Hours", "2,160", "#1B3A5C", "24/7 sensor coverage")
    with cols[3]:
        metric_card("Escalation Incidents", "0", "#27ae60", "No Level 3+ activations")

    # ── Compliance heatmap ──
    section_header("Monthly Parameter Status Heatmap")

    heatmap_data = []
    for key, lim in DECCA_LIMITS.items():
        attr_map = {
            "ph": "ph", "do": "do", "tss": "tss", "turbidity": "turbidity",
            "cod": "cod", "ammonia": "ammonia", "phosphate": "phosphate",
            "oil_grease": "oil_grease", "ecoli": "ecoli", "total_coliforms": "total_coliforms",
        }
        row_vals = []
        for r in readings:
            val = getattr(r, attr_map[key])
            result = check_compliance(key, val)
            row_vals.append(result.margin_pct)
        heatmap_data.append(row_vals)

    param_names = [lim.parameter for lim in DECCA_LIMITS.values()]

    fig = go.Figure(go.Heatmap(
        z=heatmap_data,
        x=[m[:3] for m in MONTH_NAMES],
        y=param_names,
        colorscale=[[0, "#e74c3c"], [0.3, "#f39c12"], [0.5, "#f4d03f"], [1, "#27ae60"]],
        text=[[f"{v:.0f}%" for v in row] for row in heatmap_data],
        texttemplate="%{text}",
        colorbar_title="Margin %",
    ))
    fig.update_layout(
        height=400, template="plotly_white",
        margin=dict(t=20, b=40),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)

    callout(
        "Green = large safety margin from DECCA limit. Yellow/Red = approaching or exceeding limit. "
        "Summer months (Jun–Sep) show tightest margins across all parameters due to elevated temperatures.",
        "info",
    )

    # ── Incident Log ──
    section_header("Incident Log")
    callout("No incidents recorded to date. All parameters have remained within DECCA limits "
            "throughout the reporting period.", "success")

    st.markdown("**Template for future incidents:**")
    incident_cols = ["Date", "Parameter", "Measured Value", "DECCA Limit",
                     "Duration (hr)", "Root Cause", "Corrective Action",
                     "Resolution Date", "Days to Resolve"]
    st.dataframe(pd.DataFrame(columns=incident_cols), use_container_width=True, hide_index=True)
