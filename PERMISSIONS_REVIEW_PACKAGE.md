# WOMS Permissions — Pre-Implementation Review Package

**Baseline:** version `0.5.0`, commit `0b496a2`.
**Method:** read-only discovery per `PERMISSIONS_IMPLEMENTATION_REVIEW_PROMPT.md`, executed by four parallel analysis agents (backend authz, data model/DB, frontend UX, identity/secrets/tests/ops). Raw evidence: `PERMISSIONS_REVIEW_DISCOVERY.md` (Agents B, C) and `PERMISSIONS_REVIEW_DISCOVERY_2.md` (Agents A, D).
**Status:** discovery complete. **No application code, migrations, or config were changed.** Awaiting human sign-off before Phase 0.

---

## 1. Executive summary

The current system correctly establishes *authentication* (Clerk JWT verification) and a *single-tenant-column* data model, and it does several things well: role resolves server-side from `/api/profile` (not client-mutable Clerk metadata), request bodies are tightly typed (no mass-assignment holes), cross-tenant role edits are blocked, and no secrets are git-committed. **However, authorization is not enforced as a boundary.** The identity resolver is used as if it were a gate, and it fails *open*.

Four findings are **Critical** and gate everything else:

- **CRIT-1 (auth bypass / cross-tenant IDOR).** The shared auth dependency returns a valid `operator` identity for *tokenless* requests, taking the tenant id from a client-supplied `X-Organization-Id` header. Because the backend talks to Postgres as **service-role (RLS bypassed)**, that header is the *only* tenant boundary — so an unauthenticated attacker who supplies a victim org UUID can read the victim's compliance reports, sites, sludge, and requests, and can write/delete readings, sludge zones, and data requests. *(api_server.py:343-349; corroborated by two independent agents.)*
- **CRIT-2 (privilege escalation).** Any authenticated-but-unprovisioned Clerk user is auto-granted `super_admin` over a fresh organization. This is safe only if the Clerk instance truly forbids open sign-up — an assumption that lives in a code comment, not in an allow-list. *(api_server.py:329-341, 255-276.)*
- **CRIT-3 (regulatory integrity).** The final, watermark-free compliance PDF is downloadable by any role — and, via CRIT-1, anonymously — with no approval/sign-off separation. *(api_server.py:1357-1396.)*
- **CRIT-4 (secret exposure).** A **live** Stripe secret key and the Supabase service-role key sit unencrypted on this workstation (`.streamlit/secrets.toml`, `setup_bundle.md`). Not git-committed, but should be rotated and swapped for test keys locally.

Underneath these, the model the matrix asks for is largely **unbuilt**: there is no user-to-site / user-to-project assignment, no business-unit hierarchy, no corrective-action / inventory / asset / audit-log tables, no centralized permission service, no audit trail on any sensitive mutation, and **no automated tests of any kind**. RLS policies exist but are inert because the backend connects as service-role and never uses the JWT-scoped client path (the `token` parameter is threaded through all 18 query helpers and dropped).

**Recommendation:** do **not** begin feature phases. Execute an emergency remediation of CRIT-1–4 as part of Phase 0, then proceed through the phased plan. The single highest-leverage change is to make the auth dependency **fail closed** and stop deriving tenancy from a client header — that one change closes the read/write half of CRIT-1 and several High findings.

---

## 2. Current-state discovery table

Risk classes: C=Critical, H=High, M=Medium, L=Low. Evidence is `file:line`.

