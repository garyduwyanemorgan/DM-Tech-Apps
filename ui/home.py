"""Home — the landing page. Overview + quick links into the workflow."""
import streamlit as st

from ui.components import page_header, section_header, metric_card, callout


def _go(page: str):
    """Navigate to a page from a button: set active page, clear nav radios."""
    st.session_state["active_page"] = page
    for k in list(st.session_state.keys()):
        if k.startswith("nav_"):
            st.session_state[k] = None
    st.rerun()


def render():
    page_header(
        "DUBAI LAGOON MANAGEMENT PLATFORM",
        "Predictive water-quality monitoring & compliance — GDM Enviro Consultants",
        icon="🌊",
    )

    # ── Portfolio snapshot ──
    n_sites, live = 0, False
    try:
        from db.client import is_configured
        from db.queries import get_site_names
        if is_configured():
            n_sites = len(get_site_names())
            live = bool(st.session_state.get("active_site"))
    except Exception:
        pass

    k = st.columns(3)
    with k[0]:
        metric_card("Lagoons Configured", str(n_sites) if n_sites else "—", "#2E5D8A",
                     "Sites in your portfolio")
    with k[1]:
        metric_card("Data Source", "Live" if live else "Sample", "#27ae60" if live else "#f39c12",
                     "Select a site in the sidebar for live data")
    with k[2]:
        metric_card("Compliance Standard", "Dubai Municipality (DM)", "#1B3A5C", "Dubai Municipality limits")

    # ── Quick actions ──
    section_header("Start here")
    c = st.columns(4)
    with c[0]:
        st.markdown("**📷 Record a reading**")
        st.caption("Snap a lab report — values auto-fill.")
        if st.button("Upload Lab Report", width='stretch'):
            _go("upload_report")
    with c[1]:
        st.markdown("**📡 Optimise sampling**")
        st.caption("See which lagoons to sample and the savings.")
        if st.button("Predictive Monitoring", width='stretch'):
            _go("predictive")
    with c[2]:
        st.markdown("**🧠 Diagnose a lagoon**")
        st.caption("Why is it at risk, and what to do.")
        if st.button("Lagoon Intelligence", width='stretch'):
            _go("intelligence")
    with c[3]:
        st.markdown("**📄 Produce a report**")
        st.caption("Submission-ready compliance PDF.")
        if st.button("Compliance Reporting", width='stretch'):
            _go("compliance")

    # ── How it flows ──
    section_header("How the platform works")
    st.markdown(
        "1. **Record** field readings (upload a lab report, or via the field app).\n"
        "2. **Monitor** current compliance and alert status across your lagoons.\n"
        "3. **Analyse** — the intelligence engine forecasts blooms and recommends "
        "the cheapest effective intervention.\n"
        "4. **Report** — generate the official compliance document.\n"
        "5. **Reference** — treatment calendar, species, sludge and technology guidance."
    )

    callout("Use the sidebar to navigate. Pick your site under <strong>ACTIVE SITE</strong> "
            "to switch from sample data to your live readings.", "info")
