# WOMS Permissions — Implementation Status

Branch `feat/permissions-phase0`. Tracks what is built vs. what remains, per phase.
Honest labelling per the review prompt: nothing is marked done that isn't verified.

**Legend:** ✅ done & tested · 🟡 authored, needs live-DB/integration verification ·
📄 migration authored, UNAPPLIED · ⛔ not started (needs product/UI work).

| Phase | Item | Status | Notes |
|---|---|---|---|
| 0 | Fail-closed resolver (CRIT-1) | ✅ | `api_server.py`; `AUTHZ_FAIL_CLOSED` escape hatch; test proves 401 |
| 0 | Characterization/authz test harness | ✅ | `tests/` — 26 tests, plain-python or pytest |
| 0 | Rotate live secrets (CRIT-4) | ⛔ | **Yours** — Stripe/Supabase keys on disk |
| 1 | Atomic permission catalogue | ✅ | `core/authz.py`, 44 perms, explicit bundles |
| 1 | Central authorization service | ✅ | `_ensure_permission()`, 18 endpoints |
| 1 | Convert inline role checks (behavior-preserving) | ✅ | all converted; `test_ensure_permission_central_gate` |
| 1 | Structured audit events | ✅ | `core/audit.py`; denials + site/role/user mutations |
| 1 | `audit_events` table + persistence | 📄 / ✅ | `006_audit_events.sql` unapplied; `_persist` lights up when applied |
| 1 | Last-super_admin removal guard (A3) | 🟡 | `remove_user`; logic simple, **needs live-DB smoke test** |
| 1 | CRIT-3 report finalize gate | ✅ | `reports.approve_final` vs `generate_draft` |
| 2 | Business-unit / project / assignment tables | 📄 | `007_assignments.sql` (+down); nullable, backfill-safe |
| 2 | `user_profiles(organization_id)` index | 📄 | in 007 |
| 2 | Scope-resolution logic | ✅ | `core/scope.py`, tested (`test_domain_logic.py`) |
| 2 | Assignment query helpers | 🟡 | `db/queries.py` get/set assignments; fail-safe; **needs live-DB** |
| 2 | Assignment-admin endpoints | 🟡 | `GET/PUT /users/{id}/sites`; server-validates org-owned ids; audited |
| 2 | Enforce scope in reads (behind flag) | 🟡 | `_effective_site_ids` wired into `GET /sites`; `SCOPE_ENFORCEMENT` default OFF; tested off/on |
| 2 | Enforce scope in site-scoped writes | ⛔ | `/log`, `/sludge`, `/community`, `/report` still org-wide; wire `_effective_site_ids` after backfill |
| 2 | Frontend site-selector to effective scope | ⛔ | frontend work |
| 2 | RLS decision (app-layer + backstop) | ✅ (decided) | documented; new tables RLS-on, service-role grant |
| 3 | M1 billing.status → billing.read | ✅ | Manager+; `test_billing_read_starts_at_manager_tier` |
| 3 | M5 extract excludes auditor | ✅ | `readings.create`; test |
| 3 | A4 invite email-case normalization | 🟡 | `get_user_profile`; **needs live-DB verification** |
| 3 | Destructive-delete audit | ✅ | site + sludge delete emit audit; **soft-delete/retention deferred (needs schema)** |
| 4 | Corrective-action tables | 📄 | `008_corrective_actions.sql` (+down); append-only events |
| 4 | State machine + permissions | ✅ | `core/corrective.py`, tested |
| 4 | Endpoints (list/create/assign/progress/close) | ⛔ | authz + state machine ready; endpoint bodies + live-DB tests remain |
| 4 | Frontend corrective-action UI | ⛔ | frontend work |
| 5 | Inventory tables + append-only ledger | 📄 | `009_inventory.sql` (+down); immutable ledger trigger |
| 5 | Ledger invariants (balance/transfer/no-negative) | ✅ | `core/inventory.py`, tested |
| 5 | Concurrency-safe stock ops (Postgres RPC) | 📄 | `011_inventory_rpc.sql` — advisory-lock `record_consumption`/`record_transfer`; the ONLY safe way to prevent negative stock under concurrency |
| 5 | Endpoints (consume/receive/transfer/adjust/configure) | ⛔ | authz + logic + RPC ready; endpoint bodies call `client.rpc(...)`; need live-DB integration tests |
| 5 | Financial-field protection | 🟡 (design) | `inventory.valuation.read` bundled; enforce in endpoint projection |
| 5 | Low-stock/expiry alerts | 🟡 | `is_low_stock` done; expiry job + delivery remain |
| 6 | Asset/maintenance tables | 📄 | `010_assets.sql` (+down) |
| 6 | Asset config endpoints + task generation | ⛔ | needs endpoints + scheduler |
| 7 | KPI aggregations (site/project/portfolio/exec) | ⛔ | needs endpoints; must not leak out-of-scope/financial rows |
| 8 | Pen-style authz tests, log review, rollback drills | ⛔ | partial: negative tests exist; migration rollback scripts authored |
| 8 | Feature-flag rollout, remove legacy checks | 🟡 | `AUTHZ_FAIL_CLOSED` + planned `SCOPE_ENFORCEMENT`; no flag framework yet |

## New files this branch
- `core/authz.py`, `core/audit.py`, `core/scope.py`, `core/inventory.py`, `core/corrective.py`
- `tests/test_authz.py`, `tests/test_resolver_authz.py`, `tests/test_domain_logic.py`
- `db/migrations/006_audit_events.sql` … `010_assets.sql` (+ `_down.sql` for each)
- Review docs: `PERMISSIONS_REVIEW_PACKAGE.md`, `..._DISCOVERY.md`, `..._DISCOVERY_2.md`, this file

## What a reviewer must do before deploy
1. **Rotate secrets** (CRIT-4) and switch local to `sk_test_`.
2. **Apply migrations 006–010 in order** in the Supabase SQL editor, on a backup first; verify with the `_down.sql` scripts on a copy.
3. **Smoke-test the live-DB paths** marked 🟡 (last-super_admin guard, A4 invite linking, audit persistence).
4. **Run the app** and exercise: signed-in user still works; anonymous request → 401; operator → 403 on final report/billing; auditor → 403 on extract.
5. Decide open questions still open: Q3 (sludge.delete tighten to Manager+), financial projection details, KPI metric ownership.

## Known caveats
- Audit `_persist` is a synchronous best-effort insert per event (incl. every denial); consider async/batched writes if denial volume is high.
- Scope enforcement (Phase 2 query wiring) is intentionally NOT active — tables + pure logic exist, but enforcing before backfilling assignments would lock out existing users. Gate behind `SCOPE_ENFORCEMENT` after backfill.
- SQL migrations are authored to Supabase/Postgres conventions but have NOT been executed; validate on a staging copy.
