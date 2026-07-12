# WOMS Permissions — Discovery Evidence, Part 2 (Agents A & D)

> Companion to `PERMISSIONS_REVIEW_DISCOVERY.md` (which holds Agents B & C).
> Read-only discovery. Baseline `0.5.0` / commit `0b496a2`. No implementation performed.

---

# Agent A — BACKEND AUTHORIZATION (COMPLETE)

Scope: `api_server.py`, `agent_server.py`, `billing.py`, `extract.py`, `reporting.py`, `db/queries.py`, `payments/*`, `science/*`.

## Architecture facts that drive every finding
- **`get_current_user_profile` is an identity RESOLVER, not a gate** (`api_server.py:304-349`). With no/invalid Bearer token it returns a non-error fallback: `{"user_id": None, "organization_id": <X-Organization-Id header>, "role": "operator", "token": None}` (:343-349). Any endpoint doing only `Depends(get_current_user_profile)` admits an unauthenticated caller with `operator` privileges scoped to any org id typed into `X-Organization-Id`.
- **DB uses the Supabase service-role client** (`db/queries.py:325,349`). RLS bypassed; the only tenant boundary is the Python `.eq("organization_id", org_id)` filter, and `org_id` on the fallback path is client-supplied.
- **`_check_key` is optional** (`api_server.py:63-69`); `API_KEY` is `sync:false` in `render.yaml:20-21`. Even when set, it guards only `/log`, `/assess`, `/readings`, `/status`, `/science/*` — NOT `/report`, `/sites`, `/sludge`, `/community`.
- **`get_or_create_site_id` auto-creates a site row on any read or write if the name is absent** (`db/queries.py:59-78`).
- **No audit/security events emitted anywhere.**

## 1. Endpoint register
Path prefix `/api` (inner app mounted `api_server.py:1433`). "Resolver only" = anonymous-operator reachable.

| Method + Path | Auth dependency | Role check | Org isolation | Resource scope | Proposed atomic perm | Evidence |
|---|---|---|---|---|---|---|
| GET /health | none | none | n/a | n/a | (public) | :439 |
| GET /version | none | none | n/a | n/a | (public) | :445 |
| GET /sites | resolver only | none (all roles) | yes (org from profile) | n/a | `sites.read` | :457-480 |
| POST /sites | resolver | inline `admin/super_admin` | yes | plan-limit only | `sites.create` | :483-487,497 |
| DELETE /sites/{site_name} | resolver | inline `admin/super_admin` | yes | no confirm/soft-delete/audit | `sites.delete` | :529-533; queries.py:344-382 |
| GET /profile | resolver | self only | self | self | (self) | :550 |
| GET /users | resolver | inline `admin/super_admin` | yes | org | `users.read` | :571-575 |
| PATCH /users/{user_id} | resolver | inline + super_admin-for-super_admin + self-block | yes | org, target row | `users.role.assign`/`users.executive.assign` | :607-629 |
| DELETE /users/{user_id} | resolver | inline + super_admin-for-super_admin + self-block | yes | org, target row | `users.remove` | :632-652 |
| POST /users/invite | resolver | inline + super_admin-for-super_admin | yes | org | `users.invite` | :717-731 |
| POST /access-request | none (public) | none | n/a | n/a | (public intake) | :810 |
| GET /billing/status | resolver only | none — all roles | yes | org | `billing.read` | :841-884 |
| POST /billing/checkout | resolver | inline `admin/super_admin` | yes | org | `billing.manage` | :887-891 |
| POST /billing/portal | resolver | inline `admin/super_admin` | yes | org | `billing.manage` | :912-917 |
| POST /billing/cancel | resolver | inline `admin/super_admin` | yes | org | `billing.manage` | :936-940 |
| POST /billing/webhook | provider signature | n/a | n/a | signature verified | (system) | :954-966; stripe_provider.py:186-191 |
| POST /assess | `_check_key` (optional) | none | n/a | n/a | assess | :969-970 |
| POST /log | `_check_key` + resolver | inline `admin/operator/super_admin` | yes | no assigned-site check; auto-creates site | `readings.create/overwrite` | :979-986 |
| GET /sludge/{site} | resolver only | none (all roles) | yes | site via org | `sludge.read` | :1029-1034 |
| POST /sludge/{site} | resolver | inline `operator/admin/super_admin` | yes | no assigned-site check | `sludge.write` | :1037-1041 |
| DELETE /sludge/{site}/{zone_name} | resolver | inline `operator/admin/super_admin` | yes | no assigned-site; no audit | `sludge.delete` | :1055-1059 |
| GET /readings/{site} | `_check_key` + resolver | none (all roles) | yes | site via org | `readings.read` | :1070-1076 |
| GET /community/{site} | resolver only | none | yes | site via org | `science.read` | :1104-1113 |
| GET /community/{site}/requests | resolver only | none | yes | site via org | `requests.read` | :1142-1147 |
| POST /community/{site}/requests | resolver | inline `operator/admin/super_admin` | yes | no assigned-site | `requests.create` | :1151-1156 |
| DELETE /community/{site}/requests/{request_id} | resolver | inline `operator/admin/super_admin` | yes (req scoped to site_id) | no assigned-site | `requests.fulfil` | :1167-1176; queries.py:557-574 |
| GET /status/{site} | `_check_key` + resolver | none (all roles) | yes | site via org | `readings.read` | :1182-1189 |
| GET /tools | none | none | n/a | n/a | (public) | :1212 |
| POST /science/diagnose | `_check_key` (optional) | none | n/a | n/a | `science.simulate` | :1285-1286 |
| POST /science/simulate | `_check_key` (optional) | none | n/a | n/a | `science.simulate` | :1298-1299 |
| POST /extract | resolver | gate: `user_id` present AND `role != "pending"` | n/a (no save) | auditor not excluded | `readings.create` (upload) | :1323-1336 |
| GET /report/{site} | resolver only | none; `draft` bool is the only control | yes | no role, no approval separation | `reports.generate_draft`/`reports.approve_final` | :1357-1396 |
| GET /science/interventions | none | none | n/a | n/a | (public) | :1399 |
| GET /{catchall} | none | none (static SPA) | n/a | n/a | (public) | :1455 |

