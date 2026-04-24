"""Environmental Drivers — reference for operations and client education."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.constants import MONTH_NAMES, NUTRIENT_SOURCES
from data.sample_data import get_solar_irradiance, get_monthly_table, TEMP_SPECIES_DOMINANCE
from ui.components import page_header, section_header, callout


def render():
    page_header(
        "ENVIRONMENTAL DRIVERS",
        "The Four Key Drivers of Algae Dynamics in Dubai Lagoons",
        icon="🌡️",
    )

    # ── 1. Solar Radiation ──
    section_header("1. Solar Radiation")

    solar = get_solar_irradiance()
    fig = go.Figure()
    colors = ["#f39c12" if v >= 6.5 else "#4472C4" for v in solar]
    fig.add_trace(go.Bar(
        x=MONTH_NAMES, y=solar, marker_color=colors,
        text=[f"{v}" for v in solar], textposition="outside",
    ))
    fig.add_hline(y=6.0, line_dash="dot", line_color="#e74c3c",
                  annotation_text="High algae growth risk threshold")
    fig.update_layout(
        height=350, template="plotly_white",
        yaxis_title="Solar Irradiance (kWh/m²/day)",
        margin=dict(t=40, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)
    callout("UAE receives ~6.0 kWh/m²/day average, ~3,500+ sunshine hours/year. "
            "Pre-treat March–April before radiation ramp; maintain May–September.", "info")

    # ── 2. Water Temperature & Species ──
    section_header("2. Water Temperature & Species Dominance")

    raw = get_monthly_table()

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=MONTH_NAMES, y=raw["water_temp"], name="Lagoon Water Temp",
        line=dict(color="#e74c3c", width=3), fill="tozeroy",
        fillcolor="rgba(231,76,60,0.1)",
    ))
    fig2.add_hline(y=30.6, line_dash="dash", line_color="#c0392b",
                   annotation_text="Cyanobacteria optimum (30.6°C)")
    fig2.add_hline(y=25.7, line_dash="dash", line_color="#27ae60",
                   annotation_text="Chlorophyte optimum (25.7°C)")
    fig2.add_hline(y=24.0, line_dash="dash", line_color="#3498db",
                   annotation_text="Diatom optimum (24.0°C)")
    fig2.update_layout(
        height=400, template="plotly_white",
        yaxis_title="Temperature (°C)",
        margin=dict(t=40, b=40),
    )
    st.plotly_chart(fig2, use_container_width=True)

    df_temp = pd.DataFrame(TEMP_SPECIES_DOMINANCE)
    df_temp.columns = ["Month", "Temp (°C)", "Cyanobacteria", "Chlorophytes", "Diatoms", "Dominant Group"]

    def highlight_optimum(val):
        if "AT OPTIMUM" in str(val):
            return "background-color: #FFC7CE; color: #9C0006; font-weight: bold"
        if "Near" in str(val):
            return "background-color: #FFEB9C"
        return ""

    styled = (
        df_temp.style
        .map(highlight_optimum, subset=["Cyanobacteria", "Chlorophytes", "Diatoms"])
        .set_properties(**{"text-align": "center"})
        .hide(axis="index")
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    callout(
        "<strong>Key insight:</strong> Dubai summer water (33°C) sits precisely at cyanobacteria's "
        "thermal optimum (30.6 ± 2.3°C) while suppressing all competitors. "
        "DO saturation at 33°C is only ~7.1 mg/L — leaving just 3 mg/L margin above the DECCA limit.",
        "danger",
    )

    # ── 3. Nutrient Sources ──
    section_header("3. Nutrient Sources (Dubai-Specific — Ranked)")

    df_nut = pd.DataFrame(NUTRIENT_SOURCES)
    df_nut.columns = ["Rank", "Source", "Contribution", "Controllability", "Monitoring", "Mechanism"]

    control_colors = {"HIGH": "#C6EFCE", "MEDIUM": "#FFEB9C", "LOW": "#F4B084", "NONE": "#FFC7CE"}

    def color_control(val):
        bg = control_colors.get(str(val), "")
        return f"background-color: {bg}" if bg else ""

    styled = df_nut.style.map(color_control, subset=["Controllability"]).set_properties(**{"text-align": "left"}).hide(axis="index")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    callout(
        "<strong>Critical finding:</strong> Unlike most marine basins where agricultural runoff dominates, "
        "in Dubai lagoons <strong>municipal wastewater effluent (TSE) is the dominant source</strong> "
        "of anthropogenic N and P. DM phosphate standard (25 mg PO₄/L) is well above eutrophication threshold.",
        "warning",
    )

    # ── 4. Salinity & Mixing ──
    section_header("4. Salinity & Mixing")

    sal_data = [
        {"Water Body": "Open Arabian Gulf", "Salinity (PSU)": "39–41", "Risk": "LOW", "Significance": "Reference baseline"},
        {"Water Body": "Bulk Lagoon Water", "Salinity (PSU)": "45–60+", "Risk": "HIGH", "Significance": "Evaporative concentration"},
        {"Water Body": "TSE Inflow", "Salinity (PSU)": "1–3", "Risk": "CRITICAL", "Significance": "Creates freshwater lens"},
        {"Water Body": "Freshwater Surface Lens", "Salinity (PSU)": "1–15", "Risk": "CRITICAL", "Significance": "Perfect cyanobacteria incubator"},
        {"Water Body": "Mixing Interface", "Salinity (PSU)": "~18", "Risk": "HIGH", "Significance": "Toxin release zone"},
    ]
    df_sal = pd.DataFrame(sal_data)
    risk_colors = {"LOW": "#C6EFCE", "HIGH": "#F4B084", "CRITICAL": "#FFC7CE"}

    def color_risk(val):
        bg = risk_colors.get(str(val), "")
        return f"background-color: {bg}; font-weight: bold" if bg else ""

    styled = df_sal.style.map(color_risk, subset=["Risk"]).set_properties(**{"text-align": "center"}).hide(axis="index")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    callout(
        "<strong>Stratification Trap:</strong> Low-salinity TSE floats on dense saline lagoon water → "
        "freshwater lens at surface = low salinity + concentrated nutrients + maximum solar radiation "
        "+ peak temperature = perfect cyanobacteria incubator. Continuous aeration/destratification is essential.",
        "danger",
    )
