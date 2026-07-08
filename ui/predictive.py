"""Predictive Monitoring — the client-facing value proposition.

Shows, per lagoon: predicted status, model confidence, and a SAMPLE/SKIP
recommendation; and across the portfolio: how much sampling (and money) the
model saves while keeping every lagoon within the regulatory floor.

STRICT: this page shows ONLY outputs — predicted value, confidence,
recommendation, savings. It must never reveal HOW the prediction is made
(no weather, no calibration, no model internals, no reasoning).
"""
from datetime import date

import streamlit as st

from data.provider import get_monthly_readings  # noqa: F401  (kept for parity)
from db.client import is_configured
from db.queries import get_site_names, get_readings_for_site
from science.portfolio import assess_lagoon
from science.adaptive_sampling import LagoonStatus, optimize_portfolio
from science.config import COMPLIANCE_MIN_SAMPLING_DAYS, SAMPLING_COST_AED
from ui.components import page_header, section_header, metric_card, callout


def _conf_color(c: float) -> str:
    return "#27ae60" if c >= 80 else "#f39c12" if c >= 60 else "#e74c3c"


def _confidence_ring(conf: float) -> str:
    """Inline SVG donut for a confidence percentage."""
    r, c = 26, _conf_color(conf)
    circ = 2 * 3.14159 * r
    fill = circ * max(0.0, min(conf, 100)) / 100.0
    return f"""
    <svg width="72" height="72" viewBox="0 0 72 72">
      <circle cx="36" cy="36" r="{r}" fill="none" stroke="#e6ebf1" stroke-width="7"/>
      <circle cx="36" cy="36" r="{r}" fill="none" stroke="{c}" stroke-width="7"
        stroke-dasharray="{fill:.1f} {circ:.1f}" stroke-linecap="round"
        transform="rotate(-90 36 36)"/>
      <text x="36" y="41" text-anchor="middle" font-size="16" font-weight="700"
        fill="{c}" font-family="Arial">{conf:.0f}%</text>
    </svg>
    """


def _lagoon_card(rec, assessment) -> str:
    sample = rec.action == "SAMPLE"
    badge_bg = "#e74c3c" if sample else "#27ae60"
    badge_txt = "SAMPLE DUE" if sample else "SKIP — ON TRACK"
    ring = _confidence_ring(assessment.confidence_pct)
    return f"""
    <div style="background:white; border-radius:12px; padding:1rem 1.2rem;
        box-shadow:0 2px 8px rgba(0,0,0,0.08); border-top:4px solid {badge_bg};
        display:flex; align-items:center; gap:1rem;">
      <div>{ring}</div>
      <div style="flex:1;">
        <div style="font-weight:700; color:#1B3A5C; font-size:1.05rem;">{rec.site}</div>
        <div style="color:#555; font-size:0.85rem; margin:0.15rem 0;">{assessment.headline}</div>
        <div style="color:#888; font-size:0.75rem;">{rec.reason}
          &middot; last sample {int(rec.days_since_sample)}d ago</div>
        <div style="margin-top:0.4rem;">
          <span style="background:{badge_bg}; color:white; padding:0.2rem 0.7rem;
            border-radius:12px; font-size:0.75rem; font-weight:700;">{badge_txt}</span>
        </div>
      </div>
    </div>
    """


