"""Executive Dashboard — high-level overview for DECCA / Client."""
import streamlit as st

from core.alert_engine import evaluate_alert_level
from core.calculations import check_all_compliance, compliance_summary, bloom_probability
from core.constants import AlertLevel, ALERT_COLORS, ALERT_LABELS, ALERT_THRESHOLDS
from data.sample_data import get_current_reading
from ui.components import page_header, metric_card, alert_level_badge, compliance_table, section_header, callout

import pandas as pd


def render():
    page_header(
        "DUBAI LAGOON MANAGEMENT PLAN",
        "Compliance Dashboard — DECCA / Dubai Municipality / Client View",
        icon="🏛️",
    )

    reading = get_current_reading(month_index=2)  # March
    alert = evaluate_alert_level(reading)
    results = check_all_compliance(reading)
    summary = compliance_summary(results)

    # ── KPI Row ──
    cols = st.columns(5)
    with cols[0]:
        alert_level_badge(AlertLevel(alert.level))
    with cols[1]:
        color = "#27ae60" if summary["overall_status"] == "COMPLIANT" else "#e74c3c"
        metric_card("DECCA Compliance", summary["overall_status"], color)
    with cols[2]:
        metric_card("Days Since Incident", "47", "#1B3A5C", "Last: None recorded")
    with cols[3]:
        metric_card("Active Interventions", "3", "#2E5D8A",
                     "Aeration • Enzymes • Ultrasound")
    with cols[4]:
        metric_card("Next Maintenance", "15 Apr 2026", "#1B3A5C",
                     "Phase 2 Ramp begins")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── DECCA Compliance Table ──
    section_header("DECCA/DM Water Quality Compliance Status")
    compliance_table(results)

    # ── Compliance summary bar ──
    pct = summary["compliance_pct"]
    bar_color = "#27ae60" if pct == 100 else "#f39c12" if pct >= 80 else "#e74c3c"
    st.markdown(
        f"""<div style="background: #f0f0f0; border-radius: 8px; overflow: hidden; height: 30px; margin: 1rem 0;">
        <div style="background: {bar_color}; width: {pct}%; height: 100%; display: flex;
        align-items: center; justify-content: center; color: white; font-weight: 700; font-size: 0.85rem;">
        {pct}% Compliant ({summary['passing']}/{summary['total']} parameters)
        </div></div>""",
        unsafe_allow_html=True,
    )

    # ── Alert Level Reference ──
    section_header("Alert Level Reference")

    alert_rows = []
    for level in AlertLevel:
        t = ALERT_THRESHOLDS[level]
        alert_rows.append({
            "Level": ALERT_LABELS[level],
            "Bloom Prob.": f"{t.bloom_prob_range[0]}–{t.bloom_prob_range[1]}%",
            "Chl-a": t.chla_trigger,
            "DO": t.do_trigger,
            "Phycocyanin": t.phycocyanin_trigger,
            "Temp": t.temp_trigger,
            "Monitoring": t.monitoring_freq,
            "Reporting": t.client_reporting,
        })
    df = pd.DataFrame(alert_rows)

    def color_level(val):
        for lev, lbl in ALERT_LABELS.items():
            if lbl in str(val):
                return f"background-color: {ALERT_COLORS[lev]}; color: white; font-weight: bold"
        return ""

    styled = df.style.map(color_level, subset=["Level"]).set_properties(**{"text-align": "center"}).hide(axis="index")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Current conditions ──
    section_header("Current Conditions Summary")
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Bloom Probability", f"{alert.bloom_probability}%",
                     ALERT_COLORS[AlertLevel(alert.level)])
    with c2:
        metric_card("Dominant Species", alert.dominant_species, "#2E5D8A")
    with c3:
        metric_card("Water Temperature", f"{reading.water_temp}°C", "#1B3A5C",
                     f"Chl-a: {reading.chla} µg/L")

    if alert.top_drivers:
        callout("Current drivers: " + " • ".join(alert.top_drivers), "info")
    else:
        callout("All parameters within normal operating range.", "success")
