"""Intervention Technologies — reference and dosing guide."""
import streamlit as st
import pandas as pd

from core.constants import ENZYME_TOOLKIT, BACTERIAL_CONSORTIUM
from ui.components import page_header, section_header, callout


def render():
    page_header(
        "INTERVENTION TECHNOLOGIES",
        "Three-Pillar System: Ultrasound + Enzymes + Aeration",
        icon="⚙️",
    )

    # ── Three-pillar comparison ──
    section_header("Three-Pillar Technology Comparison")

    techs = [
        {"Technology": "Ultrasonic (MPC-Buoy)", "Response": "Hours", "Mechanism": "Gas vesicle collapse → buoyancy loss → algae sink",
         "Best Against": "Cyanobacteria", "Limitation": "Doesn't remove nutrients; algae can adapt",
         "Role": "Surface bloom prevention (fast response)"},
        {"Technology": "Enzyme Bioremediation", "Response": "Days–Weeks", "Mechanism": "Cell lysis by enzymes + nutrient competition by bacteria",
         "Best Against": "All species + sludge", "Limitation": "Requires DO > 2 mg/L; needs halotolerant strains",
         "Role": "Root cause treatment"},
        {"Technology": "Aeration & Mixing", "Response": "Continuous", "Mechanism": "Destratification + oxygenation + sediment P lock",
         "Best Against": "All (enables other treatments)", "Limitation": "Undersized systems feed blooms",
         "Role": "Foundation (everything depends on this)"},
    ]
    df = pd.DataFrame(techs)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Visual integration diagram ──
    st.markdown(
        """<div style="background: linear-gradient(135deg, #f8f9fa, #e9ecef); padding: 1.5rem;
        border-radius: 10px; text-align: center; margin: 1rem 0;">
        <h4 style="color: #1B3A5C;">Integration Logic</h4>
        <div style="display: flex; justify-content: center; align-items: center; gap: 1rem; flex-wrap: wrap;">
        <div style="background: #3498db; color: white; padding: 0.8rem 1.2rem; border-radius: 8px; min-width: 200px;">
        <strong>AERATION</strong><br>Foundation<br><em>Enables everything else</em></div>
        <span style="font-size: 1.5rem;">→</span>
        <div style="background: #27ae60; color: white; padding: 0.8rem 1.2rem; border-radius: 8px; min-width: 200px;">
        <strong>ENZYMES</strong><br>Root Cause<br><em>Nutrient removal + sludge</em></div>
        <span style="font-size: 1.5rem;">→</span>
        <div style="background: #9b59b6; color: white; padding: 0.8rem 1.2rem; border-radius: 8px; min-width: 200px;">
        <strong>ULTRASOUND</strong><br>Fast Response<br><em>Surface bloom prevention</em></div>
        </div></div>""",
        unsafe_allow_html=True,
    )

    # ── Aeration mechanisms ──
    section_header("Aeration — Five Anti-Algae Mechanisms")

    mechanisms = [
        {"#": 1, "Mechanism": "Destratification", "How": "Breaks thermal + salinity layers", "Dubai Relevance": "MOST IMPORTANT — breaks TSE incubator"},
        {"#": 2, "Mechanism": "Light Disruption", "How": "Algae circulated below photic zone", "Dubai Relevance": "High PAR makes this very effective"},
        {"#": 3, "Mechanism": "Sediment P Lock", "How": "Oxygenated bottom water binds Fe³⁺-PO₄", "Dubai Relevance": "Can reduce internal P 50–80%"},
        {"#": 4, "Mechanism": "Bacterial Boost", "How": "DO > 4 mg/L enables aerobic bacteria", "Dubai Relevance": "Without this, enzymes = waste of money"},
        {"#": 5, "Mechanism": "CO₂ Off-gassing", "How": "Removes excess CO₂; shifts pH", "Dubai Relevance": "Secondary benefit"},
    ]
    st.dataframe(pd.DataFrame(mechanisms), use_container_width=True, hide_index=True)

    callout(
        "<strong>Under-aeration danger:</strong> Undersized aeration systems bring nutrient-laden "
        "bottom water to the surface without fully mixing → feeds the bloom instead of suppressing it. "
        "Must size for complete water column mixing.",
        "warning",
    )

    # ── Enzyme toolkit ──
    section_header("Enzyme Toolkit")
    df_enz = pd.DataFrame(ENZYME_TOOLKIT)
    df_enz.columns = ["Enzyme", "Target Substrate", "Optimal pH", "Optimal Temp", "Dubai Working Range", "Species Specificity"]
    st.dataframe(df_enz, use_container_width=True, hide_index=True)

    # ── Bacterial consortium ──
    section_header("Bacterial Consortium — Halotolerant Strains")
    df_bac = pd.DataFrame(BACTERIAL_CONSORTIUM)
    df_bac.columns = ["Genus", "Key Species", "Salt Tolerance", "Primary Role", "Dubai Suitability", "Spore-Forming"]

    def color_suit(val):
        if "ESSENTIAL" in str(val):
            return "background-color: #FFC7CE; font-weight: bold"
        if "HIGH" in str(val):
            return "background-color: #C6EFCE; font-weight: bold"
        return "background-color: #FFEB9C"

    styled = df_bac.style.map(color_suit, subset=["Dubai Suitability"]).set_properties(**{"text-align": "left"}).hide(axis="index")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    callout(
        "<strong>Critical:</strong> Standard freshwater bio-enzyme products FAIL at Dubai salinities (45–60 PSU) "
        "and temperatures (30–38°C). Must use Gulf-adapted halotolerant strains. "
        "Halomonas is essential for bulk lagoon water above 50 PSU.",
        "danger",
    )

    # ── Al Qudra case study ──
    section_header("Case Study: Al Qudra Lakes (Dubai, 2018)")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            """<div style="background: #C6EFCE; padding: 1rem; border-radius: 8px; text-align: center;">
            <p style="color: #666; font-size: 0.8rem; margin: 0;">Total Algae Reduction</p>
            <p style="font-size: 2rem; font-weight: 700; color: #155724; margin: 0;">-50%</p>
            <p style="font-size: 0.8rem; color: #666; margin: 0;">100 → 50 µg/L Chl-a</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """<div style="background: #C6EFCE; padding: 1rem; border-radius: 8px; text-align: center;">
            <p style="color: #666; font-size: 0.8rem; margin: 0;">Cyanobacteria Reduction</p>
            <p style="font-size: 2rem; font-weight: 700; color: #155724; margin: 0;">-73%</p>
            <p style="font-size: 0.8rem; color: #666; margin: 0;">675 → 180 µg/L phycocyanin</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            """<div style="background: #D6E4F0; padding: 1rem; border-radius: 8px; text-align: center;">
            <p style="color: #666; font-size: 0.8rem; margin: 0;">Treatment Period</p>
            <p style="font-size: 2rem; font-weight: 700; color: #1B3A5C; margin: 0;">60 days</p>
            <p style="font-size: 0.8rem; color: #666; margin: 0;">3 MPC-Buoy units deployed</p>
            </div>""",
            unsafe_allow_html=True,
        )
