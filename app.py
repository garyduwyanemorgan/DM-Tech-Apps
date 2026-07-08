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

# ── Authenticated Session Management (SaaS Phase 3) ──
try:
    from db.client import get_client, is_configured
    from db.queries import get_site_names

    # Initialize session states
    if "user_token" not in st.session_state:
        st.session_state["user_token"] = None
    if "user_email" not in st.session_state:
        st.session_state["user_email"] = None
    if "user_org_id" not in st.session_state:
        st.session_state["user_org_id"] = None
    if "user_role" not in st.session_state:
        st.session_state["user_role"] = "operator"
    if "use_sample_data" not in st.session_state:
        st.session_state["use_sample_data"] = False

    if is_configured():
        client = get_client()

        # 1. User is not authenticated and hasn't chosen sample data
        if not st.session_state["user_token"] and not st.session_state["use_sample_data"]:
            st.sidebar.markdown("### 🔐 Tenant Login")
            email = st.sidebar.text_input("Email", key="login_email")
            password = st.sidebar.text_input("Password", type="password", key="login_password")

            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("Log In", use_container_width=True):
                    try:
                        res = client.auth.sign_in_with_password({"email": email, "password": password})
                        if res.session:
                            st.session_state["user_token"] = res.session.access_token
                            st.session_state["user_email"] = res.user.email
                            st.session_state["user_id"] = res.user.id
                            st.session_state["use_sample_data"] = False

                            # Load user profile for organization_id and role
                            scoped_client = get_client(res.session.access_token)
                            prof = scoped_client.table("user_profiles").select("*").eq("id", res.user.id).execute()
                            if prof.data:
                                st.session_state["user_org_id"] = prof.data[0].get("organization_id")
                                st.session_state["user_role"] = prof.data[0].get("role", "operator")

                            st.success("Success!")
                            st.rerun()
                    except Exception as e:
                        st.sidebar.error(f"Login failed: {str(e)}")
            with col2:
                if st.button("Sample Data", use_container_width=True):
                    st.session_state["use_sample_data"] = True
                    st.rerun()
            st.sidebar.markdown("---")

            # Pause dashboard rendering
            st.info("Please log in or click 'Sample Data' to access the dashboard.")
            st.stop()

        # 2. User is logged in
        elif st.session_state["user_token"]:
            st.sidebar.markdown(f"👤 **{st.session_state['user_email']}**")
            st.sidebar.caption(f"Role: {st.session_state['user_role'].upper()}")

            if st.sidebar.button("Sign Out", use_container_width=True):
                try:
                    client.auth.sign_out()
                except Exception:
                    pass
                st.session_state["user_token"] = None
                st.session_state["user_email"] = None
                st.session_state["user_org_id"] = None
                st.session_state["user_role"] = "operator"
                st.session_state["use_sample_data"] = False
                st.session_state["active_site"] = None
                st.rerun()

            st.sidebar.markdown("---")

            # Dynamic site selectbox scoped to the tenant
            sites = get_site_names(organization_id=st.session_state["user_org_id"], token=st.session_state["user_token"])
            if sites:
                st.sidebar.markdown("**ACTIVE SITE**")
                active = st.sidebar.selectbox(
                    "Site",
                    sites,
                    key="active_site_selector",
                    label_visibility="collapsed",
                )
                st.session_state["active_site"] = active
                st.sidebar.caption(f"Tenant site: {active}")
                st.sidebar.markdown("---")
            else:
                st.sidebar.warning("No sites registered for this tenant.")
                st.session_state["active_site"] = None
                st.sidebar.markdown("---")

        # 3. Sample data mode bypass
        elif st.session_state["use_sample_data"]:
            st.sidebar.markdown("📊 **Sample Data Mode**")
            if st.sidebar.button("Return to Login", use_container_width=True):
                st.session_state["use_sample_data"] = False
                st.rerun()
            st.sidebar.markdown("---")
            st.session_state["active_site"] = None
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
        ("Compliance Reporting", "compliance"),
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
elif module_name == "compliance":
    from ui.compliance import render
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

# ── Role-based Access Control (UI Level Gate) ──
write_pages = ["upload_report"]
current_role = st.session_state.get("user_role", "operator")

if module_name in write_pages and current_role == "auditor":
    st.error("🔐 Access Denied: Your account role (Auditor) does not have permission to upload/modify data.")
else:
    render()
