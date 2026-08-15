# Security review — compliance surface (obligations / modules / entitlements)

Reviewed 2026-08-15 against `main` @ `31fac1d`. Scope: `api_server.py` (obligations,
modules, entitlements), `core/authz.py`, `core/scope.py`, `core/entitlements.py`,
`core/obligations.py`, `core/audit.py`, `core/demo.py`, `db/queries.py`, `db/client.py`,
`db/guard.py`, `db/migrations/022`–`027`, `db/schema_rls.sql`, `PERMISSIONS_MATRIX.md`,
`DM_COMPLIANCE_SCOPING.md` §7.4/§7.5/§7.12.

Review only. No code was changed.

---

## Status — updated 2026-08-15, after the fixes

The findings below are left exactly as written, including the "Fix:" lines and
the recommended order. They are the record of the review as conducted; this
block records what happened to each afterwards. Where a fix departed from the
recommendation, the departure is named.

| | Finding | Status | Where |
|---|---|---|---|
| H1 | `DELETE /sites/{name}` destroys other tenants' readings | **Fixed** | `2e3ff09` |
| M3 | `POST /users/invite` confirms an email exists in another tenant | **Fixed** | `ca4376e` |
| M1 | Entitlement audit omits the fields that decide monitoring | **Fixed** | `ca4376e` |
| M2 | `first_due_on` is unbounded | **Fixed** | `ca4376e` |
| L2 | Unbounded `price_agreed` / `notes` return 500 | **Fixed** | `ca4376e` |
| L4 | Clerk token validation checks neither `iss` nor `azp` | **Fixed** | `ca4376e` |
| H2 | RLS `super_admin` is a cross-tenant hole | **Fixed, not yet applied** | migration `029` |
| L1 | Site-scope enforcement off by default | Open — a deliberate default | — |
| L3 | GET endpoints create sites, bypassing the plan limit | **Fixed** | `75642e8` |

**H2 needs an action that the others did not.** `029_rls_tenant_scope.sql` is a
hand-applied file. Until it is run in the Supabase SQL editor the holes are open
in the live project. Applying it changes no runtime behaviour today, because the
backend connects as `service_role` and bypasses RLS either way — which is why it
should be applied now rather than in a hurry later.

**Two corrections to this review, found while fixing it:**

1. **H2's blast radius was understated.** The review cites `022`, `023`, `027`
   and `schema_rls.sql`. The real count is **41 policies across 9 files**, also
   including `016`, `017`, `020`, `024` (18 on its own) and `028` — which was
   written the same day as this review. The pattern was still being copied into
   new migrations, so `tests/test_rls_tenant_scope.py` now fails the build on
   either defect shape, and `db/migrations/README.md` explains why.

2. **H2 is two findings, not one.** The 41 sites split exactly on whether the
   table has an `organization_id`. On tenant tables the clause is pure
   cross-tenant reach and was stripped. On the 9 global reference tables
   (`standards`, `laboratories`, `guideline_modules`, `module_obligations`,
   `severity_scales`, `severity_scale_values`, `checklist_templates`,
   `checklist_items`, `coverage_requirements`) it let any customer's admin
   rewrite vendor-curated data — the catalogue's `status`, `provenance` and
   `list_price_monthly` — and those write policies were **dropped outright**
   rather than re-scoped. No `platform_staff` table or JWT claim was introduced:
   the only writers that have ever existed are the CLI loaders, which run as
   `service_role`. The review's "decide what `super_admin` means" framing
   suggested a new predicate was needed; it was not.

   Where `super_admin` was the *sole* predicate on a mutation, deleting the
   clause would have left no valid predicate and locked tenants out of their own
   rows. Those 14 are re-scoped to
   `organization_id = get_user_organization() AND get_user_role() = …`. The bug
   was the missing organisation test, not the role.

**Deliberately still open, and why.** The `auth.uid()` half of H2 is untouched:
the helper functions still resolve identity through Supabase auth while the app
authenticates with Clerk, so the policies are now correct-but-inert. Re-keying
them onto the Clerk subject remains a prerequisite for any client-side Supabase
access, and must happen **after** 029 — doing it first would have activated all
41 holes at once.