`agent_server.py` = MCP/stdio tools. No auth model at all; its `insert_reading` passes no `organization_id` (:186). Out of HTTP scope but an unauthenticated write path if exposed.

## 2. Authorization defects
### CRITICAL
- **C1 — Anonymous `operator` fallback + client-supplied org = cross-tenant IDOR (read & write).** (:343-349). Cleanest vector: `GET /api/report/{site}` with spoofed `X-Organization-Id`, no bearer, returns the victim compliance PDF (:1357-1396). Same for `/sites`, `/sludge/{site}`, `/community/{site}`, `/community/{site}/requests`, `/billing/status`. Writes reachable too: `POST /log` (:985), `POST /sludge/{site}` (:1040), `POST /community/{site}/requests` (:1155), deletes — all allow operator (guarded only by optional `_check_key` on `/log`). Fix: resolver must raise 401 on no verified user; never trust `X-Organization-Id` for tenancy.
- **C2 — Final regulatory report has no authz + no draft/approval separation.** `GET /report/{site}?draft=false` (:1357-1363) yields the watermark-free official PDF, no role check, no `_check_key`. Matrix requires Manager/GM/Exec + sign-off (MATRIX:47). `draft` bool is client-controlled, not an authz boundary.

### HIGH
- **H1 — Uninvited authenticated users auto-provision as `super_admin`.** `_create_super_admin_profile` (:329-341, :255-276). Safe only if Clerk sign-up restricted at instance level (assumed, :330-333). Inferred — depends on Clerk config not in-repo.
- **H2 — No assigned-site scoping on operational writes.** `POST /log` (:985), `POST /sludge/{site}` (:1040), `POST /community/{site}/requests` (:1155), `DELETE /sludge/...` (:1058) authorize by role only; any operator writes any site in org. No user-to-site model. Matches MATRIX:41-45.
- **H3 — Plan site-limit bypass via auto-create on reads/writes.** `get_or_create_site_id` inserts a new site whenever name unknown (queries.py:59-78), called from read paths (`/status`,`/readings`,`/report`,`/community`,`/sludge` GET) and writes. `site_limit` enforced only in `POST /sites` (:497). Any authenticated user (incl operator) can create unlimited sites — and pollute another tenant list under C1 — via a GET.

