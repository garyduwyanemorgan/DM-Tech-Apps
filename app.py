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

# ── Site selector (shown when Supabase is configured) ──
try:
    from db.client import is_configured
    from db.queries import get_site_names
    if is_configured():
        sites = get_site_names()
        if sites:
            st.sidebar.markdown("**ACTIVE SITE**")
            active = st.sidebar.selectbox(
                "Site",
                ["— Sample data —"] + sites,
                key="active_site_selector",
                label_visibility="collapsed",
            )
            st.session_state["active_site"] = None if active == "— Sample data —" else active
            if st.session_state.get("active_site"):
                st.sidebar.caption(f"Live data: {st.session_state['active_site']}")
            else:
                st.sidebar.caption("Showing sample data")
            st.sidebar.markdown("---")
except Exception:
    pass

# ── Workflow-grouped navigation: enter data → monitor → analyse → report → reference ──
NAV = {
    "DATA ENTRY": [
        ("Upload Lab Report", "upload_report"),
    ],
    "MONITORING": [
        ("Executive Dashboard", "executive"),
        ("Water Quality Monitoring", "monitoring"),
        ("Alert & Response Protocol", "alerts"),
    ],
    "INTELLIGENCE": [
        ("Lagoon Intelligence", "intelligence"),
        ("Predictive Monitoring", "predictive"),
    ],
    "REPORTING": [
        ("DECCA Reporting", "decca"),
    ],
    "REFERENCE": [
        ("Seasonal Treatment Calendar", "calendar_view"),
        ("Sludge & Sediment Mgmt", "sludge"),
        ("Environmental Drivers", "drivers"),
        ("Species Threat Matrix", "species"),
        ("Intervention Technologies", "technologies"),
        ("ML Prediction System", "ml_system"),
    ],
}

if "active_page" not in st.session_state:
    st.session_state["active_page"] = "home"

# ── Home button (always returns to the landing page) ──
if st.sidebar.button("🏠  Home", width='stretch'):
    st.session_state["active_page"] = "home"
    for _s in NAV:
        st.session_state[f"nav_{_s}"] = None


def _nav_change(section):
    """Single-selection across grouped radios: set the active page, clear the rest."""
    picked = st.session_state.get(f"nav_{section}")
    if not picked:
        return
    for label, key in NAV[section]:
        if label == picked:
            st.session_state["active_page"] = key
            break
    for other in NAV:
        if other != section:
            st.session_state[f"nav_{other}"] = None


_active = st.session_state["active_page"]
for _section, _items in NAV.items():
    _labels = [lbl for lbl, _k in _items]
    _active_label = next((lbl for lbl, k in _items if k == _active), None)
    # Seed each radio once: the active label in its section, None elsewhere.
    if f"nav_{_section}" not in st.session_state:
        st.session_state[f"nav_{_section}"] = _active_label
    st.sidebar.markdown(
        f"<p style='color:#9FB6CC; font-size:0.7rem; font-weight:700; "
        f"letter-spacing:1.5px; margin:0.7rem 0 0.1rem 0;'>{_section}</p>",
        unsafe_allow_html=True,
    )
    st.sidebar.radio(_section, _labels, key=f"nav_{_section}",
                     label_visibility="collapsed",
                     on_change=_nav_change, args=(_section,))

st.sidebar.markdown("---")
st.sidebar.markdown(
    """<div style="font-size: 0.75rem; opacity: 0.6; text-align: center; padding-top: 1rem;">
    GDM Enviro Consultants<br>
    Compliance Reporting — Dubai Lands<br>
    © 2026
    </div>""",
    unsafe_allow_html=True,
)

# ── Render selected page ──
module_name = st.session_state["active_page"]

if module_name == "home":
    from ui.home import render
elif module_name == "executive":
    from ui.executive import render
elif module_name == "decca":
    from ui.decca import render
elif module_name == "intelligence":
    from ui.intelligence import render
elif module_name == "predictive":
    from ui.predictive import render
elif module_name == "upload_report":
    from ui.upload_report import render
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