**New residual risks introduced by the M3 and L4 fixes** (neither is a
regression; both are limits of the fix):

- `/users/invite` is now audited but not rate-limited, and its timing still
  separates the cross-tenant case from an unknown address. A per-actor limit is
  the real control.
- Email matching is `strip().lower()` only, so plus-addressing can still produce
  the two-pending-profiles ambiguity that the cross-tenant refusal exists to
  prevent. Needs one canonicalisation policy shared with `get_user_profile`.
- L4's `azp` allow-list is inert until `CLERK_AUTHORIZED_PARTIES` is set. It
  fails open by design so fresh checkouts do not 401 wholesale, which means it
  **must be configured before go-live**. The `iss` check is live unconditionally.

---

## 0. The central fact — verified, and it is correct

**The backend connects to Supabase as `service_role`, and therefore bypasses RLS entirely.**

- `db/client.py:29-49` — `get_client()` builds one process-wide client from
  `SUPABASE_URL`/`SUPABASE_KEY` with no token. The `token` branch (lines 38-43) exists but
  is called from exactly one place in the whole repo: `app.py:84`, the legacy Streamlit
  app. Every call site in `db/queries.py` and `api_server.py` uses the bare `get_client()`.
- The configured `SUPABASE_KEY` decodes to `{"role":"service_role","iss":"supabase",...}`.

So every policy in 022–027 and `db/schema_rls.sql` is dead code at runtime. The API-layer
`_ensure_permission` checks (`api_server.py:382-422`) plus the `.eq("organization_id", …)`
filters in `db/queries.py` are the only enforcement that actually runs. `PERMISSIONS_MATRIX.md:173`
and `core/authz.py:108-111` both already state this correctly — the codebase is not
confused about it.

One consequence that is *not* acknowledged anywhere: because the policies never execute,
they have never been tested, and two of them are wrong (finding **H2**).

---

## CONFIRMED findings

### H1 — HIGH · `DELETE /sites/{name}` destroys other tenants' readings, and can leave a site half-deleted

**One line:** `delete_site` deletes readings by `site_name` with no organisation or
`site_id` filter, so deleting a site called "Main Plant" deletes every tenant's readings
for any site of that name.

**Evidence:** `db/queries.py:370-372`

```python
client.table("readings").delete().eq("site_id", site_id).execute()
# Also cover legacy rows stored by site_name only
client.table("readings").delete().eq("site_name", site_name).execute()
```

The second statement has no `organization_id` and no `site_id` predicate. `readings` has no
`organization_id` column at all (`db/migrations/000_base.sql:59-84`) — tenancy lives only in
`site_id`, which this statement ignores. And `insert_reading` writes `site_name` on **every**
row, not just legacy ones (`db/queries.py:166`), so the statement matches current rows in
every tenant, not just orphans. RLS (`db/schema_rls.sql:97-102`) would have caught this; it
is bypassed.

**Exploit path:** any user with `sites.delete` (role `admin` or `super_admin` — and every
self-provisioned signup is `super_admin`, see H2) creates a site named `Main Plant`, `Site 1`,
`Emaar`, or any plausible collision, then calls `DELETE /api/sites/Main%20Plant`. All readings
named `Main Plant` across every organisation on the platform are deleted. Entry point
`api_server.py:651-672`. No confirmation, no soft delete, no recovery path.

**Second-order, and this is what migration 023 changed:** `obligations.site_id` is
`ON DELETE RESTRICT` (`023:419`). PostgREST issues these four deletes as four separate
transactions, so for any site carrying an obligation the readings are destroyed at line
370-372 and the `sites` delete at line 381 then fails. `delete_site` returns
`(False, "Database error: …")` → `api_server.py:663-664` raises **404**, and the
`audit_emit("site.delete", …)` at line 665 is never reached. Net result: a tenant's readings
are gone, the site still exists, the caller is told "not found", and nothing is audited.