### MEDIUM
- **M1 — `GET /billing/status` exposes subscription data to every role** (:841-884). Matrix: `billing.read` starts at Manager tier (MATRIX:73).
- **M2 — Fragile inline allow-lists duplicated across ~15 endpoints** (:486,532,574,610,635,726,890,916,939,985,1040,1058,1155,1171). One omission silently opens an endpoint (as in C2/M1). Centralize (MATRIX gap #2, :147).
- **M3 — Destructive deletes: no confirmation, soft-delete, or audit.** `DELETE /sites/{site_name}` cascade-deletes site + readings + predictions (:529-547; queries.py:344-382). Sludge/request deletes unlogged, allow operator.
- **M4 — No audit/security events on any sensitive mutation.** Role changes (:626), removal (:651), invites (:748), deletes, report finalization, billing (:900,949) emit nothing. No `audit_log` table anywhere.
- **M5 — `POST /extract` does not exclude `auditor`** (:1335). Matrix excludes auditor (MATRIX:39). `role=="pending"` branch is dead code (resolver never returns "pending").

### LOW
- **L1** — `/assess`, `/science/diagnose`, `/science/simulate` no user auth, only optional `_check_key` (:969-970,1285-1286,1298-1299). Compute unmetered per-tenant.
- **L2** — CORS `allow_origins=["*"]` on both apps (:54-59,1425-1430) + header-based org selection broadens attack surface.
- **L3** — Legacy `site_name`-only fallback drops org filter (queries.py:91) — latent cross-tenant read; reachable when org_id None.

## 3. Mass-assignment review — NO critical findings
Request bodies tightly typed (`UpdateRoleRequest` role-only validated against allow-list :563,612; `CreateSiteRequest`/`LogRequest`/`SludgeZoneRequest`/`DataRequestBody` domain fields only). No endpoint accepts arbitrary role/scope/cost/stock/status/approval from body. `update_org_billing(**fields)` (billing.py:122-132) called only from signature-verified webhook. Report status/approval not a persisted field (draft is a query flag) — itself the C2 gap.

## 4. Audit-event coverage — NONE. Single largest cross-cutting gap.

### Top fixes (priority order)
1. Make `get_current_user_profile` fail closed (401; never derive tenancy from `X-Organization-Id`). Resolves C1 + write half of H3/L3.
2. Add role + approval enforcement to `GET /report`; split draft vs `approve_final` (C2).
3. Add user-to-site assignment model, enforce on operational reads/writes (H2).
4. Stop auto-creating sites on read paths; keep creation + plan-limit in `POST /sites` only (H3).
5. Centralize authorization into one permission dependency; add immutable audit log (M2, M3, M4).

---

# Agent D — IDENTITY / SECRETS / TESTS / OPS (COMPLETE)

## A. Clerk identity to profile linking & provisioning
Flow: FE `AuthContext.tsx` gets Clerk JWT -> `GET /api/profile` (Bearer + `X-User-Email`) -> backend `get_current_user_profile` (:304-349) verifies JWT via Clerk JWKS (`get_user_from_token` :168-215), resolves internal profile.

- **CONFIRMED CRITICAL — new users auto-provisioned `super_admin`.** Valid token, no matching profile, no matching invite -> `_create_super_admin_profile` returns `role:"super_admin"` (:329-341). That fn inserts `user_profiles` row with `"role":"super_admin"` + new personal org (:255-276). Docstring claims safety via "self sign-up restricted at Clerk instance level" (:330-333) — unverified external assumption. MATRIX:39 says backend "blocks pending/anonymous" — code does the opposite.
- **CONFIRMED HIGH — no-token/anonymous fallback -> `operator`.** No token -> `{user_id:None, organization_id:<X-Organization-Id>, role:"operator", token:None}` (:343-349). Operator is in write allow-list for `POST/DELETE /sludge/{site}` (:1040,1058) and `POST/DELETE /community/{site}/requests` (:1155,1171); none re-check `user_id`. Unauthenticated caller + guessed org UUID = operator write/delete. `POST /extract` (:1335) is the ONLY endpoint that correctly rejects the anonymous dict (401) and documents that the resolver "is an identity resolver, not a gate."
- **Invite path (legit):** `POST /users/invite` (:717-764) admin creates Clerk invite + pending `user_profiles` row (`clerk_id=None`). First sign-in links pending row by email (`get_user_profile` :229-244). Invite lower-cases email (:738) but fallback lookup uses raw email (:318,234) -> case-mismatch could miss invite and fall through to super_admin auto-provision (:334). Inferred MEDIUM.
- **Self-escalation/last-super_admin:** self-role-change blocked (:624); self-removal blocked (:646); super_admin grant restricted to super_admin (:614-615,730-731); only super_admin removes super_admin (:649-650). All scoped by org (:626,651) — cross-tenant role edits prevented (good). **GAP: no "cannot remove/demote LAST super_admin" protection; no role-change/removal audit.** MEDIUM.

## B. Secrets & config hygiene
Real secrets on disk (values REDACTED):

| File:line | Variable | Type | Severity |
|---|---|---|---|
| `.streamlit/secrets.toml:3` | `[supabase] key` | Supabase service_role JWT (BYPASSRLS) | CRITICAL |
| `.streamlit/secrets.toml:12` | `[stripe] secret_key` | Stripe LIVE key (`sk_live_...`) | CRITICAL |
| `.streamlit/secrets.toml:13` | `[stripe] webhook_secret` | `whsec_...` | HIGH |
| `setup_bundle.md:13` | supabase key | duplicate service_role JWT | CRITICAL |
| `setup_bundle.md:20` | stripe secret_key | duplicate LIVE key | CRITICAL |
| `setup_bundle.md:21` | webhook_secret | duplicate `whsec_...` | HIGH |
| `promote_admin.py:22` | `SUPABASE_URL` default | hardcoded project URL | LOW |

**Mitigating (verified):** `git ls-files` shows only `.streamlit/secrets.toml.example` tracked. Real `secrets.toml` and `setup_bundle.md` NOT committed — `.gitignore` globs `.streamlit/secrets.toml*` (:3), `.env*`,`*.key`,`*.bak` (:4-8), `setup_bundle.md` (:18), `*.log` (:25). `secrets.toml.example` = placeholders only. **Log scan (all root .log files): NO leaked secrets/JWTs/Authorization headers/emails/PII** — uvicorn access lines only. `render.yaml` clean (`sync:false`). **Residual:** LIVE Stripe + service_role key unencrypted on dev box + `.md` bundle. Rotate + use `sk_test_` locally.

## C. Existing tests & coverage gaps
**CONFIRMED: effectively zero test infra.** No `pytest.ini`/`setup.cfg`/`tox.ini`/`pyproject.toml`/`conftest.py`; no `test_*.py`. `science/backtest.py` = domain backtester, not a unit test. FE: no vitest/jest config, no `*.test.tsx`. `requirements.txt` has no test dep. Missing categories (all absent): positive per-role; negative 403 (auditor writes; operator on /sites,/users,/billing); cross-tenant (directly relevant to anon `X-Organization-Id` bypass); cross-site/project scope; mass-assignment; IDOR (`/users/{id}`,`/report/{site}`,`/readings/{site}` foreign ids); concurrency (reading upsert, report-approval, last-super_admin removal); regression/characterization to pin current bad behavior.

## D. Ops / rollout readiness
- `render.yaml`: single web service (free plan), forward-only; clean secrets. No staging/canary, no health-gated deploy.
- `run_recurring_billing.py`: Checkout.com renewals, idempotent per run (:14), daily cron intent. No lock/mutex against overlapping runs, no dead-letter for repeated `past_due`. MEDIUM.
- Webhooks: `POST /billing/webhook` (:954-966) delegates sig verification to provider (`stripe_provider.py:76-77`); depends on `whsec_` set. Creation scripts read keys from env only.
- **Migrations: forward-only `.sql`, run MANUALLY in Supabase SQL editor (SAAS_STACK_GOTCHAS.md:153). No down/rollback, no transaction wrapping, no backup step.** HIGH for prod DB.
- **Feature flags/rollout gates: NONE** (grep 0 hits). Auto-provision change cannot be dark-launched/disabled without redeploy.
- **Audit-event pipeline: NONE** (grep 0 hits). Contradicts MATRIX gaps #5, `audit.read` (:76,128,150).
- Observability: uvicorn access logs only; no structured logging/error tracking/metrics.

## Severity summary (Agent D)
| # | Finding | Class |
|---|---|---|
| A1 | Unprovisioned users auto-granted `super_admin` (:329-341,255-276) | CRITICAL |
| A2 | No-token fallback -> operator, writable via `X-Organization-Id` (:343-349,1040,1058,1155,1171) | HIGH |
| B1 | LIVE Stripe + service_role keys unencrypted on disk (not committed) | CRITICAL (exposure) |
| B2 | Stripe `whsec_` on disk | HIGH |
| A3 | No last-super_admin protection; role/removal unaudited | MEDIUM |
| A4 | Invite email-case mismatch may bypass invite -> super_admin (inferred) | MEDIUM |
| C1 | No test infra; all authz test categories missing | HIGH (risk) |
| D1 | Forward-only manual migrations, no rollback/backup/txn | HIGH |
| D2 | No feature flags, no audit pipeline, minimal observability | MEDIUM |