def render():
    page_header(
        "PREDICTIVE MONITORING",
        "Optimised sampling — predict lagoon condition, sample only where needed",
        icon="📡",
    )

    if not is_configured():
        callout("Connect site data to run predictive monitoring. Showing nothing live yet.", "warning")
        return

    sites = get_site_names()
    if not sites:
        callout("No lagoons configured yet.", "warning")
        return

    today = date.today()
    year, month = today.year, today.month

    # ── Assess each lagoon (hidden driver+calibration stack) ──
    statuses, assessments, sites_readings = [], {}, {}
    for site in sites:
        readings = get_readings_for_site(site)
        sites_readings[site] = readings
        a = assess_lagoon(site, readings, year, month)
        assessments[site] = a
        statuses.append(LagoonStatus(
            site=site, confidence_pct=a.confidence_pct,
            days_since_sample=a.days_since_sample, risk_level=a.risk_level,
            headline=a.headline,
        ))

    plan = optimize_portfolio(statuses)

    # ── Portfolio-scale projector (client may run many more lagoons) ──
    section_header("Portfolio")
    pc1, pc2 = st.columns([1, 3])
    with pc1:
        portfolio_size = st.number_input(
            "Total lagoons in portfolio", min_value=len(sites), max_value=500,
            value=max(len(sites), 15), step=1,
            help="Project the saving to your full portfolio.")
    skip_rate = plan.n_skip / plan.n_lagoons if plan.n_lagoons else 0.0
    proj_skip_per_cycle = skip_rate * portfolio_size
    proj_annual_saving = proj_skip_per_cycle * SAMPLING_COST_AED * 12

    # ── Headline KPIs ──
    k = st.columns(4)
    with k[0]:
        metric_card("Sample This Cycle", f"{plan.n_sample} / {plan.n_lagoons}",
                     "#e67e22", "Only where the model is unsure or due")
    with k[1]:
        metric_card("Safely Skipped", f"{plan.n_skip} / {plan.n_lagoons}",
                     "#27ae60", "Model confident & within cadence")
    with k[2]:
        metric_card("Projected Annual Saving", f"AED {proj_annual_saving:,.0f}",
                     "#1B3A5C", f"Across {portfolio_size} lagoons")
    with k[3]:
        metric_card("Portfolio Confidence", f"{plan.mean_confidence_pct:.0f}%",
                     _conf_color(plan.mean_confidence_pct), "Mean predicted-state confidence")

    callout("Every lagoon stays within the Compliance mandated sampling cadence "
            f"(≤ {COMPLIANCE_MIN_SAMPLING_DAYS} days). The model only ever removes "
            "<em>discretionary</em> sampling, never the regulatory minimum.", "success")

    if plan.next_best_to_sample:
        callout(f"<strong>Next priority:</strong> if you can take one more sample this cycle, "
                f"sample <strong>{plan.next_best_to_sample}</strong> — it most reduces "
                "uncertainty across the portfolio.", "info")

    # ── Per-lagoon cards ──
    section_header("Lagoon Status")
    rec_by_site = {r.site: r for r in plan.recommendations}
    cols = st.columns(2)
    for i, site in enumerate(sites):
        with cols[i % 2]:
            st.markdown(_lagoon_card(rec_by_site[site], assessments[site]),
                        unsafe_allow_html=True)
            st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

    # ── Confidence trend (how certainty grows with sampling) ──
    _render_confidence_trend(sites_readings)

    # ── Predicted detail (still output-only) ──
    section_header("Predicted Readings (this cycle)")
    import pandas as pd
    rows = []
    for site in sites:
        a = assessments[site]
        row = {"Lagoon": site, "Confidence": f"{a.confidence_pct:.0f}%",
               "Recommendation": rec_by_site[site].action}
        for p, d in a.predictions.items():
            row[f"{d['label']} ({d['unit']})"] = f"{d['value']:.1f}"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
    st.caption("Predicted values shown with the portfolio's model confidence. "
               "Confidence rises as samples are taken and the model is validated.")

    # ── Model accuracy track record (out-of-sample validation) ──
    _render_track_record(sites_readings)