**Fix:** delete the `site_name` sweep entirely, or bound it —
`.eq("site_name", site_name).is_("site_id", "null")` — and pre-check the RESTRICT
dependencies (obligations, certificates, assets) before deleting anything, returning 409 with
the blocking counts. Audit the attempt, not only the success.

---

### H2 — HIGH (latent) · The RLS "second line of defence" is a cross-tenant hole, not a defence

**One line:** every policy treats `super_admin` as a *platform* role, but it is a *tenant*
role that every self-provisioned signup receives; and all policies key on `auth.uid()` while
identity is Clerk, so they have never been exercised.

**Evidence:**

- `db/schema_rls.sql:44-53` — `get_user_role()` reads `user_profiles.role` for `auth.uid()`.
  There is no notion of a platform operator; `super_admin` is the ordinary top tenant role
  (`core/authz.py:25,96-120`).
- `api_server.py:317-330` — any user who passes Clerk sign-in with no existing profile is
  auto-provisioned **`super_admin`** of a fresh org.
- Consequences if a JWT-carrying client ever ships:
  - `023:790-796` `select_organization_entitlements` — `OR get_user_role() = 'super_admin'`
    → reads **every** tenant's entitlements, including `price_agreed`.
  - `023:812-818` `select_obligations` — same clause → reads every tenant's obligation
    registry, the table 023's own header calls "the single most damaging table in the schema
    to leak".
  - `023:797-799` `mutate_organization_entitlements` — `USING (get_user_role() = 'super_admin')`
    with no org predicate → **writes** any tenant's entitlements.
  - `023:779-781` / `022:290-296` `mutate_guideline_modules`, `mutate_standards` — any tenant's
    super_admin could set a module `status='available'`, `provenance='verified'`, or rewrite
    `list_price_monthly`. That is precisely the guarantee `023:776-778` says the policy exists
    to protect.
  - `db/schema_rls.sql:64-124` — the same clause on organizations, sites, readings,
    predictions, user_profiles.
- Second, independent defect: `user_profiles.id` references `auth.users(id)`
  (`db/schema_rls.sql:5-10`) and every policy resolves identity through `auth.uid()`. The app
  authenticates with Clerk and keys profiles on `clerk_id` (`002_clerk.sql`, `api_server.py:208`).
  A Supabase JWT for a Clerk user would not exist; a synthesised one would return `NULL` from
  `get_user_organization()` and match nothing. The policies as written cannot work for this
  app's identity model.

**Why it is not exploitable today:** service_role bypasses RLS, and no code path but
`app.py:84` ever builds a token-scoped client. This is a **latent** finding — but it means the
documented mitigation ("RLS is the backstop") does not exist, so H1-class bugs at the API layer
have nothing underneath them.

**Fix:** decide what `super_admin` means. If it is a tenant role, remove every bare
`OR get_user_role() = 'super_admin'` from `022`, `023`, `027` and `schema_rls.sql` and replace
it with a real platform-staff predicate (a `platform_staff` table, or a JWT claim). Separately,
re-key the helper functions on the Clerk subject before any client-side Supabase access ships.

---

### M1 — MEDIUM · The entitlement audit record omits every field that decides whether a duty is monitored

**One line:** `entitlement.create` records only `module_id` and a count, not `first_due_on`,
`active_from`, `site_ids` or `price_agreed` — so the levers that decide what appears overdue
leave no trace.

**Evidence:** `api_server.py:2955-2958`

```python
audit_emit("entitlement.create", …, target_id=entitlement["id"],
           module_id=body.module_id, obligations_created=len(created))
```

`first_due_on` flows to `core/entitlements.py:84-88`, which sets `next_due_on` and then
computes `status` from it. A `first_due_on` of `2035-01-01` makes every periodic obligation
in the module compute `compliant` (`core/obligations.py:196-202`) from creation. The endpoint's
own docstring calls the override "a claim about the past" and asks for it in `notes` — but
`notes` is optional and free text, and neither the value nor its absence is recorded.

