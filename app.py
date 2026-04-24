"""
Dubai Lagoon Management Dashboard
Entry point — Streamlit multi-page app.

Architecture:
  core/   — Pure computation, zero UI dependencies
  data/   — Sample data generators
  ui/     — Streamlit page renderers

Run:  streamlit run dashboard/app.py
"""
import streamlit as st

st.set_page_config(
    page_title="Dubai Lagoon Management Plan",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ──
st.markdown("""
<style>
    .stApp { background-color: #f5f7fa; }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1B3A5C 0%, #2E5D8A 100%);
    }
    [data-testid="stSidebar"] * { color: white !important; }
    [data-testid="stSidebar"] .stSelectbox label { color: #D6E4F0 !important; }
    div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
    h1, h2, h3 { font-family: Arial, sans-serif; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar navigation ──
st.sidebar.markdown(
    """<div style="text-align: center; padding: 1rem 0;">
    <h2 style="margin: 0;">🌊 Dubai Lagoons</h2>
    <p style="font-size: 0.85rem; opacity: 0.8; margin: 0.3rem 0 0 0;">Management Dashboard</p>
    </div>""",
    unsafe_allow_html=True,
)

st.sidebar.markdown("---")
st.sidebar.markdown("**CLIENT / DECCA**")

PAGES = {
    # Client / DECCA section
    "Executive Dashboard":     "executive",
    "DECCA Reporting":         "decca",
    # Operations section
    "Water Quality Monitoring": "monitoring",
    "Alert & Response Protocol":"alerts",
    "Seasonal Treatment Calendar":"calendar_view",
    "Sludge & Sediment Mgmt":  "sludge",
    # Reference section
    "Environmental Drivers":   "drivers",
    "Species Threat Matrix":   "species",
    "Intervention Technologies":"technologies",
    "ML Prediction System":    "ml_system",
}

page_names = list(PAGES.keys())
ops_start = 2   # index where Operations section starts
ref_start = 6   # index where Reference section starts

# Build selection with section headers
selected = st.sidebar.radio(
    "Navigate",
    page_names,
    format_func=lambda x: x,
    label_visibility="collapsed",
)

# Show section labels
idx = page_names.index(selected)
if idx == ops_start:
    pass  # handled below

st.sidebar.markdown("---")
st.sidebar.markdown(
    """<div style="font-size: 0.75rem; opacity: 0.6; text-align: center; padding-top: 1rem;">
    GDM Enviro Consultants<br>
    Dubai Holdings — Dubai Lands<br>
    © 2026
    </div>""",
    unsafe_allow_html=True,
)

# ── Render selected page ──
module_name = PAGES[selected]

if module_name == "executive":
    from ui.executive import render
elif module_name == "decca":
    from ui.decca import render
elif module_name == "monitoring":
    from ui.monitoring import render
elif module_name == "alerts":
    from ui.alerts import render
elif module_name == "calendar_view":
    from ui.calendar_view import render
elif module_name == "sludge":
    from ui.sludge import render
elif module_name == "drivers":
    from ui.drivers import render
elif module_name == "species":
    from ui.species import render
elif module_name == "technologies":
    from ui.technologies import render
elif module_name == "ml_system":
    from ui.ml_system import render

render()
