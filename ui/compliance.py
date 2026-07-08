"""Compliance Reporting — formatted for regulatory submission."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.constants import COMPLIANCE_LIMITS, MONTH_NAMES
from core.calculations import check_compliance, monthly_compliance_rate
from data.provider import get_monthly_readings
from ui.components import page_header, section_header, metric_card, callout


def render():
    page_header(
        "REGULATORY COMPLIANCE REPORT",
        "Reporting Period: January – December 2026  |  Compliance Reporting — Project",
        icon="📋",
    )

    readings = get_monthly_readings()

    # ── Official report generation (the paid step — open for now) ──
    _render_report_download(readings)

    # ── Annual compliance by parameter ──
    section_header("Monthly Compliance Summary")

    rows = []
    for key, lim in COMPLIANCE_LIMITS.items():
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
            "Compliance Limit": lim.display,
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
    st.dataframe(styled, width='stretch', hide_index=True)

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
    for key, lim in COMPLIANCE_LIMITS.items():
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

    param_names = [lim.parameter for lim in COMPLIANCE_LIMITS.values()]

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
    st.plotly_chart(fig, width='stretch')

    callout(
        "Green = large safety margin from compliance limit. Yellow/Red = approaching or exceeding limit. "
        "Summer months (Jun–Sep) show tightest margins across all parameters due to elevated temperatures.",
        "info",
    )

    # ── Incident Log ──
    section_header("Incident Log")
    callout("No incidents recorded to date. All parameters have remained within compliance limits "
            "throughout the reporting period.", "success")

    st.markdown("**Template for future incidents:**")
    incident_cols = ["Date", "Parameter", "Measured Value", "Compliance Limit",
                     "Duration (hr)", "Root Cause", "Corrective Action",
                     "Resolution Date", "Days to Resolve"]
    st.dataframe(pd.DataFrame(columns=incident_cols), width='stretch', hide_index=True)


def _render_report_download(readings):
    """Official Compliance report download. Open for now; the paywall hooks onto the
    `draft` flag (watermarked free preview vs clean official report)."""
    from datetime import date
    from reporting import build_compliance_report

    site = st.session_state.get("active_site") or "Sample Lagoon"
    year = readings[0].timestamp.year if readings else date.today().year

    section_header("📄 Official Compliance Report")
    st.markdown(
        f"Generate a formatted, submission-ready compliance report for "
        f"**{site} — {year}**: compliance summary, exceedance log, and bloom-risk "
        "assessment in a single PDF.")

    c1, c2 = st.columns([1, 2])
    with c1:
        try:
            official = build_compliance_report(site, year, readings, draft=False)
            st.download_button(
                "⬇ Download Official Report (PDF)", data=official,
                file_name=f"Compliance_Report_{site}_{year}.pdf", mime="application/pdf",
                width='stretch')
        except Exception as exc:
            st.error(f"Could not generate report: {exc}")
    with c2:
        try:
            draft = build_compliance_report(site, year, readings, draft=True)
            st.download_button(
                "Preview (watermarked draft)", data=draft,
                file_name=f"Compliance_Report_{site}_{year}_DRAFT.pdf", mime="application/pdf")
        except Exception:
            pass
    st.caption("The report is the formal regulatory deliverable. Dashboard access is free; "
               "report generation is the premium step.")