`DELETE /entitlements` is better: it records `active_until` and the suspended count
(`api_server.py:3014-3017`).

**Fix:** put `active_from`, `first_due_on`, `site_ids` (count and ids), `price_agreed` and
`confirm` into the audit context. They are identifiers and dates, not secrets, so they are
within `core/audit.py`'s stated policy (`core/audit.py:10-12`).

---

### M2 — MEDIUM · `first_due_on` is unbounded — a legitimate override doubles as a way to make nothing overdue

**One line:** the only validation on `first_due_on` is that it parses as a date; a far-future
value silently converts a module's whole duty set into "compliant".

**Evidence:** `api_server.py:2611-2617` (declared as a plain `str | None`), parsed at
`api_server.py:2885-2888` with `date.fromisoformat` and no range test; consumed at
`core/entitlements.py:84-88`. Same for `active_from` — the only constraint is the DB's
`active_from <= active_until` (`023:363-365`), which does not bound either end.

This is the §7.5 threat arriving through the *create* path rather than the un-tick path, and
unlike un-ticking it produces no warning block, no `no_longer_monitored` list, and (per M1) no
audit detail.

**Mitigating control:** `entitlements.manage` is super_admin-only and enforced
(`api_server.py:2879-2880`), and the plan/confirm two-step means the operator sees
`due_immediately: 0` before writing. So this is misuse by an authorised insider, not privilege
escalation. It is still the exact insider the §7.5 reasoning in `core/authz.py:112-118` is
about.

**Fix:** reject `first_due_on > today` (or `> today + one cadence`) with 422, and require
`notes` whenever `first_due_on` is supplied. Bound `active_from` to a sane window.

---

### M3 — MEDIUM · `POST /users/invite` confirms that an email exists in another tenant

**One line:** the duplicate check is not org-scoped, so the 409 message discloses whether an
address is registered anywhere on the platform.

**Evidence:** `api_server.py:981-983`

```python
existing = client.table("user_profiles").select("id").eq("email", email).execute()
if existing.data:
    raise HTTPException(409, detail=f"{email} is already invited or registered.")
```

No `.eq("organization_id", org_id)`. Every other user endpoint is correctly org-scoped
(`api_server.py:792, 815, 850`).

**Exploit path:** an admin of any tenant (including a throwaway self-provisioned one, H2)
enumerates addresses one at a time and learns which belong to platform users — competitor
staff lists, in a market of FM contractors bidding against each other. It also breaks a real
case: a person employed by two contractors can never be invited to the second.

`invite_user` additionally emits **no** audit event, unlike `user.role.assign` and
`user.remove` (`api_server.py:800, 836`). Account creation is the one user-management action
with no trail.

**Fix:** scope the check to `org_id`; return a generic "cannot invite this address" for the
cross-tenant case; add `audit_emit("user.invite", …)`.

---

### L1 — LOW · Site-scope enforcement on the obligations registry is off by default

`_scope_enforcement_on()` returns False unless `SCOPE_ENFORCEMENT=1`
(`api_server.py:425-429`), which makes `_effective_site_ids` return `ALL_SITES` and both
`_in_scope` (`api_server.py:2669-2676`) and the scope half of `_resolve_site_filter`
(`api_server.py:2663-2665`) no-ops. `GET /obligations` requires only `reports.read`
(`api_server.py:2688`), which `operator` holds (`core/authz.py:66-70`). So today every
operator sees the entire organisation's obligation registry, including sites they are not
assigned to. The org filter still holds (`db/queries.py:1361-1362`) — this is intra-tenant
over-sharing, not cross-tenant. Deliberate and documented; flagged so it is a decision rather
than a surprise at go-live.

### L2 — LOW · Unbounded `price_agreed` / `notes` reach PostgREST and return 500

