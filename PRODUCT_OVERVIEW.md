# Dubai Lagoons Dashboard — Product Overview

> Written for business-strategy work. Pair with a market-challenges document
> to develop a go-to-market plan. This file describes what the product is,
> who it's for, what it does today, and what state the build is in — not
> the market itself.

## 1. One-line description

A multi-tenant SaaS platform that monitors, predicts, and proves regulatory
compliance for artificial lagoons and water features in the UAE/GCC —
turning manual water-quality logging and algae-bloom guesswork into a
dashboard, a predictive model, and an auditable PDF compliance report.

## 2. The problem it addresses

Dubai (and the wider GCC) has a large and growing footprint of engineered
lagoons and water bodies — golf course lakes, master-planned community
lagoons, resort water features — that are:

- Fed largely by **Treated Sewage Effluent (TSE)**, which is nutrient-rich
  and drives eutrophication and cyanobacterial/algal blooms.
- Subject to **Dubai Municipality water-quality standards** (pH,
  dissolved oxygen, TSS, turbidity, COD, ammonia, phosphate, oils & grease,
  E. coli, total coliforms — 10+ regulated parameters).
- Operated today mostly through **manual lab sampling, spreadsheets, and
  reactive treatment** (chemical dosing, aeration, ultrasound) rather than
  forecasting — operators find out about a bloom risk when it's already
  visible, not days before.
- A **liability surface**: non-compliant water quality creates regulatory,
  reputational, and sometimes public-health exposure for the community
  developer, HOA, or facilities manager responsible for the lagoon.

## 3. What the product does

### Core workflow
1. **Field teams log monthly/periodic readings** (14 Compliance parameters) via
   a web form, a voice/phone pipeline (Vonage + n8n → HTTP API), an Android
   app, or by **photographing a lab report** — Claude Vision extracts the
   structured values automatically (`extract.py`), with a human
   review/correction step before anything is saved (required for
   regulatory data).
