# Changelog

All notable changes to the Dubai Lagoons Compliance platform are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Version source of truth:** the root `VERSION` file and `frontend/package.json`.
Releases are automated — run `scripts/release.sh [patch|minor|major|auto]` (or the
`/release` command, or `scripts\release.ps1` on Windows). It bumps the version files,
generates the new version's entries from the Conventional-Commit messages since the
last tag, commits, tags `vX.Y.Z`, and pushes. `[Unreleased]` below holds only the
forward-looking **Planned** roadmap; shipped entries are filled in automatically at
release time, so just write clear commit messages (`feat:`, `fix:`, `chore:` …).

## [Unreleased]

### Planned
- Alert auto-dispatch (email / SMS / push) on Level 3–4 — SMTP is half-built (used only for
  access requests); the Vonage/n8n voice channel is the intended delivery path.
- Stateful alert de-escalation — enforce the 48 / 72 / 168 h hold periods over time
  (escalation is currently evaluated statelessly per reading).
- Dashboard KPI tiles — surface live parameter values for a selected site (they currently
  fall back to sample data because `/api/status` returns only the alert level and compliance).
- Frontend bundle code-splitting (single chunk is ~968 kB).
- Reconcile organisation `site_limit` with the real billing plan before production billing.

## [1.8.0] - 2026-07-22

- feat(landing): full site footer, modelled on the GDM Environmental one

## [1.7.0] - 2026-07-22

- feat(landing): public landing page with the GDM mosaic globe as its hero
- feat(scope): park the lagoon world behind a feature flag; drop "Start here"

## [1.6.0] - 2026-07-21

- feat(standards,upload,docs): close the open issues

## [1.5.0] - 2026-07-21

- feat(kpi,dashboards,nav): connect uploaded certificates to the dashboards
- feat(reporting,home,upload): audits 4, 5 and 6
- chore(brand): rename to Compliance Intelligence Platform
- feat(nav,sites): audit 1a and 3 — site infrastructure and nav by asset class

## [1.4.1] - 2026-07-21

- fix(upload): asset dropdown lists sampled asset types, not instances

## [1.4.0] - 2026-07-21

- feat(assets): asset register in Settings, and upload derives from it
- fix(assets): asset_class and scope were silently discarded on create

## [1.3.0] - 2026-07-21

- feat(assets): scope belongs to the asset, and the upload flow now resolves it

## [1.2.0] - 2026-07-21

- feat(compliance): capture the governing standard and give a certificate verdict

## [1.1.0] - 2026-07-21

- feat: env-first secrets and deterministic Wimpey lab-report ingestion

## [1.0.4] - 2026-07-16

- feat(settings): Features tab with Intelligence/Reporting/Reference toggles

## [1.0.3] - 2026-07-15

- feat(settings): tabbed settings page - one section per tab

## [1.0.2] - 2026-07-15

- fix(sidebar): sample-data label tracks the real flag; authenticate site fetch
- feat(sites): street address per site + persistent Google Maps panel

## [1.0.1] - 2026-07-15

- feat(ui): searchable multi-select dropdown for site assignment
- chore: itemize v1.0.0 changelog and renumber demo migration to 014

## [1.0.0] - 2026-07-15

- feat(demo): self-service demo mode — one-click 30-day activation (server-provisioned
  key, never typed by the user), unlimited sites while active, read-only after expiry
  with billing kept open as the one-click switch-to-live (migration 014)
- feat(users): Sites column in User Management — checkbox multi-select of the sites each
  user can work on; editable by Executive Management only (`users.sites.assign`)
- feat(authz): admin site scope now honours direct site assignments in addition to
  project-derived sites
- feat(api): `/sites` returns site ids; `/users` returns per-user `site_ids` (batched)
- test: demo-mode decision logic + executive-only permission coverage

## [0.7.0] - 2026-07-14

- feat(design): ERP-style sidebar — collapsible groups, icon rail, signed-in user
- refactor(design): Dashboard, Alerts, and Sidebar onto canonical tokens
- refactor(design): dashboard tiers use shared MetricCard and StatusBadge
- refactor(design): operations pages adopt shared MetricCard/StatusBadge/Button
- refactor(design): SampleDataToggle uses the shared ui/Toggle Switch
- feat(design): shared UI component library + global accent/ink adoption
- feat(design): canonical design-system tokens in lib/tokens.ts
- fix: never blend sample data into live lab readings
- feat: persist the sample-data toggle on the user profile