def _render_confidence_trend(sites_readings: dict):
    """Per-lagoon confidence over time — certainty rising as each lagoon is
    sampled. Client-safe: shows confidence trajectory only."""
    import plotly.graph_objects as go
    from science.backtest import confidence_trajectory
    from science.config import ADAPTIVE_CONF_THRESHOLD

    series = {s: confidence_trajectory(s, r) for s, r in sites_readings.items()}
    series = {s: t for s, t in series.items() if t}
    if not series:
        return

    section_header("Confidence Trend")
    st.caption("How each lagoon's prediction confidence grows as samples accumulate. "
               "A stable lagoon climbs and stays high; a volatile one plateaus low and "
               "keeps needing samples.")

    palette = ["#2E5D8A", "#27ae60", "#e67e22", "#9b59b6", "#16a085", "#c0392b"]
    fig = go.Figure()
    for i, (site, traj) in enumerate(series.items()):
        fig.add_trace(go.Scatter(
            x=[p["label"] for p in traj], y=[p["confidence"] for p in traj],
            mode="lines+markers", name=site,
            line=dict(color=palette[i % len(palette)], width=3),
            marker=dict(size=6)))
    # Sampling threshold reference line.
    fig.add_hline(y=ADAPTIVE_CONF_THRESHOLD, line_dash="dot", line_color="#e74c3c",
                  annotation_text=f"Skip threshold ({ADAPTIVE_CONF_THRESHOLD:.0f}%)",
                  annotation_position="bottom right")
    fig.update_layout(height=380, template="plotly_white",
                      yaxis_title="Model confidence (%)", yaxis_range=[0, 100],
                      xaxis_title="Sample timeline",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                      margin=dict(t=50, b=40))
    st.plotly_chart(fig, width='stretch')
    callout("Lagoons whose line sits above the threshold can have discretionary "
            "sampling stretched; lines below it keep their full cadence.", "info")


def _render_track_record(sites_readings: dict):
    """Validation ledger: out-of-sample predicted-vs-actual accuracy.
    Client-safe — shows accuracy only, never how the prediction is made."""
    import pandas as pd
    import plotly.graph_objects as go
    from science.backtest import backtest_site
    from science.validation import aggregate

    all_recs = []
    for site, readings in sites_readings.items():
        all_recs.extend(backtest_site(site, readings))
    if not all_recs:
        return

    stats = aggregate(all_recs)
    section_header("Model Accuracy — Validation Track Record")
    st.caption("Each past sample was predicted using only the samples before it "
               "(out-of-sample), then checked against the laboratory result.")

    k = st.columns(3)
    with k[0]:
        metric_card("Within Confidence Band", f"{stats.within_band_rate_pct:.0f}%",
                     _conf_color(stats.within_band_rate_pct),
                     f"{stats.n} predictions validated")
    with k[1]:
        metric_card("Mean Error", f"{stats.mean_pct_error:.0f}%", "#2E5D8A",
                     "Predicted vs laboratory")
    with k[2]:
        metric_card("Predictions Validated", f"{stats.n}", "#1B3A5C",
                     "Across all lagoons & parameters")

    # Predicted vs actual scatter (the credibility chart).
    in_band = [r for r in all_recs if r.within_band]
    out_band = [r for r in all_recs if not r.within_band]
    fig = go.Figure()
    if in_band:
        fig.add_trace(go.Scatter(
            x=[r.actual for r in in_band], y=[r.predicted for r in in_band],
            mode="markers", name="Within band",
            marker=dict(color="#27ae60", size=8, opacity=0.7)))
    if out_band:
        fig.add_trace(go.Scatter(
            x=[r.actual for r in out_band], y=[r.predicted for r in out_band],
            mode="markers", name="Outside band",
            marker=dict(color="#e74c3c", size=8, opacity=0.7)))
    lim = max([r.actual for r in all_recs] + [r.predicted for r in all_recs]) * 1.1
    fig.add_trace(go.Scatter(x=[0, lim], y=[0, lim], mode="lines",
                             name="Perfect", line=dict(color="#95a5a6", dash="dash")))
    fig.update_layout(height=380, template="plotly_white",
                      xaxis_title="Laboratory result", yaxis_title="Model prediction",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
                      margin=dict(t=50, b=40))
    st.plotly_chart(fig, width='stretch')

    # Per-parameter accuracy.
    prows = []
    for p, d in stats.per_parameter.items():
        from science.config import PREDICTED_PARAMETERS
        label = PREDICTED_PARAMETERS.get(p, {}).get("label", p)
        prows.append({"Parameter": label, "Predictions": d["n"],
                      "Within Band": f"{d['within_band_rate_pct']:.0f}%",
                      "Mean Error": f"{d['mean_pct_error']:.0f}%" if d["mean_pct_error"] is not None else "—"})
    st.dataframe(pd.DataFrame(prows), width='stretch', hide_index=True)
    callout("This track record is the basis for reducing sampling: the more "
            "predictions that land within band, the more confidently discretionary "
            "sampling can be stretched — always within the regulatory floor.", "info")
