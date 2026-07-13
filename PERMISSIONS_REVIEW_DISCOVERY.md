# WOMS Permissions — Discovery Findings (work in progress)

> Status: **partial**. Read-only discovery per `PERMISSIONS_IMPLEMENTATION_REVIEW_PROMPT.md`.
> No implementation performed. Baseline `0.5.0` / commit `0b496a2`.
> Session rate-limited mid-run (reset 5:50pm Africa/Johannesburg); Agents A/C/D to be resumed.

## Agent status
- **B — Data model & DB:** COMPLETE (below).
- **C — Frontend authorization UX:** COMPLETE (below).
- **A — Backend authorization:** COMPLETE (below).
- **D — Identity / secrets / tests / ops:** COMPLETE (below).

## CONFIRMED Critical findings (corroborated by two independent agents)
- **CRIT-1 — Anonymous `operator` fallback + client-supplied org = cross-tenant IDOR (read & write).** `get_current_user_profile` returns `role="operator"`, `organization_id = X-Organization-Id header` for any tokenless request (`api_server.py:343-349`). Service-role DB client bypasses RLS, so the only tenant boundary is the Python `org_id` filter — which is attacker-controlled here. Confirmed by Agent A (C1) and Agent D (A2).
- **CRIT-2 — Uninvited authenticated users auto-provision as `super_admin`.** `_create_super_admin_profile` grants super_admin + fresh org to any signed-in user with no profile (`api_server.py:329-341`, `:255-276`). Safe only if Clerk instance truly blocks open sign-up — an unverified external assumption. Confirmed by Agent A (H1) and Agent D (A1).
- **CRIT-3 — Final regulatory report has no authz and no draft/approval separation.** `GET /report/{site}?draft=false` yields the watermark-free official PDF with no role check and no API key (`api_server.py:1357-1396`). Confirmed by Agent A (C2) and Agent C (frontend HIGH).
- **CRIT-4 — LIVE Stripe secret key + Supabase service-role key sit unencrypted on disk** (`.streamlit/secrets.toml:3,12,13`, `setup_bundle.md:13,20,21`). NOT git-committed (`.gitignore` covers them), but present on this workstation. Recommend rotation + `sk_test_` locally. Agent D (B1/B2).

---

# Agent B — DATABASE & DATA MODEL (COMPLETE)

