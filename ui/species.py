"""Species Threat Matrix — identification and response guide."""
import streamlit as st
import pandas as pd

from core.constants import SPECIES_PROFILES
from ui.components import page_header, section_header, callout


def render():
    page_header(
        "SPECIES THREAT MATRIX",
        "Algae Identification & Response Guide",
        icon="🦠",
    )

    # ── Species profiles ──
    section_header("Species Profiles")

    rows = []
    for sp in SPECIES_PROFILES:
        rows.append({
            "Category": sp.category,
            "Group": sp.group,
            "Key Species": sp.key_species,
            "Salinity": sp.salinity_range,
            "Temp Optimum": sp.temp_optimum,
            "Toxin": sp.toxin_type,
            "Threat": sp.threat_level,
            "Peak Season": sp.peak_season,
            "Treatment": sp.treatment,
        })
    df = pd.DataFrame(rows)

    cat_colors = {
        "HIGH THREAT": "#FFC7CE",
        "MODERATE": "#FFEB9C",
        "SPECIALIST": "#D6E4F0",
    }
    threat_colors = {"HIGH": "#FFC7CE", "MODERATE": "#FFEB9C", "LOW": "#D6E4F0"}

    def color_cat(val):
        bg = cat_colors.get(str(val), "")
        return f"background-color: {bg}; font-weight: bold" if bg else ""

    def color_threat(val):
        bg = threat_colors.get(str(val), "")
        return f"background-color: {bg}; font-weight: bold" if bg else ""

    styled = (
        df.style
        .map(color_cat, subset=["Category"])
        .map(color_threat, subset=["Threat"])
        .set_properties(**{"text-align": "left"})
        .hide(axis="index")
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Species ID indicators ──
    section_header("Sensor-Based Species Identification")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """<div style="background: #FFC7CE; padding: 1rem; border-radius: 8px; text-align: center;">
            <h4 style="margin: 0;">Phycocyanin : Chl-a > 0.5</h4>
            <p style="margin: 0.3rem 0 0 0; font-size: 1.1rem; font-weight: bold;">🔴 Cyanobacteria Dominant</p>
            <p style="margin: 0.2rem 0 0 0; font-size: 0.85rem;">Activate ultrasound + cyano-specific enzymes</p>
            </div>""",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            """<div style="background: #D6E4F0; padding: 1rem; border-radius: 8px; text-align: center;">
            <h4 style="margin: 0;">Phycocyanin : Chl-a < 0.5</h4>
            <p style="margin: 0.3rem 0 0 0; font-size: 1.1rem; font-weight: bold;">🔵 Other Species Dominant</p>
            <p style="margin: 0.2rem 0 0 0; font-size: 0.85rem;">Standard treatment protocol (aeration priority)</p>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    callout(
        "<strong>Two simultaneous bloom regimes:</strong> Dubai lagoons host marine dinoflagellates "
        "in bulk water AND freshwater cyanobacteria in the TSE surface lens. "
        "Both chlorophyll-a (total biomass) and phycocyanin (cyano-specific) must be monitored.",
        "warning",
    )

    # ── Detailed species cards ──
    section_header("Detailed Species Profiles")

    for sp in SPECIES_PROFILES:
        st.markdown(
            f"""<div style="border-left: 4px solid {sp.color}; padding: 0.8rem 1.2rem;
            margin: 0.5rem 0; background: white; border-radius: 0 8px 8px 0;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);">
            <h4 style="color: {sp.color}; margin: 0;">{sp.group}
            <span style="font-size: 0.8rem; color: #999;"> — {sp.category}</span></h4>
            <p style="color: #666; margin: 0.2rem 0; font-style: italic;">{sp.key_species}</p>
            <table style="font-size: 0.85rem; width: 100%;">
            <tr><td style="width: 110px; font-weight: 600;">Salinity</td><td>{sp.salinity_range}</td>
            <td style="width: 110px; font-weight: 600;">Temp</td><td>{sp.temp_optimum}</td></tr>
            <tr><td style="font-weight: 600;">Toxin</td><td>{sp.toxin_type}</td>
            <td style="font-weight: 600;">Season</td><td>{sp.peak_season}</td></tr>
            <tr><td style="font-weight: 600;">Treatment</td><td colspan="3">{sp.treatment}</td></tr>
            </table></div>""",
            unsafe_allow_html=True,
        )

    # ── Historical events ──
    section_header("Historical Bloom Events — UAE / Gulf Region")

    events = pd.DataFrame([
        {"Year": "2008–09", "Location": "Arabian Gulf coastline", "Species": "Cochlodinium", "Impact": "1,200 km affected", "Lesson": "Gulf-wide monitoring needed"},
        {"Year": "2017", "Location": "Off Dubai coast", "Species": "Noctiluca", "Impact": "Visible bloom", "Lesson": "Winter blooms also possible"},
        {"Year": "2018", "Location": "Al Qudra Lakes", "Species": "Cyanobacteria", "Impact": "Recreational system", "Lesson": "MPC-Buoy reduced cyano 73% in 60 days"},
        {"Year": "2021", "Location": "Kuwait Bay", "Species": "Chattonella", "Impact": "435,000 cells/L", "Lesson": "Dust storms trigger blooms within days"},
    ])
    st.dataframe(events, use_container_width=True, hide_index=True)
