"""Upload Lab Report — photo/PDF in, structured reading out (with human review).

Field flow: upload a lab-report photo or PDF → AI reads the 14 parameters →
operator reviews/corrects the prefilled form → save. The human-confirm step is
mandatory: this is regulatory data, so a recognition error must be caught
before it lands in the database.
"""
import streamlit as st

from core.constants import MONTH_NAMES
from db.client import is_configured as db_configured
from db.queries import get_site_names, insert_reading
from ui.components import page_header, section_header, callout

# (extract key, label, unit, DECCA hint, readings-table column)
_FIELDS = [
    ("ph",              "pH",                "",          "6.0–9.0",      "ph"),
    ("do",              "Dissolved Oxygen",  "mg/L",      "> 4.0",        "do_mgl"),
    ("tss",             "TSS",               "mg/L",      "< 50",         "tss_mgl"),
    ("turbidity",       "Turbidity",         "NTU",       "< 75",         "turbidity_ntu"),
    ("cod",             "COD",               "mg/L",      "< 50",         "cod_mgl"),
    ("ammonia",         "Ammonia",           "mg/L",      "< 5.0",        "ammonia_mgl"),
    ("phosphate",       "Phosphate",         "mg/L",      "< 5.0",        "phosphate_mgl"),
    ("oil_grease",      "Oils & Grease",     "mg/L",      "< 10",         "oil_grease_mgl"),
    ("ecoli",           "E. coli",           "CFU/100mL", "< 200",        "ecoli_cfu"),
    ("total_coliforms", "Total Coliforms",   "CFU/100mL", "< 1000",       "total_coliforms_cfu"),
    ("chla",            "Chlorophyll-a",     "µg/L",      "bloom > 10",   "chla_ugl"),
    ("phycocyanin",     "Phycocyanin",       "µg/L",      "cyano > 50",   "phycocyanin_ugl"),
    ("salinity",        "Salinity",          "PSU",       "40–60",        "salinity_psu"),
    ("water_temp",      "Water Temp",        "°C",        "22–33",        "water_temp_c"),
]


def render():
    page_header("UPLOAD LAB REPORT",
                "Photo or PDF → readings auto-filled → review → save",
                icon="📷")

    if not db_configured():
        callout("Connect site data first — readings can't be saved without the database.", "warning")
        return

    sites = get_site_names() or ["Lagoon"]

    # ── Step 1: upload ──
    section_header("Step 1 — Upload the lab report")
    up = st.file_uploader("Lab report (photo or PDF)",
                          type=["png", "jpg", "jpeg", "webp", "pdf"])
    if up is not None:
        if up.type.startswith("image/"):
            st.image(up, caption=up.name, width=360)
        else:
            st.caption(f"📄 {up.name}")

        from extract import is_configured as ai_ready
        if ai_ready():
            if st.button("✨ Extract values from report", type="primary"):
                with st.spinner("Reading the report…"):
                    try:
                        from extract import extract_lab_report
                        st.session_state["lab_extracted"] = extract_lab_report(
                            up.getvalue(), up.type)
                        st.success("Extracted — review the values below before saving.")
                    except Exception as exc:
                        st.error(f"{exc}")
                        st.session_state.pop("lab_extracted", None)
        else:
            callout("AI extraction is off (no ANTHROPIC_API_KEY set). You can still enter the "
                    "values manually below.", "info")

    extracted = st.session_state.get("lab_extracted", {})
    if extracted.get("notes"):
        callout(f"<strong>Reader notes:</strong> {extracted['notes']}", "warning")

    # ── Step 2: review + period ──
    section_header("Step 2 — Review and confirm")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        site = st.selectbox("Site", sites)
    with c2:
        from datetime import date
        month_name = st.selectbox("Month", MONTH_NAMES, index=date.today().month - 1)
        month = MONTH_NAMES.index(month_name) + 1
    with c3:
        year = st.number_input("Year", min_value=2020, max_value=2035,
                               value=date.today().year, step=1)
    with c4:
        overwrite = st.checkbox("Overwrite if exists", value=False)

    with st.form("lab_review"):
        st.caption("Values are pre-filled from the report — correct anything the reader got wrong.")
        cols = st.columns(3)
        values = {}
        for i, (key, label, unit, hint, _col) in enumerate(_FIELDS):
            with cols[i % 3]:
                pre = extracted.get(key)
                values[key] = st.number_input(
                    f"{label}" + (f" ({unit})" if unit else ""),
                    value=float(pre) if isinstance(pre, (int, float)) else 0.0,
                    step=0.1, format="%.2f", help=f"DECCA: {hint}")
        submitted = st.form_submit_button("Save Reading", type="primary", width='stretch')

    if submitted:
        fields = {col: values[key] for key, _l, _u, _h, col in _FIELDS}
        ok, msg = insert_reading(site, int(year), int(month), fields, upsert=overwrite)
        if ok:
            st.success(f"Saved — {site}, {month_name} {year}. {msg}")
            st.session_state.pop("lab_extracted", None)
        else:
            st.error(msg)