| Area | Current behavior | Evidence | Risk | Required change | Phase |
|---|---|---|---|---|---|
| Auth dependency | `get_current_user_profile` returns `operator` + header-supplied org for tokenless requests (resolver used as gate) | api_server.py:343-349 | **C** | Fail closed (401); derive org only from verified profile | 0/1 |
| Tenant isolation | Service-role client bypasses RLS; only Python `org_id` filter isolates; RLS policies inert; JWT path dead (`token` dropped at all 18 call sites) | db/client.py:65,72; queries.py (18 `get_client()` calls); schema_rls.sql | **C** | Decide app-authz vs RLS; either activate JWT client or drop `token` params; never trust client org | 0/2 |
| Provisioning | Unprovisioned Clerk user auto-granted `super_admin` + new org | api_server.py:329-341,255-276 | **C** | Replace with invite-only provisioning / pending state; verify Clerk sign-up policy | 0/1 |
| Final report | `GET /report?draft=false` returns official PDF, no role check, no approval separation | api_server.py:1357-1396 | **C** | Require `reports.approve_final`; split draft vs final; gate anon (via CRIT-1 fix) | 1/3 |
| Secrets on disk | Live Stripe + service-role keys unencrypted (not committed) | .streamlit/secrets.toml:3,12,13; setup_bundle.md:13,20,21 | **C** (exposure) | Rotate keys; use `sk_test_` locally; encrypt/remove bundle | 0 |
| Assigned-site scope | Operational writes authorize by role only; any operator writes any org site | api_server.py:985,1040,1058,1155 | **H** | Add user→site assignment; enforce on read+write | 2/3 |
| Site auto-create | `get_or_create_site_id` mints sites on read/write paths; plan limit only on POST /sites | queries.py:59-78; api_server.py:497 | **H** | Remove creation side-effect from read paths; centralize limit | 3 |
| Cross-tenant delete | `delete_site` selects+deletes by name across all orgs when org None; unconditional `DELETE readings WHERE site_name` | queries.py:344-382 | **H** | Require org; soft-delete + audit + confirmation | 1/3 |
| Legacy name fallback | `site_name`-only branches drop org filter (read/write/count/validate) | queries.py:91,142,244,278,354-357,369,395 | **H** | Hard-require `organization_id`; remove fallback | 1/2 |
| Migrations | Forward-only `.sql`, run manually, no rollback/backup/txn | SAAS_STACK_GOTCHAS.md:153; db/migrations/* | **H** | Repeatable, transactional, reversible migrations + backups | 0 |
| Tests | No test infra of any kind (py or FE) | (no pytest/vitest config found) | **H** (risk) | Characterization + authz test harness | 0 |
| Billing status | Returned to every authenticated role | api_server.py:841-884 | **M** | Restrict to `billing.read` bundle (Manager+) | 1/3 |
| Inline allow-lists | Role checks duplicated across ~15 endpoints | api_server.py:486,532,574,610,635,726,890,916,939,985,1040,1058,1155,1171 | **M** | Centralize into permission dependency | 1 |
| Destructive deletes | No confirmation/soft-delete/audit; operator can delete sludge | api_server.py:529-547,1055-1059 | **M** | Confirmation + retention + audit; tighten role | 3 |
| Audit trail | No audit/security events anywhere | (no `audit_log` table/write) | **M** | Immutable `audit_events`; emit on sensitive mutations | 1 |
| Extract role | `POST /extract` allows `auditor` (matrix excludes) | api_server.py:1335 | **M** | Enforce `readings.create` bundle (exclude auditor) | 3 |
| Last super_admin | No protection against removing/demoting final exec | api_server.py:646-651 | **M** | Block last-super_admin removal/demotion | 1 |
| Invite email case | Invite lower-cases email; lookup uses raw → may miss invite → auto-provision | api_server.py:738 vs 234,318 | **M** | Normalize email on both sides | 1 |
| Recurring billing | No lock against overlapping cron runs; no dead-letter | run_recurring_billing.py:14 | **M** | Run-lock + dead-letter for `past_due` | 8 |
| Science/assess auth | Only optional `_check_key`; unmetered per-tenant | api_server.py:969,1285,1298 | **L** | Require `science.simulate`; meter | 3 |
| CORS | `allow_origins=["*"]` on both apps + header org selection | api_server.py:54-59,1425-1430 | **L** | Restrict origins in prod | 8 |
| Missing entities | No assignments, business units, corrective actions, inventory, assets, audit tables | (schema.sql, migrations) | (blocks phases) | Build per §4 | 2,4,5,6 |

---

## 3. Threat model & prioritized risk register

Per-threat: asset · attacker · entry point · precondition · impact · existing control · missing control · mitigation · verification test.

| ID | Threat | Asset | Attacker | Entry point | Precondition | Impact | Existing control | Missing control | Mitigation | Verification test |
|---|---|---|---|---|---|---|---|---|---|---|
| T1 | Cross-tenant read via header org | Reports, sites, sludge, requests | Unauthenticated / any tenant | Resolver-only GET endpoints + `X-Organization-Id` | Knows/guesses victim org UUID | Full read of victim compliance data | Org filter only (service-role) | Fail-closed auth; no client-derived tenancy | Anon GET /report with foreign org → 401 |
| T2 | Cross-tenant write/delete | Readings, sludge, requests | Unauthenticated / any tenant | POST/DELETE /log,/sludge,/community | Same as T1; operator in allow-list | Data corruption/destruction in victim org | Optional `_check_key` on /log only | Fail-closed auth + assigned-scope | Anon POST /sludge foreign org → 401 |
| T3 | Self-provision to super_admin | Whole tenant | Any Clerk-authable user | GET /profile first call | Clerk open sign-up | Executive of a fresh (or, if misused, existing) org | Comment-only Clerk assumption | Invite-only provisioning; pending default | New unknown user → pending, not super_admin |
| T4 | Site Supervisor accesses unassigned site (same org) | Site data | Insider operator | Any site-scoped endpoint | Authenticated | Sees/edits sites outside assignment | None | user→site assignment enforcement | Operator on unassigned site → 403 |
| T5 | Project Manager accesses another project | Project portfolio | Insider admin | Site/project endpoints | Authenticated | Cross-project data access | None (org-wide) | user→project assignment | Admin on foreign project → 403 |
| T6 | GM performs operational writes | Readings/sludge | Insider auditor | Write endpoints | Authenticated | Read-only role mutates data | Role allow-list excludes auditor (writes) | Keep; add extract exclusion | Auditor POST /extract → 403 |
| T7 | Admin grants Executive Management | Role table | Insider admin | PATCH /users | Authenticated admin | Privilege escalation | super_admin-only guard (:614) | Keep; audit event | Admin sets super_admin → 403 + audit |
| T8 | Remove final Executive user | Org governance | Insider super_admin | DELETE /users | Two+ super_admins or self | Orphaned/unadministrable org | Self-removal block only | Last-super_admin guard | Remove last super_admin → 409 |
| T9 | IDOR on resources | sites/readings/sludge/requests/reports/users | Any tenant | id/name in path | Authenticated | Access foreign objects | Org filter (weak under T1) | Membership+scope check per object | Foreign id → 404 (no existence leak) |
| T10 | Mass assignment | role/scope/cost/status | Any user | Mutation bodies | Authenticated | Field tampering | Typed models, allow-listed role | Keep; extend to new models | Body with `role` on non-role endpoint ignored |
| T11 | Replay/forgery of approvals/stock | reports, inventory, actions | Insider | future mutation endpoints | Phases 4/5 exist | Fraudulent approval/stock | N/A (not built) | Idempotency keys; append-only ledger | Duplicate approval → single effect |
| T12 | Destructive delete w/o evidence | sites, readings | Insider admin | DELETE /sites | Authenticated admin | Irrecoverable loss | Cascade only | Soft-delete + retention + audit + confirm | Delete → recoverable + audit row |
| T13 | Financial/PII leakage | valuation, billing, personal | Lower roles | /billing/status, future KPIs | Authenticated | Sensitive disclosure | None (billing to all) | Scope financial to Manager+ | Operator GET /billing/status → 403 |
| T14 | Bypass via public/webhook/upload/sim | compute, data | External | /assess,/science/*,/extract,/webhook | Endpoint reachable | Unmetered cost / abuse | Signature on webhook; optional key | Per-tenant auth+meter | Anon /science/simulate → 401 |
| T15 | Race conditions | stock, report approval, last user | Concurrent insider | future endpoints | Phases 4/5 | Inconsistent balances / double effect | N/A | Transactional ledger + locks | Concurrent consume → no negative stock |
| T16 | Audit-log tampering/omission | audit trail | Insider | mutations | — | No forensic evidence | None (no audit at all) | Append-only, REVOKE update/delete | Mutation → immutable audit row |

**Prioritized risk register:** CRIT-1 (T1/T2) → CRIT-2 (T3) → CRIT-3 (T12/regulatory) → CRIT-4 (secrets) → H (T4/T5 scope, site auto-create, migrations, tests) → M (T7/T8/T13/T16) → L (T14 metering, CORS).

---

## 4. Proposed database / entity changes

New tables (DDL sketches; **not created**). All denormalize `organization_id` so each scope filter needs one predicate and any future RLS scopes in one hop. Full sketches in `PERMISSIONS_REVIEW_DISCOVERY.md` §4.

- **`user_site_assignments`** (user_id, site_id, organization_id; PK(user_id,site_id); idx site_id, (organization_id,user_id)) — Phase 2.
- **`projects`** + **`user_project_assignments`**; `ALTER sites ADD project_id` — Phase 2.
- **`business_units`** (self-referential `parent_id` tree, organization-scoped) — Phase 2.
- **`corrective_actions`** + append-only **`corrective_action_events`** (REVOKE update/delete) — Phase 4.
- **Inventory:** `inventory_locations`, `inventory_items`, `inventory_batches`, append-only **`inventory_ledger`** (balances = SUM(qty_delta); transfers = paired rows via `transfer_group`; corrections = compensating `adjust` rows; REVOKE update/delete) — Phase 5.
- **`assets`** + **`maintenance_schedules`** — Phase 6.
- **`audit_events`** (append-only, REVOKE update/delete, service-role write only) — Phase 1.

Existing-schema fixes:
- Denormalize `organization_id` onto `readings`/`predictions` (currently isolated only via `sites` join) — reduces the legacy-fallback leak surface.
- Add `user_profiles(organization_id)` index (currently seq-scanned by `get_user_organization()` and member listing).
- Add org-scoping RLS policies to `sludge_surveys`/`data_requests` (RLS-on, zero-policy today) *if* the JWT-client path is adopted.
- Remove the `site_limit=999, plan_name='dev'` backdoor (001_billing:12) before production.

---

## 5. Endpoint → atomic-permission map

(Full register in `PERMISSIONS_REVIEW_DISCOVERY_2.md` §1. Summary of the intended mapping.)

| Endpoint | Atomic permission | Scope check to add |
|---|---|---|
| GET /sites | `sites.read` | filter to assigned sites |
| POST /sites | `sites.create` | project scope + plan limit |
| DELETE /sites/{name} | `sites.delete` | org + soft-delete + audit |
| GET /users | `users.read` | org |
| PATCH /users/{id} | `users.role.assign` / `users.executive.assign` | org + target row + last-super_admin |
| DELETE /users/{id} | `users.remove` | org + last-super_admin |
| POST /users/invite | `users.invite` | org + role allow-list |
| GET /billing/status | `billing.read` | org; Manager+ only |
| POST /billing/{checkout,portal,cancel} | `billing.manage` | org |
| POST /log | `readings.create` / `readings.overwrite` | assigned site |
| GET /readings,/status/{site} | `readings.read` | assigned site |
| POST /assess | (assess) | authn + meter |
| GET /sludge/{site} | `sludge.read` | assigned site |
| POST /sludge/{site} | `sludge.write` | assigned site |
| DELETE /sludge/{site}/{zone} | `sludge.delete` | assigned site + audit; restrict to Manager+ (recommended) |
| GET/POST/DELETE /community/{site}/requests | `requests.read` / `requests.create` / `requests.fulfil` | assigned site |
| POST /extract | `readings.create` (upload) | authn; exclude auditor |
| GET /report/{site}?draft=true | `reports.generate_draft` | assigned/project scope |
| GET /report/{site}?draft=false | `reports.approve_final` | project scope + approval state |
| POST /science/diagnose,/simulate | `science.simulate` | authn + meter |
| GET /community/{site} (forecasts) | `science.read` | assigned site |

---

## 6. Role → permission bundle map

Bundles are **explicit** (never `tier >= N`). Note the tier inversion trap: `auditor` (GM) is display-tier 3 but has *fewer* write permissions than `admin` (tier 2).

| Permission | operator (Site Sup.) | admin (Proj/Contract Mgr) | auditor (Gen. Mgr) | super_admin (Exec) |
|---|:--:|:--:|:--:|:--:|
| sites.read | ✓ (assigned) | ✓ (project) | ✓ (portfolio) | ✓ (org) |
| sites.create / update / delete | — | ✓ | — | ✓ |
| readings.read | ✓ | ✓ | ✓ | ✓ |
| readings.create / overwrite | ✓ | ✓ | — | ✓ |
| reports.read | ✓ | ✓ | ✓ | ✓ |
| reports.generate_draft | ✓ | ✓ | — | ✓ |
| reports.approve_final | — | ✓ | ✓ (view) | ✓ |
| sludge.read | ✓ | ✓ | ✓ | ✓ |
| sludge.write | ✓ | ✓ | — | ✓ |
| sludge.delete | — (recommend) | ✓ | — | ✓ |
| requests.read / create / fulfil | ✓ | ✓ | read-only | ✓ |
| actions.read | ✓ | ✓ | ✓ | ✓ |
| actions.create / update | ✓ (assigned) | ✓ | — | ✓ |
| actions.close | — | ✓ | view | ✓ |
| inventory.read | ✓ | ✓ | ✓ | ✓ |
| inventory.consume | ✓ | ✓ | — | ✓ |
| inventory.receive/transfer/adjust/configure | — | ✓ | view | ✓ |
| inventory.valuation.read | — | — | ✓ | ✓ |
| assets.read | ✓ | ✓ | ✓ | ✓ |
| assets.configure | — | ✓ | — | ✓ |
| science.read | ✓ | ✓ | ✓ | ✓ |
| science.simulate | ✓ | ✓ | view | ✓ |
| analytics.site.read | ✓ | ✓ | ✓ | ✓ |
| analytics.project.read | — | ✓ | ✓ | ✓ |
| analytics.portfolio.read | — | — | ✓ | ✓ |
| analytics.executive.read | — | — | — | ✓ |
| users.read / invite / role.assign / remove | — | ✓ | — | ✓ |
| users.executive.assign | — | — | — | ✓ |
| billing.read | — | ✓ | — | ✓ |
| billing.manage | — | ✓ | — | ✓ |
| organization.configure | — | — | view | ✓ |
| audit.read | — | ✓ | ✓ | ✓ |
| permissions.configure | — | — | — | ✓ |

---

## 7. Scope-resolution algorithm (pseudocode)

```
authorize(request, permission_key):
    profile = verify_clerk_jwt(request.bearer)         # NO token => 401 (fail closed)
    if profile is None: raise 401
    if profile.status == "pending" or profile.org is None: raise 403

    org = profile.organization_id                      # from DB profile, NEVER from header
    if permission_key not in bundle_for(profile.role): raise 403

    scope = effective_scope(profile)                   # precomputed sets
    return (profile, org, scope)

effective_scope(profile):
    match profile.role:
      operator    -> { sites: assigned_sites(profile.user_id) }
      admin       -> { projects: assigned_projects(profile.user_id),
                       sites: sites_of(assigned_projects) }
      auditor     -> { business_units: portfolio(profile.user_id),
                       read_only: true }               # scope wide, writes denied by bundle
      super_admin -> { org_wide: true }

require_resource(permission, resource, profile, org, scope):
    r = load_resource(resource.id, org)                # org-filtered load
    if r is None: raise 404                            # do not leak existence cross-scope
    if not in_scope(r, scope): raise 404               # same status as not-found
    # writes additionally check resource STATE (e.g. report must be draft to approve)
    if permission.is_write and not state_allows(r, permission): raise 409
    return r
```

Key rules: (a) org derives from the verified profile, never a header; (b) 404 (not 403) for out-of-scope objects so existence is not leaked; (c) permission and scope are separate checks; (d) writes also validate resource state.

---

## 8. Migration & backward-compatibility plan

- **Make migrations safe first (Phase 0):** wrap each in a transaction, add a companion `NNN_down.sql`, take a Supabase backup/snapshot before applying, and document apply/rollback in `SAAS_STACK_GOTCHAS.md`. Current process (manual, forward-only) is the biggest operational risk.
- **Additive, reversible steps:** new tables and nullable columns first; backfill; only later add NOT NULL / FK constraints once data is clean.
- **Assignments backfill:** on introducing `user_site_assignments`, backfill every existing user with their current de-facto org-wide access behind a flag, so enforcement can be turned on per-tenant without locking anyone out (avoids a breaking change at cutover).
- **Legacy `site_name` rows:** backfill `site_id`/`organization_id` onto `readings`/`predictions`, then remove the `site_name`-only fallback branches. Until backfilled, keep fallback behind an org-required guard.
- **Backward compat:** keep existing endpoint shapes; add enforcement behind flags; remove the `super_admin` auto-provision path with a migration that converts any accidentally-provisioned solo orgs to a reviewed state (manual list first).
- **Secrets:** rotate live Stripe + service-role keys out-of-band; this is not a schema migration but must precede any shared-environment work.

---

## 9. Test matrix

No tests exist today; this is greenfield. Add pytest (+httpx) for backend, vitest for frontend.

| Category | Representative cases |
|---|---|
| Characterization (Phase 0) | Pin current behavior: anon+header → operator; unknown user → super_admin; report draft/final; billing to all. So fixes are detectable. |
| Positive | Each role reaches its permitted endpoints for in-scope resources. |
| Negative (403) | auditor blocked from writes & /extract; operator blocked from /sites,/users,/billing,report-final. |
| Cross-tenant | org A cannot read/write org B sites/readings/sludge/requests/reports; **anon + foreign `X-Organization-Id` → 401** (CRIT-1 regression). |
| Cross-scope | operator on unassigned site → 404/403; admin on foreign project → 404/403 (after Phase 2). |
| IDOR | foreign id/name on /users, /report, /readings, /sludge, /community → 404 (no existence leak). |
| Mass-assignment | body carrying role/scope/cost/status on non-authorizing endpoint is ignored. |
| Provisioning | unknown Clerk user → pending (not super_admin); invite email case-insensitive link. |
| Governance | cannot remove/demote last super_admin → 409; self-role-change blocked. |
| Concurrency (Phases 4/5) | parallel stock consume never goes negative; double report-approval → single effect; concurrent last-user removal → one blocked. |
| Regression | full suite green before any legacy role check is removed (Phase 8). |
| Audit | every sensitive mutation writes exactly one immutable `audit_events` row. |

---

## 10. Observability, audit, rollout & rollback plan

- **Audit:** append-only `audit_events`, written on auth failures and every sensitive mutation (role change, user removal, invite, site/sludge/request delete, report finalization, billing change, stock adjust). REVOKE update/delete; service-role writes only. Expose via `audit.read` (Manager+).
- **Observability:** structured JSON logs (never log tokens/emails/secrets — current logs are clean, keep them that way), an authorization-denial counter, scope-anomaly alerts, and audit-event volume monitoring.
- **Rollout:** feature flags per enforcement area (there are none today). Order: internal admins → pilot tenant → all tenants. Dark-launch the fail-closed resolver and per-tenant scope enforcement behind flags.
- **Rollback:** every migration reversible with a tested `_down.sql`; keep legacy role checks in place (behind flags) until the new path is proven, then remove in Phase 8. Test migration rollback on a production-like copy before each cutover.

---

## 11. Open questions & assumptions requiring human decisions

1. **Clerk sign-up policy (blocks CRIT-2 severity):** Is the Clerk instance actually closed to public sign-up? If yes, CRIT-2 is High-not-Critical in practice; if no/unknown, it is actively exploitable. *Needs verification in the Clerk dashboard — not visible in-repo.*
2. **App-authz vs RLS:** Adopt the JWT-scoped Supabase client (activate RLS as defense-in-depth) *or* formally commit to app-layer-only and delete the misleading `token` params? Recommendation: app-layer as source of truth **and** activate RLS as a backstop for new tables.
3. **Sludge deletion role:** Matrix cell grants operator delete, but the least-privilege note recommends Manager+. Which governs?
4. **Auditor and final reports:** view-only vs able to export the final PDF (read) — confirm the exact `reports.approve_final` semantics for GM.
5. **Existing accidental super_admin orgs:** how to reconcile any tenants already created by the auto-provision path (audit list → manual review?).
6. **Billing visibility for auditor:** matrix shows GM `—` for billing; confirm GMs should not see subscription/usage at all.
7. **Site↔project↔business-unit cardinality:** does a site belong to exactly one project? one business unit? (drives FK vs join-table design in Phase 2).

---

## 12. Phase estimates (relative effort & dependency order)

Effort is relative (S/M/L/XL), not calendar. Dependencies are hard unless noted.

| Phase | Scope | Effort | Depends on |
|---|---|---|---|
| **0 — Baseline & safety net** | Characterization tests, endpoint→permission register, **rotate secrets**, safe/reversible migrations + backups, rollout flags. **Emergency: fail-closed resolver + report gate.** | **L** | — |
| **1 — Central authorization foundation** | Typed permission catalogue; central authz dependency/service; remove anon `operator` fallback; standardized 401/403/404; audit_events + emission; last-super_admin guard; email-case fix. | **L** | 0 |
| **2 — Assignment & scope enforcement** | Assignment tables (site/project/BU), FKs/indexes; scope in queries+mutations; site-selector/dashboards to effective scope; RLS decision. | **XL** | 1 |
| **3 — Existing-feature permission completion** | Apply explicit perms to uploads/extract, readings, sludge, requests, reporting (draft vs final), simulation, billing status, user mgmt; destructive-delete safeguards; FE/BE alignment; stop site auto-create. | **L** | 1 (2 for full scope) |
| **4 — Corrective-action workflow** | Records, assignment, transitions, evidence, closure approval, immutable history. | **L** | 2, 3 |
| **5 — Inventory & chemical control** | Items/batches/locations, append-only ledger, transactional balances, financial-field protection, alerts. | **XL** | 2, 3 |
| **6 — Asset & maintenance config** | Asset types, checklists, schedules, task generation. | **M** | 2, 3 |
| **7 — KPI & management views** | Site/project/portfolio/executive aggregations without scope/financial leakage; metric definitions. | **L** | 2, 5, 6 |
| **8 — Hardening & controlled rollout** | Pen-style authz tests, log review, migration rollback drills, flagged rollout, remove legacy checks, CORS tightening, cron run-lock. | **M** | all |

**Critical path:** 0 → 1 → 2 → (3,4,6) → 5 → 7 → 8. Phase 2 is the widest and gates most feature work; Phases 4/6 can run in parallel after 2/3.

---

## Decision log (format required by the review prompt)

| Decision | Evidence | Security rationale | Product/eng trade-off | Alternative considered | Recommendation | Human approval |
|---|---|---|---|---|---|---|
| Make auth resolver fail closed; org from profile only | api_server.py:343-349 | Closes CRIT-1 read+write cross-tenant IDOR | Some anon/legacy callers (agent_server, `_check_key` scripts) may break → audit callers | Keep resolver, add per-endpoint gates | **Adopt** — single highest-leverage fix | **Required** |
| Invite-only provisioning; default pending | api_server.py:329-341 | Closes CRIT-2 privilege escalation | New-user onboarding needs an explicit invite step | Keep auto-provision, verify Clerk closed sign-up | **Adopt**, plus verify Clerk policy | **Required** |
| Split `reports.generate_draft` vs `reports.approve_final` | api_server.py:1357-1396 | Regulatory integrity (CRIT-3) | Adds an approval state/step to reporting | Watermark-only distinction (current) | **Adopt** | **Required** |
| Rotate live Stripe + service-role keys; `sk_test_` locally | secrets.toml:3,12,13 | Limits blast radius of CRIT-4 exposure | Key rotation coordination | Leave as-is (not committed) | **Adopt** | **Required** |
| App-layer authz as source of truth + RLS backstop on new tables | schema_rls.sql; queries.py 18 call sites | Defense-in-depth; removes misleading dead `token` | Two enforcement layers to keep consistent | App-only (delete token params) | **Recommend**, pending Q2 | **Required** |
| Centralize into permission dependency over atomic catalogue | api_server.py ~15 inline checks | Prevents silent per-endpoint omissions | Refactor risk; needs regression tests | Keep inline checks | **Adopt** in Phase 1 | Advisory |
| Restrict sludge.delete to Manager+ | MATRIX:43 vs cell | Least privilege on destructive op | Contradicts matrix cell (operator=A) | Honor matrix cell (operator delete) | **Escalate** (Q3) | **Required** |

---

*Prepared for human sign-off. No implementation will begin until the sign-off table in `PERMISSIONS_IMPLEMENTATION_REVIEW_PROMPT.md` is completed and Phase 0 scope is approved.*
