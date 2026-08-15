"""Water Quality Monitoring — detailed data for operations team."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.constants import COMPLIANCE_LIMITS, MONTH_NAMES
from core.specs import NON_COMPLIANT, judge, lagoon_spec_set
from data.provider import get_monthly_readings, get_monthly_table
from ui.components import page_header, section_header


def render():
    page_header(
        "WATER QUALITY MONITORING",
        "Monthly Data Log — Operations Team View",
        icon="🔬",
    )

    readings = get_monthly_readings()
    raw = get_monthly_table()

    # ── Monthly data table ──
    section_header("Monthly Water Quality Data (2026)")

    df = pd.DataFrame({
        "Month": MONTH_NAMES,
        "pH": raw["ph"],
        "DO (mg/L)": raw["do"],
        "TSS (mg/L)": raw["tss"],
        "Turbidity (NTU)": raw["turbidity"],
        "COD (mg/L)": raw["cod"],
        "Ammonia (mg/L)": raw["ammonia"],
        "Phosphate (mg/L)": raw["phosphate"],
        "Chl-a (µg/L)": raw["chla"],
        "Phycocyanin (µg/L)": raw["phycocyanin"],
        "Salinity (PSU)": raw["salinity"],
        "Temp (°C)": raw["water_temp"],
    })

    # Column header -> parameter key. This view showed six of the ten parameters
    # and still does; a parameter that is not judged agrees with everything, so
    # widening the table is a product decision, not a side effect of this change.
    _COLUMN_PARAM = {
        "DO (mg/L)": "do",
        "TSS (mg/L)": "tss",
        "Turbidity (NTU)": "turbidity",
        "COD (mg/L)": "cod",
        "Ammonia (mg/L)": "ammonia",
        "Phosphate (mg/L)": "phosphate",
    }
    _spec = lagoon_spec_set()

    def highlight_risk(val, col):
        """Red on a breach, amber when approaching one.

        The breach test used to be a private copy of the limits — the third of
        the eight verdict implementations DM_COMPLIANCE_SCOPING.md §5 catalogues.
        Its values and operators matched the canonical ones, so routing it through
        core/specs.py changes no cell's colour; it removes the copy that would
        eventually have drifted.

        The AMBER band is deliberately left as it was: 0.8x an upper limit, 1.2x
        a lower one. It is a fourth risk-band scheme (§5), and unifying the bands
        is a separate decision that changes what users see. This change is about
        where the BREACH comes from, and nothing else.
        """
        key = _COLUMN_PARAM.get(col)
        if key is None:
            return ""
        try:
            v = float(val)
        except (ValueError, TypeError):
            return ""

        if judge(v, _spec, parameter_key=key) == NON_COMPLIANT:
            return "background-color: #FFC7CE; color: #9C0006"

        lim = _spec.limits[key]
        if lim.max_val is not None and v >= lim.max_val * 0.8:
            return "background-color: #FFEB9C; color: #856404"
        if lim.min_val is not None and v <= lim.min_val * 1.2:
            return "background-color: #FFEB9C; color: #856404"
        return ""

    styled = df.style.hide(axis="index")
    for col in ["DO (mg/L)", "TSS (mg/L)", "Turbidity (NTU)", "COD (mg/L)", "Ammonia (mg/L)", "Phosphate (mg/L)"]:
        styled = styled.map(lambda v, c=col: highlight_risk(v, c), subset=[col])
    st.dataframe(styled, width='stretch', hide_index=True)

    # ── Multi-axis chart ──
    section_header("Water Quality Trends")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(x=MONTH_NAMES, y=raw["do"], name="DO (mg/L)",
                   line=dict(color="#4472C4", width=3)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=MONTH_NAMES, y=raw["chla"], name="Chl-a (µg/L)",
                   line=dict(color="#00B050", width=3)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=MONTH_NAMES, y=raw["water_temp"], name="Temp (°C)",
                   line=dict(color="#FF0000", width=3, dash="dash")),
        secondary_y=True,
    )

    # Compliance DO limit line
    fig.add_hline(y=4.0, line_dash="dot", line_color="#e74c3c",
                  annotation_text="Compliance DO Limit (4.0 mg/L)", secondary_y=False)

    fig.update_layout(
        height=450,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(t=60, b=40),
    )
    fig.update_yaxes(title_text="DO (mg/L) / Chl-a (µg/L)", secondary_y=False)
    fig.update_yaxes(title_text="Temperature (°C)", secondary_y=True)

    st.plotly_chart(fig, width='stretch')

    # ── Salinity & Phycocyanin chart ──
    section_header("Salinity & Cyanobacteria Indicators")

    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
    fig2.add_trace(
        go.Bar(x=MONTH_NAMES, y=raw["salinity"], name="Salinity (PSU)",
               marker_color="#3498db", opacity=0.6),
        secondary_y=False,
    )
    fig2.add_trace(
        go.Scatter(x=MONTH_NAMES, y=raw["phycocyanin"], name="Phycocyanin (µg/L)",
                   line=dict(color="#9b59b6", width=3), fill="tozeroy",
                   fillcolor="rgba(155,89,182,0.1)"),
        secondary_y=True,
    )
    fig2.update_layout(
        height=400, template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(t=60, b=40),
    )
    fig2.update_yaxes(title_text="Salinity (PSU)", secondary_y=False)
    fig2.update_yaxes(title_text="Phycocyanin (µg/L)", secondary_y=True)
    st.plotly_chart(fig2, width='stretch')

    # ── Annual statistics ──
    section_header("Annual Statistics")
    stats = {
        "Statistic": ["Average", "Maximum", "Minimum"],
    }
    for col_name, key in [("pH", "ph"), ("DO", "do"), ("TSS", "tss"), ("Chl-a", "chla"),
                           ("Temp", "water_temp"), ("Salinity", "salinity")]:
        vals = raw[key]
        stats[col_name] = [
            round(sum(vals) / len(vals), 1),
            max(vals),
            min(vals),
        ]
    st.dataframe(pd.DataFrame(stats), width='stretch', hide_index=True)