`price_agreed` is `float | None, ge=0` with no upper bound (`api_server.py:2618`) against
`NUMERIC(12,2)` (`023:352`); `notes` is unbounded `str | None` (`api_server.py:2619`) against
`TEXT`. `create_entitlement` propagates exceptions by design (`db/queries.py:1488-1502`) and
the endpoint does not wrap it, so `price_agreed: 1e15` yields an unhandled numeric-overflow
exception → 500 instead of 422. Requires super_admin; body is not reflected back, so nothing
leaks. Fix: `le=9_999_999_999.99` and `max_length` on `notes`.

### L3 — LOW · GET endpoints create sites, bypassing the plan site limit

`get_readings_for_site` → `get_or_create_site_id` **inserts** a site when the name is unknown
(`db/queries.py:87, 59-78`; also `reading_exists:135` and `insert_reading:165`). So
`GET /api/readings/{anything}` and `GET /api/status/{anything}` mint rows in `sites`. The
plan/site-limit gate lives only on `POST /sites` (`api_server.py:611-627`), so this is a
billing-control bypass and an unauthenticated-shaped row-inflation vector (authentication is
still required). `_site_certificates` (`api_server.py:1479-1481`) explicitly documents the
opposite rule — "a GET must never bring a site into existence" — and the function two lines
below it violates it. Fix: a `create=False` flag, or split resolution from creation.

### L4 — LOW · Clerk token validation checks neither `iss` nor `azp`

`api_server.py:184-190` decodes with `verify_aud: False` and no issuer or authorised-party
check. The JWKS URL is derived from the configured publishable key
(`api_server.py:135-147`), which does bind the token to the right Clerk instance — that is the
control that makes this low rather than high. Adding `issuer=` and an `azp` allow-list is cheap
and closes token reuse from another app on the same instance.

---

## PLAUSIBLE (suspected, not traced to a working exploit)

- **`evaluate` trusts one stored value.** `core/obligations.py:142-146` is the sole place a
  stored `status` decides the verdict: `suspended` short-circuits ageing. Today only
  `suspend_obligations_for_entitlement` writes it, and that is org+entitlement scoped,
  super_admin-gated and audited (`db/queries.py:1544-1556`, `api_server.py:2984, 3012`). Any
  future writer of `status` — an import, a backfill, a "bulk edit" endpoint — silences overdue
  rows with no other check in the way. Worth a comment at the write site and a test.
- **CORS is `*` on both apps** (`api_server.py:63-68`, `3050-3055`) with
  `allow_credentials` unset. Bearer tokens live in the SPA's own storage, so this is not
  directly exploitable, but it removes origin as a defence in depth for every endpoint.
- **Module `notes` is exposed to every authenticated role** (`api_server.py:2776`). It is
  internal editorial commentary about the guideline (`_not_sellable_reason` quotes the same
  material). Probably fine; worth confirming nothing operational or commercial is written
  there.

---

## Areas that are genuinely sound

These were checked and found correct — recording them so they are not re-litigated.

1. **No un-gated mutation path exists for the compliance tables.** Grepping every write to
   `obligations`, `organization_entitlements`, `guideline_modules`, `module_obligations`,
   `standards`, `specification_sets`, `spec_limits` returns exactly: `db/queries.py:1501, 1512,
   1525, 1537, 1553` (all behind `entitlements.manage`), and the operator-run CLI loaders
   `db/load_guidelines.py` / `db/seed_standards.py`, which are not reachable from the API. So
   the answer to "are there other paths that mutate these without an `entitlements.manage`
   check" is **no**. There is no endpoint to edit an obligation's cadence, `next_due_on`,
   responsible user, or status at all — which is the right posture for now.

2. **Every client-supplied id is validated against the caller's org before use, not filtered
   after.**
   - `entitlement_id` → `get_entitlement(org_id, id)` with both `.eq()`s
     (`db/queries.py:1450-1462`), called *before* the update (`api_server.py:2997-2999`); the
     update itself re-applies both predicates (`db/queries.py:1537-1540`), as does the rollback
     delete (`1525-1526`) and the suspend (`1553-1555`). Belt and braces.
   - `site_ids` → `_validated_sites` (`api_server.py:2836-2852`) proves membership of
     `list_site_ids(org_id)` before any row is built.
   - query `site_id` → `_resolve_site_filter` (`api_server.py:2653-2666`), 404 before use.
   - `module_id` → global reference data by design; not org-scoped, correctly.
   - The composite FK `(entitlement_id, organization_id)` → `organization_entitlements(id,
     organization_id)` (`023:452-454`, `023:358-360`) is a genuine third check at the DB level
     that survives service_role.

