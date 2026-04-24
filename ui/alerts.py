"""Alert & Response Protocol — operations team action guide."""
import streamlit as st
import pandas as pd

from core.constants import (
    AlertLevel, ALERT_LABELS, ALERT_COLORS, ALERT_THRESHOLDS, TREATMENT_ACTIONS,
)
from core.alert_engine import DE_ESCALATION_RULES, ESCALATION_OVERRIDES, SPECIAL_EVENTS
from ui.components import page_header, section_header, callout


def render():
    page_header(
        "ALERT & RESPONSE PROTOCOL",
        "Operations Guide — Decision Matrix & Treatment Actions",
        icon="🚨",
    )

    # ── Decision Matrix ──
    section_header("Alert Level Decision Matrix")

    rows = []
    for level in AlertLevel:
        t = ALERT_THRESHOLDS[level]
        rows.append({
            "Alert Level": ALERT_LABELS[level],
            "Bloom Prob.": f"{t.bloom_prob_range[0]}–{t.bloom_prob_range[1]}%",
            "Chl-a": t.chla_trigger,
            "DO": t.do_trigger,
            "Phycocyanin": t.phycocyanin_trigger,
            "Temp": t.temp_trigger,
        })
    df = pd.DataFrame(rows)

    def color_level(val):
        for lev, lbl in ALERT_LABELS.items():
            if lbl in str(val):
                return f"background-color: {ALERT_COLORS[lev]}; color: white; font-weight: bold"
        return ""

    styled = df.style.map(color_level, subset=["Alert Level"]).set_properties(**{"text-align": "center"}).hide(axis="index")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Treatment Actions ──
    section_header("Treatment Actions by Alert Level")

    for level in AlertLevel:
        t = TREATMENT_ACTIONS[level]
        color = ALERT_COLORS[level]
        label = ALERT_LABELS[level]

        st.markdown(
            f"""<div style="border-left: 4px solid {color}; padding: 0.8rem 1.2rem;
            margin: 0.5rem 0; background: white; border-radius: 0 8px 8px 0;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);">
            <h4 style="color: {color}; margin: 0 0 0.5rem 0;">{label}</h4>
            <table style="width: 100%; font-size: 0.85rem;">
            <tr><td style="width: 120px; font-weight: 600; color: #666;">Enzymes</td><td>{t.enzyme}</td></tr>
            <tr><td style="font-weight: 600; color: #666;">Aeration</td><td>{t.aeration}</td></tr>
            <tr><td style="font-weight: 600; color: #666;">Ultrasound</td><td>{t.ultrasound}</td></tr>
            <tr><td style="font-weight: 600; color: #666;">Monitoring</td><td>{t.monitoring}</td></tr>
            {"<tr><td style='font-weight: 600; color: #e74c3c;'>⚠️ WARNING</td><td style='color: #e74c3c; font-weight: bold;'>" + t.do_not + "</td></tr>" if t.do_not != "—" else ""}
            </table></div>""",
            unsafe_allow_html=True,
        )

    # ── Special Event Overrides ──
    section_header("Special Event Overrides")
    for evt in SPECIAL_EVENTS:
        st.markdown(
            f"""<div style="background: #FFF3CD; border-left: 4px solid #f39c12;
            padding: 0.6rem 1rem; margin: 0.4rem 0; border-radius: 0 6px 6px 0;">
            <strong>{evt['event']}</strong><br>
            <span style="color: #666;">Response:</span> {evt['response']} —
            <span style="color: #666;">Action:</span> {evt['action']}
            </div>""",
            unsafe_allow_html=True,
        )

    # ── Escalation Rules ──
    col1, col2 = st.columns(2)

    with col1:
        section_header("Escalation Rules (Fast)")
        for rule in ESCALATION_OVERRIDES:
            callout(
                f"<strong>{rule['trigger']}</strong> → Level {rule['min_level']} minimum ({rule['response']})",
                "danger",
            )

    with col2:
        section_header("De-escalation Rules (Slow)")
        for (from_lev, to_lev), rule in DE_ESCALATION_RULES.items():
            callout(
                f"<strong>Level {from_lev} → {to_lev}:</strong> {rule['condition']}",
                "success",
            )

    callout(
        "<strong>Design Principle:</strong> De-escalation is always slower than escalation "
        "→ prevents costly oscillating treatment cycles.",
        "info",
    )