2. **Every reading is scored against compliance limits** and assigned a 4-level
   alert (`core/alert_engine.py`): GREEN → WATCH → WARNING → CRITICAL, each
   tied to a specific monitoring cadence and prescribed treatment protocol
   (enzyme dosing, aeration intensity, ultrasound, explicit "DO NOT deploy
   algicide" guardrails at high alert levels).
3. **A generated, watermark-gated PDF compliance report** is the paid
   deliverable (`reporting.py`) — the live dashboard is the free hook; the
   official, clean report a client can hand to a regulator or their board
   is the thing being sold.
4. **A forecasting/decision-support layer** (`science/`) goes beyond
   monitoring into prediction: bloom forecasting (Random Forest + XGBoost +
   LSTM ensemble, R² 0.78–0.92 depending on horizon), nutrient-source
   attribution (TSE, irrigation runoff, greywater, dust deposition,
   sediment internal loading, groundwater seepage — ranked by
   contribution and controllability), residence-time and hydraulic
   transport modelling, sediment/Fe-P coupling, adaptive sampling
   recommendations, and an early-stage "digital twin" of the lagoon system.
5. **Species-level threat intelligence** — a reference library mapping
   specific dinoflagellate/cyanobacteria/diatom species to salinity range,
   toxin type, threat level, and treatment approach, used to interpret
   readings in context rather than as raw numbers.

### Product surface (what a user actually clicks through)
React frontend pages: Home, Dashboard, Monitoring, Alerts, Calendar,
Compliance Report (PDF generation), Upload Report (photo/PDF extraction),
Species, Drivers (nutrient sources), Sludge, ML System (bloom forecasts),
Science Simulation (digital twin), Site Manager, User Manager, Settings
(billing + admin).

### Multi-tenant SaaS mechanics
- **Auth**: Clerk (identity) joined to Supabase `user_profiles` (role +
  organization). Roles: `super_admin`, `admin`, `operator`, `auditor`.
  New unattached sign-ups auto-provision their own organization so nobody
  hits a dead end pre-sales-contact.
- **Tenancy**: one `organization` → many `sites` (each site = one lagoon).
  Row-level security scopes all data by organization.
- **Billing**: seat/site-limit tiers — Starter (1 site, $199/mo), Growth
  (5 sites, $799/mo), Professional (15 sites, $1,999/mo), plus an internal
  unlimited Dev tier. Payment is behind a provider abstraction
  (`payments/`) — Checkout.com is the active processor, Stripe is fully
  built and kept ready as a drop-in alternative via configuration only.
  This means a live pricing/plan change or a processor switch is an
  operational decision, not an engineering one.
- **Deployment**: unified FastAPI app (serves the built React SPA + the
  `/api/*` backend from one process) on Render, custom domain
  `lagoons.gdm-enviro.com`. A legacy Streamlit build of the same dashboard
  still exists but is deprecated in favor of the React/FastAPI app.
- **Agent/automation access**: an MCP server (`agent_server.py`) exposes
  the compliance logic and data layer as tools so a field team can log
  readings or query compliance status by talking to Claude Desktop/Cursor
  instead of using the web form — relevant for low-connectivity field
  conditions or voice-first workflows.

## 4. Who it's for

- **Primary buyer**: master-planned community developers, HOAs, and
  facilities/asset managers in Dubai (and transferable to the wider GCC)
  who are legally or contractually responsible for lagoon/lake water
  quality — the entities who must produce a compliance report to Dubai Municipality,
  Dubai Municipality, or their own governance board.
- **Primary user (day to day)**: the environmental/O&M contractor or
  in-house team that does the physical sampling, dosing, and treatment —
  they need the alert levels and treatment protocol to decide what to do
  *today*, not just a compliance record for later.
- **Secondary/downstream audience**: the regulator or auditor who receives
  the PDF report as proof of monitoring and compliance.

## 5. What makes it differentiated (as built, not aspirational)

- It is **not just a data-logging dashboard** — the alert engine embeds
  operational treatment protocols (what enzyme, what aeration intensity,
  what to avoid) directly against the regulatory thresholds, so the output
  is a decision, not just a number.
- It **forecasts rather than just reports** — the ML ensemble and
  nutrient-source attribution are aimed at telling an operator a bloom is
  coming and *why* (which source is driving it), which is the harder and
  more defensible product than a compliance spreadsheet.
- It has a **built-in monetization mechanism** tied to the actual paid
  deliverable (the clean PDF report vs. the free/watermarked dashboard
  view), not a generic seat-based paywall bolted onto reporting.
- The domain rules (compliance limits, species thresholds, nutrient rankings,
  seasonal treatment phases) are **UAE/GCC-specific**, not adapted from a
  generic US/EU water-quality product — that specificity is a moat against
  general-purpose water-monitoring SaaS entering the region, but it is
  also a constraint on how directly the product can expand outside GCC
  regulatory frameworks without rework.

## 6. Current build maturity (important for strategy — don't oversell)

This is a working product with real architecture, not a prototype, but it
is **pre-revenue / early-commercial**, and a few things should shape any
market strategy:

- Billing is technically complete on both a legacy (Stripe) and new
  (Checkout.com) path, but **no live paying customer has gone through it
  yet** — pricing tiers exist but are unvalidated against willingness to
  pay.
- The ML forecasting layer (`science/`) has documented R² performance
  claims but the roadmap docs inside `science/` (`Scientific_Roadmap.md`,
  `CLAUDE_FINAL_TASKLIST.md`) indicate this is **still being built out**,
  not a finished, field-validated model — treat the predictive/"digital
  twin" story as the frontier capability being developed, not a proven,
  battle-tested feature to lead marketing with yet.
- The org-onboarding flow for a brand-new customer (self-serve org
  creation, first site, first subscription) is functional but young —
  worth confirming end-to-end before any paid pilot, not just assuming it
  from the code.
- Security note for GTM conversations with security-conscious enterprise
  buyers (developers/HOAs procuring at scale): CORS is currently wide open
  (`allow_origins=["*"]`) and should be tightened before a serious
  enterprise sales process, and invite-email delivery is not yet wired to
  a transactional provider.

## 7. Adjacent capabilities not yet exposed as product

The codebase includes a broader "Forensic Asset Hydrogeology" orchestration
layer (groundwater flow modelling via MODFLOW/FloPy, geochemistry via
PHREEQC, InSAR subsidence analysis, etc.) aimed at **forensic groundwater
and construction-dispute liability investigations** — a related but
distinct GCC market (subsurface water/Sabkha dissolution, construction
liability attribution) from the surface-lagoon monitoring product described
above. Worth flagging as a possible adjacent product line or upsell path
for the same buyer persona (developers/asset managers facing GCC-specific
water risk), but it is a separate codebase/capability, not part of this
lagoon SaaS product.
