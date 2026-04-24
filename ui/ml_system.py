"""ML Prediction System — architecture & performance reference."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.constants import ML_MODELS, ENSEMBLE_WEIGHTS
from ui.components import page_header, section_header, callout


def render():
    page_header(
        "ML PREDICTION SYSTEM",
        "Architecture, Model Comparison & Performance Tracking",
        icon="🤖",
    )

    # ── Model comparison ──
    section_header("Model Comparison")

    df = pd.DataFrame(ML_MODELS)
    df.columns = ["Model", "Forecast Range", "Training Data", "R² Score", "Key Advantage", "Tier", "Production Role"]

    def color_tier(val):
        colors = {1: "#C6EFCE", 2: "#FFEB9C", 3: "#D6E4F0"}
        bg = colors.get(val, "")
        return f"background-color: {bg}; font-weight: bold" if bg else ""

    styled = df.style.map(color_tier, subset=["Tier"]).set_properties(**{"text-align": "center"}).hide(axis="index")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Ensemble weights visual ──
    section_header("Ensemble Weights by Forecast Horizon")

    fig = go.Figure()
    horizons = [w["horizon"] for w in ENSEMBLE_WEIGHTS]
    rf_weights = [w["rf"] for w in ENSEMBLE_WEIGHTS]
    lstm_weights = [w["lstm"] for w in ENSEMBLE_WEIGHTS]

    fig.add_trace(go.Bar(x=horizons, y=rf_weights, name="Random Forest",
                         marker_color="#4472C4", text=[f"{w}%" for w in rf_weights], textposition="inside"))
    fig.add_trace(go.Bar(x=horizons, y=lstm_weights, name="LSTM",
                         marker_color="#e74c3c", text=[f"{w}%" for w in lstm_weights], textposition="inside"))
    fig.update_layout(
        barmode="stack", height=300, template="plotly_white",
        yaxis_title="Weight %",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(t=50, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(
        """<div style="display: flex; gap: 1rem; flex-wrap: wrap;">
        <div style="flex: 1; background: #D6E4F0; padding: 0.8rem; border-radius: 8px; min-width: 200px;">
        <strong>Option A (Start Here):</strong> Horizon-weighted average — calibrate via grid search on validation RMSE</div>
        <div style="flex: 1; background: #FFEB9C; padding: 0.8rem; border-radius: 8px; min-width: 200px;">
        <strong>Option B (Production):</strong> Stacking meta-learner — logistic regression on out-of-fold predictions</div>
        <div style="flex: 1; background: #C6EFCE; padding: 0.8rem; border-radius: 8px; min-width: 200px;">
        <strong>Option C (Mature):</strong> Conditional routing — RF-only when stable, LSTM-dominant during blooms</div>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── Input variables ──
    section_header("Input Variables")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Sensor Inputs (10-min intervals)**")
        sensor_vars = [
            "Chlorophyll-a (total biomass) — CRITICAL",
            "Phycocyanin (cyano-specific) — CRITICAL",
            "Dissolved Oxygen — CRITICAL",
            "Water Temperature — HIGH",
            "Salinity (surface + bulk) — HIGH",
            "pH — MODERATE",
            "Turbidity — MODERATE",
        ]
        for v in sensor_vars:
            priority = "🔴" if "CRITICAL" in v else "🟡" if "HIGH" in v else "🔵"
            st.markdown(f"  {priority} {v}")

    with col2:
        st.markdown("**External APIs & Derived Features**")
        ext_vars = [
            "Weather forecast (wind, solar, air temp) — HIGH",
            "Dust storm index (Met Office) — HIGH",
            "TSE inflow volume + quality (N, P) — CRITICAL",
            "Rolling 24h stats (mean, max, min, std)",
            "Lag features (24h, 48h, 72h ago)",
            "Rate-of-change (Chl-a delta 6h/12h/24h)",
            "Cross-features (temp × nutrient proxy)",
        ]
        for v in ext_vars:
            priority = "🔴" if "CRITICAL" in v else "🟡" if "HIGH" in v else "⚪"
            st.markdown(f"  {priority} {v}")

    # ── Architecture diagram ──
    section_header("Ensemble Architecture")

    st.markdown(
        """<div style="background: #f8f9fa; padding: 1.5rem; border-radius: 10px; font-family: monospace; font-size: 0.85rem;">
        <pre style="margin: 0;">
Sensor Data (10-min) → Cleaned Time-Series (TimescaleDB/Redis)
    ├── RF Path: Tabular snapshot + rolling stats + lag features (~40-60 features)
    │   └── RF/XGBoost → Chl-a prediction + SHAP values
    │
    └── LSTM Path: 7-day hourly sequence (168 timesteps × 7-10 features)
        └── LSTM → Chl-a at +24h, +72h, +168h

Both paths → Ensemble Combiner → Bloom Probability (calibrated sigmoid)
    └── Alert Engine → Treatment Dispatch → Client Dashboard
        </pre></div>""",
        unsafe_allow_html=True,
    )

    # ── Implementation roadmap ──
    section_header("Implementation Roadmap")

    phases = [
        {"Phase": "Phase 1 (Months 1–3)", "Focus": "Launch", "Action": "Deploy sensors, build RF model, Option A ensemble (RF only)", "Deliverable": "1–3 day alerts"},
        {"Phase": "Phase 2 (Months 3–6)", "Focus": "LSTM Integration", "Action": "Train first LSTM on 3+ months data, Option A with calibrated weights", "Deliverable": "Integrated prediction-to-treatment"},
        {"Phase": "Phase 3 (Months 6–12)", "Focus": "Production Ensemble", "Action": "Stacking meta-learner (Option B), calibrate bloom probabilities", "Deliverable": "SHAP dashboard + full season"},
        {"Phase": "Phase 4 (Year 2+)", "Focus": "Mature Platform", "Action": "Conditional routing (Option C), satellite integration, per-lagoon tuning", "Deliverable": "Multi-lagoon portfolio"},
    ]
    df_phases = pd.DataFrame(phases)

    phase_colors = {"Launch": "#5dade2", "LSTM Integration": "#f4d03f", "Production Ensemble": "#e67e22", "Mature Platform": "#27ae60"}

    def color_focus(val):
        bg = phase_colors.get(str(val), "")
        return f"background-color: {bg}; color: white; font-weight: bold" if bg else ""

    styled = df_phases.style.map(color_focus, subset=["Focus"]).set_properties(**{"text-align": "left"}).hide(axis="index")
    st.dataframe(styled, use_container_width=True, hide_index=True)

    callout(
        "<strong>Key research finding:</strong> Random Forest consistently outperforms benchmarks once "
        "training data exceeds 4 years (MAPE 16.4% lower). XGBoost achieved R² = 0.92 for HABs prediction. "
        "Operational algal bloom forecasting systems are still scarce — this is a differentiator.",
        "info",
    )