3. **Pricing suppression is complete.** `_module_view` (`api_server.py:2762-2789`) builds an
   explicit whitelist — `list_price_monthly` and `currency` are the only commercial columns in
   `guideline_modules` and both sit behind `billing.read`, which `operator` and `auditor` lack
   (`core/authz.py:61-95`). `price_agreed` never appears in `/modules`; it is returned only in
   the `POST /entitlements` response, which already required super_admin. `billing.py:522-540`
   is org-scoped.

4. **Error messages do not confirm other tenants' records.** "Site not found in your
   organisation" (`api_server.py:2662`), "Entitlement not found in your organisation"
   (`2999`), "Module not found in the catalogue" (`2895`) — all indistinguishable between
   "does not exist" and "belongs to someone else". `_validated_sites` echoes only the caller's
   own input (`2850-2851`). The single exception is M3.

5. **§7.5 is implemented honestly.** Un-ticking sets `active_until` and `status='suspended'`
   and deletes nothing (`db/queries.py:1529-1556`); `evaluate` reports suspended as
   "not monitored, and history retained", never `compliant` (`core/obligations.py:139-146`);
   the response names every affected obligation rather than giving a count
   (`api_server.py:3025-3034`); `ON DELETE RESTRICT` on `obligations.entitlement_id`,
   `site_id`, `asset_id`, `standard_id` (`023:419-421, 452-454`) makes the destructive
   alternative fail at the database. `needs_attention` is counted separately and never folded
   into `overdue` (`core/obligations.py:238-256`).

6. **Date input validation is right where it exists.** `_as_of` (`api_server.py:2622-2631`)
   and both entitlement date parsers (`2884-2888`, `2990-2993`) return 422 on a bad date rather
   than letting it reach PostgREST. Enum-ish inputs on this surface are all server-derived, not
   client-supplied.

7. **The demo path cannot reach real data, or vice versa.** Migration 014 is a per-org trial
   *licence* (`demo_keys`, `UNIQUE(organization_id)`, `ON DELETE CASCADE`), not a sample-data
   seeder; `core/demo.py` is pure date arithmetic with no DB access. `get_demo_key` and
   `create_demo_key` are org-scoped (`db/queries.py:666-707`), activation is super_admin-only
   and audited (`api_server.py:1104, 1119-1121`), and the state cache is keyed by org id
   (`api_server.py:352-379`). The only "sample data" in the product is client-side in the
   Streamlit app (`app.py:60-146`) and never touches Supabase. Expiry correctly gates
   `entitlements.manage` as a write (`core/demo.py:64-69`). **No finding.**

8. **The audit table cannot be rewritten.** `audit_events` has `GRANT SELECT, INSERT` only —
   no DELETE — plus a `BEFORE UPDATE` reject trigger (`006_audit_events.sql:49-56`,
   re-asserted by `012:13-16`). 012's removal of the DELETE trigger is a deliberate,
   documented trade for cascade offboarding and does not open a delete path, because the grant
   was never made.

9. **`db/guard.py` is fail-closed and correct** for its stated purpose (never write the frozen
   lagoon database). It is not a tenancy control and does not pretend to be.

---

## Recommended order of work

*(As recommended at review time. It was followed; see the Status block at the
top for what remains.)*

1. **H1** — one-line data-destruction bug, reachable by any admin today. Fix first.
2. **M3** — trivial fix, ongoing disclosure.
3. **M1 + M2** — together they close the §7.5 create-path gap; both are small.
4. **H2** — larger decision (what `super_admin` means), but it must land **before** any
   client-side Supabase access ships, not after.
5. **L1–L4** as convenient.
