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

[Unreleased]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/garyduwyanemorgan/DECCA-Lagoons-App/releases/tag/v0.1.0