## [0.6.0] - 2026-07-13

- chore: ignore .venv-codex and stop tracking compiled bytecode
- feat(frontend): UI for corrective actions, inventory, assets, and KPIs
- fix(db): drop audit_events org FK so tenants remain deletable (013)
- test(integration): phase 8 end-to-end authz + workflow suite
- feat(assets,kpi): phase 6 asset/maintenance config + phase 7 management KPIs
- feat(inventory): phase 5 endpoints — stock, atomic consume/transfer, valuation
- feat(actions): phase 4 corrective-action workflow + fix append-only cascade
- chore(db): wrap migrations 006-011 (and rollbacks) in transactions
- feat(inventory): concurrency-safe stock RPCs (unapplied)
- feat(authz): phase 2 scope enforcement (flag-gated) and assignment admin
- feat(authz): phase 3 fixes, domain logic, and schema for phases 2-6
- feat(authz): centralize permissions and fail closed on unauthenticated requests

## [0.5.0] - 2026-07-11

- fix: never cache index.html
- feat: authenticate against the Clerk dev instance on localhost
- feat: auto-provision each new sign-in as super_admin of its own organisation
- feat: invite users by Clerk invitation instead of a temp password
- feat: role-aware dashboards from site supervisor to executive
- feat: add an auditor role and a shared role model

## [0.4.1] - 2026-07-10

- fix: require authentication for /api/extract

## [0.4.0] - 2026-07-10

- chore: backport --verify to the release script
- feat: warn when a stale bundle is talking to a newer API

## [0.3.0] - 2026-07-09

- feat: surface deployed version in Settings and expose /api/version

## [0.2.0] - 2026-07-08

- feat: add one-command release automation (/release + scripts/release.{sh,ps1})

## [0.1.0] - 2026-07-08

First versioned baseline — the platform as demoed to the client. Establishes changelog and
version tracking going forward.

### Added
- **Systems Intelligence Engine loop tabs** — each renders an Obsidian-style force-directed
  graph (dark canvas, glowing health-coloured nodes, animated influence edges), a month
  selector, and a "what's changing / why / what's next / what to do" intelligence panel:
  - **Environmental Drivers** — Bloom Pressure Index fusing temperature, nutrients, solar
    radiation, and salinity/stratification into a single signal with event nodes.
  - **Chemistry Loop** (amber identity) — Chemical Stress Index over 8 processes, encoding the
    forensic organic-loading → oxygen-depletion → redox → phosphorus-release chain.
  - **Ecology Loop** (green identity) — Ecological Stress Index over 8 biological processes,
    with Algae Bloom / Fish Kill / Night Oxygen Crash event nodes.
- **Live Alert & Response Protocol** — reads the active site's latest reading, shows the current
  alert level, highlights the active treatment protocol, lists the triggering factors, and
  carries a persistent alert-level colour legend.

### Fixed
- **Critical auth regression** — the cached Clerk session token (~60 s TTL) was silently
  downgrading every authenticated *write* to `operator` once it expired, producing spurious
  `403`s ("Only admins can create sites") and blocked uploads. `AuthContext` now refreshes the
  token every 45 s and exposes a fresh-token getter; `SiteManager` and `UploadReport` fetch a
  fresh token per request and send the `X-User-Email` header.

### Changed
- Rebranded **"DECCA" → "Compliance" / "Dubai Municipality (DM)"** across the codebase
  (constants, components, report builder, service names). The repository folder and git remote
  were intentionally left unchanged.
- Raised organisation `site_limit` to **15** (was Starter = 1) to allow multi-site portfolios.
  Applied directly in Supabase rather than through the billing flow — see the Unreleased note.

### Security
- Restored and hardened `.gitignore` so `.streamlit/secrets.toml`, `frontend/.env.local`,
  `node_modules/`, and `dist/` can never be committed (Supabase, Clerk, Stripe, and Anthropic
  keys live in those files).

[Unreleased]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.8.0...HEAD
[1.8.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.0.4...v1.1.0
[1.0.4]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.0.3...v1.0.4
[1.0.3]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v0.7.0...v1.0.0
[0.7.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/releases/tag/v0.1.0