Repo: `E:\DECCA-lagoons-dashboard\db\` · Baseline `0.5.0` / `0b496a2` · No files modified, no DB contacted.

## 1. Current Schema Inventory

### Tables that physically exist in DDL

| Table | Defined in | PK | Tenant column | Key FKs | Uniqueness | Indexes |
|---|---|---|---|---|---|---|
| `organizations` | schema.sql:5 | `id UUID` | **is the tenant** | — | `name` unique (schema.sql:7) | PK only |
| `sites` | schema.sql:12 | `id UUID` | **`organization_id`** (NOT NULL, FK→orgs, CASCADE) schema.sql:14 | organizations | `(organization_id, name)` schema.sql:19 | PK, unique idx only — **no standalone `organization_id` index** |
| `readings` | *ALTERed only* (schema.sql:23) | `id bigserial` (inferred, queries.py:5) | **NO** — has `site_id` (nullable, added via ALTER) + legacy `site_name` | `site_id`→sites CASCADE | `(site_id, year, month)` schema.sql:37 | **no index on `site_id`** |
| `predictions` | *ALTERed only* (schema.sql:42) | inferred | **NO** — `site_id` (nullable) + legacy `site_name` | `site_id`→sites CASCADE | `(site_id, year, month, parameter)` schema.sql:51 | **no index on `site_id`** |
| `user_profiles` | schema_rls.sql:5 | `id UUID` | **`organization_id`** (nullable, FK→orgs, SET NULL) schema_rls.sql:7 | orgs; `auth.users` FK later dropped (002_clerk:6) | `clerk_id` unique (002_clerk:9) | PK only |
| `sludge_surveys` | 003:5 | `id UUID` | **NO** — `site_id` only (NOT NULL, CASCADE) 003:7 | sites | `(site_id, zone_name)` 003:13 | `sludge_surveys_site_id_idx` 003:16 |
| `data_requests` | 005:6 | `id UUID` | **NO** — `site_id` only (NOT NULL, CASCADE) 005:8 | sites | none | `data_requests_site_id_idx` 005:15 |

**Important structural findings:**
- `readings` and `predictions` are **never `CREATE`d** in this repo — schema.sql only `ALTER`s them (schema.sql:23, 42). Base DDL assumed pre-existing in Supabase (documented only as a docstring, queries.py:3-24). Inferred: bigserial PK, legacy `site_name` column still present.
- Tenant isolation for `readings`/`predictions`/`sludge_surveys`/`data_requests` is **indirect** — one hop through `sites.organization_id`. No `organization_id` denormalized onto these tables, so every scoped query must join/subquery through `sites`.
- `readings.site_id` and `predictions.site_id` are **nullable** and coexist with legacy `site_name`. Dual-path code uses `site_name` when `site_id` is absent — an unscoped fallback.

### Billing columns on `organizations` (001_billing, 002_payment_provider)
`site_limit`, `plan_name`, `stripe_customer_id`, `stripe_subscription_id`, `payment_provider`, `payment_customer_id`, `payment_subscription_id`, `payment_source_id`, `subscription_status`, `next_billing_at`. Note 001_billing:12 sets every existing org to `site_limit=999, plan_name='dev'` — a dev backdoor the migration comment flags for removal before production.

## 2. RLS Analysis

**Policies defined (schema_rls.sql):** RLS enabled on `organizations`, `sites`, `readings`, `predictions`, `user_profiles`. Each has SELECT + `FOR ALL` mutate policies keyed on `public.get_user_organization()` (reads `organization_id` from `user_profiles WHERE id = auth.uid()`) with a `super_admin` global-read escape hatch (schema_rls.sql:67, 80, 94, 109). Policies are **well-formed and correctly org-scoped in isolation.**

**But bypassed in practice — three compounding reasons:**

1. **Service-role key bypasses RLS entirely.** `db/client.py` builds the client from `cfg["key"]` (client.py:65, 72). Migration comments confirm this is the **service_role** key: 003:19-24, 005:17-20, queries.py:325, 349. Postgres `service_role` is `BYPASSRLS` — **every policy above is inert for backend traffic.**
2. **The JWT path is never exercised.** `get_client(token)` *can* build a request-scoped anon client with the user JWT (client.py:62-67) — which would activate RLS. But **all 18 call sites in queries.py call `get_client()` with no token** (lines 61,83,108,134,164,208,233,274,299,327,350,387,448,468,496,518,542,561). The `token` parameter is threaded through every helper then dropped. RLS user-scoping is **dead code.**
3. **`sludge_surveys` / `data_requests` have RLS enabled with zero policies** (003:20, 005:19) → only service_role (bypass) can touch them. No org-scoping policy exists; isolation depends 100% on app-layer `site_id` filtering.

**Contradiction summary:** the app's real authorization boundary is **100% app-layer** (the `organization_id` filters in queries.py), not RLS. RLS is switched off by the service-role connection. Any missing/incorrect app-layer filter is an unmitigated cross-tenant leak (matrix PERMISSIONS_MATRIX.md:137 requires org isolation on every persisted query — currently only Python enforces it).

## 3. Query-Helper Isolation Audit (`db/queries.py`)

Legend: ✅ org-filtered · ⚠️ trusts caller-supplied id · ❌ can return/act cross-tenant.

| Function | Line | Org-scoped? | Finding |
|---|---|---|---|
| `get_or_create_site_id` | 59 | ⚠️ | Filters `organization_id` only because caller passes it (queries.py:69). Returns `None` if `organization_id` falsy (62) → forces unscoped `site_name` fallback. **Auto-creates a site on any miss** (73) — read helper with a write side-effect; wrong/missing name silently mints rows. |
| `get_readings_for_site` | 81 | ❌ | If `site_id` resolves, scoped. Else **`.eq("site_name", site_name)` with NO org filter** (91) → readings for *any* tenant sharing that name. Triggered whenever `organization_id` is None. |
| `get_site_names` | 100 | ✅/⚠️ | Scoped when `organization_id` passed (111); else reads from Streamlit secrets / `LAGOON_SITES` env (119-129) — unscoped config source. |
| `reading_exists` | 132 | ❌ | Unscoped `site_name` branch (142). |
| `insert_reading` | 151 | ⚠️/❌ | Writes `site_name` always; `site_id` only if resolvable (170-171). With no `organization_id`, row bound only to `site_name`; `upsert` conflict key `site_name,year,month` (175) lets one tenant overwrite another's same-named site reading. |
| `insert_prediction` | 203 | ⚠️/❌ | Same `site_name`-fallback write (222). |
| `validate_open_predictions` | 230 | ❌ | Unscoped `site_name` branch (243-245). |
| `get_validated_predictions` | 271 | ❌ | **When `site_name` is None (default), returns EVERY validated prediction across ALL tenants** (278). Cross-tenant read. |
| `create_organization` | 292 | n/a | Provisioning. |
| `create_site` | 322 | ⚠️ | Inserts with caller-supplied `organization_id` (331). Comment (325-326) states it **trusts the API layer** to have validated org from JWT — no DB-side check. |
| `delete_site` | 344 | ❌ **high-risk** | If `organization_id` None, selects site **by name only across all orgs** (354-357) and deletes it. Worse, 369 unconditionally `DELETE FROM readings WHERE site_name=<name>` — **deletes legacy readings for that name in every tenant**, even when an org filter was supplied for the site lookup. Destructive cross-tenant blast radius. |
| `get_site_reading_count` | 385 | ❌ | Unscoped `site_name` branch (395). |
| `get_sludge_zones` | 444 | ✅ | Requires resolved `site_id`; [] if none (453). Safe *provided* `get_or_create_site_id` was org-scoped. |
| `upsert_sludge_zone` | 462 | ✅ | Requires `site_id` (471-473). |
| `delete_sludge_zone` | 493 | ✅ | Requires `site_id` (499). |
| `create_data_request` | 514 | ✅ | Requires `site_id` (521). |
| `get_open_data_requests` | 539 | ✅ | Requires `site_id` (546). |
| `dismiss_data_request` | 557 | ✅ | Double-filters `.eq("id",…).eq("site_id",…)` (569) — good pattern. |

**Root cause:** the readings/predictions helpers all carry a `site_name`-only fallback for pre-multitenancy legacy rows. That fallback is the cross-tenant hole. Newer tables (sludge, data_requests) drop the fallback and are consistently `site_id`-gated — but their org-scoping is only as strong as `get_or_create_site_id` being handed a correct `organization_id`, which is unverified caller trust.

## 4. Missing Models (required by matrix, absent from schema)

None exist in any DDL. DDL sketches are **proposals only — do not create.** All assume denormalizing `organization_id` onto each table so app filters and any future RLS scope in one hop.

**a. User→Site assignment** (matrix rows 34-36, priority gap #1)
```sql
user_site_assignments(
  user_id TEXT REFERENCES user_profiles(clerk_id) ON DELETE CASCADE,
  site_id UUID REFERENCES sites(id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES organizations(id),
  assigned_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (user_id, site_id));
CREATE INDEX ON user_site_assignments(site_id);
CREATE INDEX ON user_site_assignments(organization_id, user_id);
```

**b. User→Project/Contract assignment + Projects** (matrix row 63, scope dim line 139)
```sql
projects(id UUID PK, organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  business_unit_id UUID REFERENCES business_units(id), name TEXT NOT NULL, contract_ref TEXT,
  UNIQUE(organization_id, name));
-- sites gains: ALTER sites ADD project_id UUID REFERENCES projects(id);
user_project_assignments(user_id TEXT, project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  organization_id UUID NOT NULL, role_in_project TEXT, PRIMARY KEY(user_id, project_id));
CREATE INDEX ON projects(organization_id);
CREATE INDEX ON user_project_assignments(project_id);
```

**c. Business-unit hierarchy** (matrix row 75, scope dim line 138)
```sql
business_units(id UUID PK, organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  parent_id UUID REFERENCES business_units(id) ON DELETE SET NULL,
  name TEXT NOT NULL, UNIQUE(organization_id, name));
CREATE INDEX ON business_units(organization_id);
CREATE INDEX ON business_units(parent_id);
```

**d. Corrective-action workflow** (matrix rows 51-53)
```sql
corrective_actions(id UUID PK, organization_id UUID NOT NULL, site_id UUID REFERENCES sites(id),
  asset_id UUID REFERENCES assets(id), title TEXT NOT NULL, description TEXT,
  owner_user_id TEXT, status TEXT NOT NULL DEFAULT 'open'
    CHECK(status IN ('open','in_progress','pending_approval','closed','cancelled')),
  severity TEXT, due_date DATE, created_by TEXT, created_at TIMESTAMPTZ DEFAULT now(),
  closed_by TEXT, closed_at TIMESTAMPTZ);
corrective_action_events(  -- append-only, immutable
  id BIGSERIAL PK, action_id UUID NOT NULL REFERENCES corrective_actions(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL, actor_user_id TEXT, payload JSONB, evidence_url TEXT,
  created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX ON corrective_actions(organization_id, status);
CREATE INDEX ON corrective_actions(site_id);
CREATE INDEX ON corrective_action_events(action_id, created_at);
-- immutability: REVOKE UPDATE/DELETE on corrective_action_events from all app roles.
```

**e. Inventory** (matrix rows 54-61; append-only ledger) — largest gap:
```sql
inventory_locations(id UUID PK, organization_id UUID NOT NULL REFERENCES organizations(id),
  site_id UUID REFERENCES sites(id), kind TEXT CHECK(kind IN ('warehouse','vehicle','site_store')),
  name TEXT NOT NULL, UNIQUE(organization_id, name));
inventory_items(id UUID PK, organization_id UUID NOT NULL, sku TEXT, name TEXT NOT NULL,
  unit TEXT, reorder_threshold NUMERIC, unit_cost NUMERIC, UNIQUE(organization_id, sku));
inventory_batches(id UUID PK, item_id UUID NOT NULL REFERENCES inventory_items(id),
  organization_id UUID NOT NULL, batch_number TEXT, expiry_date DATE, received_cost NUMERIC,
  UNIQUE(item_id, batch_number));
inventory_ledger(  -- APPEND-ONLY; balances are SUM(qty_delta), never stored mutable
  id BIGSERIAL PK, organization_id UUID NOT NULL, item_id UUID NOT NULL REFERENCES inventory_items(id),
  batch_id UUID REFERENCES inventory_batches(id), location_id UUID NOT NULL REFERENCES inventory_locations(id),
  txn_type TEXT NOT NULL CHECK(txn_type IN ('receive','consume','transfer_in','transfer_out','adjust')),
  qty_delta NUMERIC NOT NULL, reason TEXT, ref_site_id UUID, ref_asset_id UUID, ref_action_id UUID,
  transfer_group UUID, actor_user_id TEXT, created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX ON inventory_ledger(organization_id, item_id, location_id);
CREATE INDEX ON inventory_ledger(batch_id);
CREATE INDEX ON inventory_batches(expiry_date);
-- immutability: REVOKE UPDATE/DELETE on inventory_ledger; corrections are compensating 'adjust' rows.
```

**f. Asset / maintenance config** (matrix row 50)
```sql
assets(id UUID PK, organization_id UUID NOT NULL, site_id UUID REFERENCES sites(id) ON DELETE CASCADE,
  asset_type TEXT, name TEXT NOT NULL, config JSONB, UNIQUE(site_id, name));
maintenance_schedules(id UUID PK, organization_id UUID NOT NULL, asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  checklist JSONB, interval_days INT, next_due DATE);
CREATE INDEX ON assets(organization_id, site_id);
CREATE INDEX ON maintenance_schedules(asset_id);
CREATE INDEX ON maintenance_schedules(next_due);
```

**g. Audit log** (matrix row 76; immutable)
```sql
audit_events(  -- append-only, immutable
  id BIGSERIAL PK, organization_id UUID NOT NULL, actor_user_id TEXT, actor_role TEXT,
  action TEXT NOT NULL, target_type TEXT, target_id TEXT, payload JSONB, ip TEXT,
  created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX ON audit_events(organization_id, created_at DESC);
CREATE INDEX ON audit_events(target_type, target_id);
-- immutability: REVOKE UPDATE/DELETE from all app roles; service-role writes only.
```

## 5. Missing Indexes for Scope-Filtered Queries
- **`readings(site_name)`** — queried in every fallback branch (91,142,369,395) and the global delete; **no index** → seq scans (composite `(site_id,year,month)` covers the `site_id` prefix, so bare `site_id` index not strictly needed).
- **`predictions(site_name)`** — fallback (244,284) unindexed.
- **`sites(organization_id)`** — covered by `(organization_id, name)` prefix (adequate while composite exists).
- **`user_profiles(organization_id)`** — only `clerk_id` indexed; `get_user_organization()` and member listing do **seq scans**. Add index.

## Cross-cutting recommendations (not implemented)
1. Kill the `site_name`-only fallbacks (91,142,244,354-357,369,395) or hard-require `organization_id` — concrete cross-tenant read/write/delete leaks; RLS will not backstop them (service-role).
2. Either pass `token` into `get_client(token)` at all 18 call sites to activate RLS, or drop the `token` params so code stops implying an isolation guarantee it doesn't provide.
3. Add org-scoping RLS policies to `sludge_surveys` and `data_requests` (RLS-on/zero-policy, 003:20 / 005:19) before any non-service-role access.
4. Remove the `site_limit=999 / plan_name='dev'` production backdoor (001_billing:12).
5. Denormalize `organization_id` onto `readings`/`predictions` (and all new tables).

*Inferred:* `readings`/`predictions` base DDL and PK types reconstructed from queries.py:3-24 docstring + ALTERs; `cfg["key"]` as service_role evidenced by migration comments 003:19, 005:17 and queries.py:325,349 (not by reading secrets).

---

# Agent C — FRONTEND ROLE/PERMISSION (COMPLETE)

Scope: `frontend/src`. Backend is authoritative per `PERMISSIONS_MATRIX.md:17`. Backend-enforcement column reflects the matrix's delivery notes, not independent backend code review (see Agent A for that).

## 1. Role model
**Definition** — `frontend/src/lib/roles.ts`
- Four DB roles, `Role = 'operator' | 'admin' | 'auditor' | 'super_admin'` (roles.ts:16), each mapped in `ROLE_META` to a business label, `tier` (1–4), icon, badge, `dashboardTier` (roles.ts:35-68).
- Tier ordering: operator=1, admin=2, **auditor=3**, super_admin=4 (roles.ts:39,48,56,64). **Inversion trap:** auditor (General Manager) is tier 3, above admin's tier 2, yet the matrix grants auditor *fewer* write permissions than admin. Tier is a display/altitude concept, NOT a privilege ordering.
- `roleMeta()` fails safe: unknown/empty role → operator (lowest privilege) (roles.ts:70-76).
- `tier`/`dashboardTier` used ONLY for exact-match dashboard selection (App.tsx:129-133), never `tier >= N` authorization. No tier-comparison gate exists (grep-verified). Good — but ordering is latent; a future `tier >= N` write-gate would wrongly grant auditor > admin.

**Role resolution** — `frontend/src/context/AuthContext.tsx`
- Role NOT read from Clerk claims directly. `AuthProvider` gets Clerk token, fetches `/api/profile` with Bearer + `X-User-Email`, sets `role` from backend response (AuthContext.tsx:54-68).
- Defaults to `operator` before load and on any failure (AuthContext.tsx:25,63) — fail-closed (good). Exposed via `useAuth()` (AuthContext.tsx:116).

## 2. Frontend gating register

| UI element | How gated (frontend) | Matrix permission | file:line | Backend check? |
|---|---|---|---|---|
| Nav: Upload Lab Report | `roles:['super_admin','admin','operator']` filter (hides auditor) | Upload/extract (A/A/—/A) | Sidebar.tsx:50,261 | Yes — allow-list (MATRIX:39) |
| Upload submit action | `if (role==='auditor') return` | same | UploadReport.tsx:187 | Yes (MATRIX:41) |
| Sludge add/update/delete | `canEdit = role in {operator,admin,super_admin}` | Sludge write/delete (A/A/—/A) | Sludge.tsx:64,180,194,248 | Yes; assigned-site validation missing (MATRIX:42-43) |
| Community lab/data request | `canRequest = role in {operator,admin,super_admin}` | Raise/fulfil requests (A/A/—/A) | Community.tsx:47 | Partial (MATRIX:45) |
| Compliance "Export Official Report" (final) | **No gate** — all roles | Export final report (—/A/V/A) | ComplianceReport.tsx:146,156 | **No** (Gap, MATRIX:47) |
| Compliance "Preview Draft" | No gate (all roles) | Generate/view reports (V/V/V/V) | ComplianceReport.tsx:159 | Partial (MATRIX:46) |
| Digital Twin "Simulate Intervention" | **No gate** (all incl auditor) | Run simulations (A/A/V/A) | ScienceSimulation.tsx:57,134 | **No explicit role policy** (MATRIX:66) |
| Site Manager: Add/Delete site + form | `isAdmin = role in {admin,super_admin}` | Create/Delete site (—/M/—/M) | SiteManager.tsx:36,179,191,284 | Yes (MATRIX:48-49) |
| Site Manager access (read/list) | Reachable by all roles via "+ Manage" | View site list (V/V/V/V) | Sidebar.tsx:179; SiteManager.tsx | Yes (read allowed all) |
| Settings → Billing panel | `isAdmin` conditional render | View subscription (—/V/—/V) | Settings.tsx:342,349 | **Mismatch** — backend returns billing to every role (MATRIX:73) |
| Billing checkout/portal/cancel | Rendered only inside admin-gated panel | Manage subscription (—/M/—/M) | Settings.tsx:83,103,119,354 | Yes (MATRIX:74) |
| Settings → Site/User Mgmt embeds | `isAdmin` conditional render | Users/sites admin (—/M/—/M) | Settings.tsx:380,388 | Yes (MATRIX:67-72) |
| User Manager: fetch/invite/role/remove | `isAdmin` gates render+fetch; `isSuperAdmin` gates super_admin rows | Invite/assign/remove; grant Exec | UserManager.tsx:75-76,100,166-168,271,285 | Yes (MATRIX:67-72) |
| Site selector dropdown | Lists **all** org sites, no assignment filter | View *assigned* site list | Sidebar.tsx:106-117,213-247 | No site-assignment scoping (MATRIX:34) |
| Dashboard tier landing | `dashboardTier` exact match | View role-specific dashboard | App.tsx:129-133 | n/a (view only) |

## 3. Findings

### HIGH
- **Final regulatory report export has no gate, frontend or backend.** `ComplianceReport.tsx:156` renders "Export Official Report" (`downloadPdf(false)`, :70-91) for every role. Matrix requires operator=— and auditor=view-only (MATRIX:47), flags backend approval/sign-off as a Gap. Any operator or read-only auditor can pull the non-watermarked official PDF.
- **Digital-twin simulate is ungated end-to-end.** `ScienceSimulation.tsx:134` → `POST /api/science/simulate` (:57) has no role check; matrix marks auditor view-only and notes explicit role policy not enforced backend-side (MATRIX:66).

### MEDIUM
- **Billing visibility mismatch (verified frontend side).** `Settings.tsx:342` `isAdmin` gates panel render (:349), but `BillingPanel` calls `/api/billing/status` with only bearer/org header — no role parameter (Settings.tsx:74-78). Hide is pure conditional rendering; backend returns billing status to every authenticated role (MATRIX:73). Operator/auditor can retrieve subscription/usage by calling the endpoint directly.
- **Site selector shows all org sites regardless of assignment.** `Sidebar.tsx:106-117` fetches `/api/sites` with only `X-Organization-ID`; `SiteManager.tsx:49-60` identical. No user-to-site scoping (MATRIX:34).
- **Hard-coded role-name checks instead of atomic permissions.** Write-capability set re-expressed as literal role arrays in ≥4 places: Sidebar.tsx:50, Sludge.tsx:64, Community.tsx:47, inverted `role==='auditor'` in UploadReport.tsx:187; plus `isAdmin` duplicated in Settings.tsx:342, SiteManager.tsx:36, UserManager.tsx:75. No `hasPermission(key)` helper. Structural blocker to the atomic-permission model (MATRIX:79-129).

### LOW
- **Operator can delete sludge zones.** `canEdit` includes operator (Sludge.tsx:64), gates delete button (:248). Matches matrix cells (A/A/—/A) but contradicts least-privilege note (MATRIX:43). FE faithfully implements the permissive row.
- **Site Manager read view reachable by all roles**, via "+ Manage" (Sidebar.tsx:179), ungated `sitemanager` tab (App.tsx:149). Writes are `isAdmin`-gated inside (SiteManager.tsx:179,284); non-admin notice shows (:161). View-only exposure, informational.

### Positive notes
- Role resolves from backend `/api/profile`, not client-mutable Clerk metadata (AuthContext.tsx:57); defaults to lowest privilege on failure (:25,63).
- Upload has defense-in-depth (nav filter + submit guard).
- Self-privilege-escalation guarded in UI: cannot edit own role, non-super-admin cannot touch super_admin rows (UserManager.tsx:271,285).
