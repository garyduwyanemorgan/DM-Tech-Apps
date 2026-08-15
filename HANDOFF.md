# Handoff — 2026-08-16

Written at the end of a session that resumed work interrupted by an unplanned
machine shutdown on 2026-08-15. Records verified state, not intended state:
everything below marked "verified" was checked against the live stack on the
date above, and everything still open is named with the reason it is open.

Branch `feat/dm-compliance-phase-1`, version 1.8.0. Working tree clean, 0 ahead
and 0 behind `origin/feat/dm-compliance-phase-1`. Nothing is stashed and nothing
is uncommitted.

---

## 1. The one thing blocking someone else

`CLERK_DEV_SECRET_KEY` is **not set**, and the last attempt to set it did not
land on disk. `POST /users/invite` returns 503 at `api_server.py:999` until it
is. Nothing else depends on it.

Add to `C:\AI\DM-Tech-Apps\.env` (gitignored at `.gitignore:6`, untracked —
verified safe to hold a secret):

```
CLERK_DEV_SECRET_KEY=sk_test_…
```

The `sk_test_` key from the `touching-baboon-1305` Clerk dashboard
(Configure → API keys). **The name matters.** `api_server.py:109-118` prefers a
dev secret key only when a dev *publishable* key is also present, which it is;
and the pairing guard at `api_server.py:1002-1012` refuses the invite outright
if the two keys name different Clerk instances. So a `sk_live_…` paired with the
configured `pk_test_…` does not half-work — it 503s with a mismatch message.
Note `.env.example:22` shows `CLERK_SECRET_KEY=sk_live_...`; that is the
production pairing, not this one.

Verify without printing the value:

```bash
python -c "
from core.config import secret
for k in ('dev_secret_key','secret_key','dev_publishable_key'):
    v = secret('clerk', k)
    print(f'  clerk.{k:20} -> ' + ('SET' if v else 'NOT SET'))
"
```

At time of writing this reports `dev_secret_key -> NOT SET`. The resolution
chain `secret()` searches is env → `.env` → `secrets.toml` (`core/config.py:83-96`);
all three were checked and none held it. `.env` mtime was still 2026-08-15 20:21,
unchanged, so the edit never reached the file — check the editor's title bar for
the real path before re-editing.

---

## 2. Verified state of the environment

The database is the **self-hosted Supabase stack at `C:\AI\supabase\docker`**.
The lagoon database is never touched. The gateway is on **port 54321**, not 8000.

Docker Desktop restarts these containers on launch, so after a reboot they come
back on their own. To bring them up by hand:

```bash
cd /c/AI/supabase/docker && docker compose up -d
```

Caution learned the hard way: Docker Desktop *restarts* containers rather than
recreating them, and container env is frozen at creation. After changing
`C:\AI\supabase\docker\.env`, `docker compose up -d` reporting "Running" means
nothing was re-read. Check what a container actually holds:

```bash
docker inspect supabase-rest --format '{{range .Config.Env}}{{println .}}{{end}}' | grep PGRST_JWT_SECRET
```

A ~40-character value is the bare symmetric secret; a ~580-character value is
the JWKS key set. It is currently the JWKS (verified).

### Clerk as a JWT issuer — done, and proven downstream

`JWT_JWKS` in the stack's `.env` holds **two** keys: Clerk's RS256 public key
(`ins_3HxUWwygVrq68HQYBjGOrllFBfs`) and the local HS256 secret as an `oct` key.
Both are required — dropping the symmetric key would reject `anon` and
`service_role`, breaking `db/client.py` and every existing caller.
`scripts/clerk_jwks.py --verify` reports what PostgREST will trust without
printing key material.

The `"role": "authenticated"` claim was added in the Clerk dashboard
(Sessions → customize session token) on 2026-08-16.

Verified against the live stack:

| Check | Result |
|---|---|
| `service_role` → `user_profiles` | 200 — existing callers unbroken |
| `anon` → `user_profiles` | `[]` — RLS failing closed |
| malformed bearer token | 401 |
| `role: "no_such_role_xyz"` | 401 *role does not exist* — proves PostgREST reads the claim and does `SET ROLE` |
| `role: "authenticated"` | 200 |
| `clerk_subject()` under that token | returns the token's `sub` — 030's helper chain resolves |

**Not verified:** that Clerk itself now emits the claim. The tests above used a
token signed with the local HS256 key — the same PostgREST code path, since
signature validation precedes role resolution, but it proves everything
*downstream* of Clerk rather than Clerk's own output. To close that gap, decode
a real session token from the running app and confirm `role: "authenticated"`
appears in the payload.

### Migrations 029 and 030 — applied

Both are hand-applied files, and both commit messages say "not yet applied"
because they were written before the migrations were run. **They have since been
applied.** Verified directly against the database:

- all four RLS helpers (`clerk_subject`, `get_user_organization`, `get_user_role`,
  `get_user_profile_id`) exist, are `STABLE`, `SECURITY DEFINER`, `search_path`
  pinned to `public, pg_temp`
- zero policies reference `auth.uid()`
- zero write policies remain on the global reference tables
- 50 policies total, matching 030

One policy looks like a leftover under a naive grep and is not: `mutate_org` on
`organizations` reads `id = get_user_organization() AND get_user_role() =
'super_admin'`. That table keys its tenant on `id`, not `organization_id`, so
this is exactly the re-scoped shape 029 prescribes. Do not "fix" it.

---

## 3. What this session changed

Four commits, all pushed:

| Commit | What |
|---|---|
| `083bdb0` | `scripts/clerk_jwks.py` — how the RS256 + HS256 key set was built, so the 580-char blob in the stack's `.env` is reproducible |
| `75642e8` | L3 — reads no longer create sites |
| `6a4ea36` | L3 marked fixed in the review register |
| `395308a` | Two scope defects found while investigating L1 |

**Tests: 674 passed, 10 skipped.** Baseline at session start was 628/10.
Run with `python -m pytest -q`. Some tests hit the live stack, so it must be up.

### L3 (`75642e8`) was larger than filed

Filed as 3 call sites; there were 13. The insert was not the dangerous part —
every read had an `else` branch filtering on `site_name` when resolution failed,
and `readings`/`predictions` carry no `organization_id` (tenancy lives only in
`site_id`), so that fallback read every tenant with a site of that name. The old
code could barely reach it because the site was always created first, meaning a
naive fix would have *opened* H1 in read form. `validate_open_predictions` was
worse than a read — its name fallback was an `UPDATE` across tenants.

Deliberately left open: the ingest path still auto-provisions sites outside the
plan limit, so that limit remains enforceable only on `POST /sites`. Closing it
means deciding whether ingest for an unlisted site should 402 or
auto-provision-and-bill — a commercial decision, not a code one.

### The two scope defects (`395308a`)

Both live behind `SCOPE_ENFORCEMENT` and neither is reachable while it is off.

1. `get_assigned_site_ids` / `get_project_site_ids` swallowed every exception and
   returned `[]`. Under enforcement `[]` is a positive claim — "assigned to
   nothing" — so an outage made a fully-assigned user indistinguishable from an
   unassigned one, silently. They now raise `ScopeUnavailable` and the endpoints
   answer 503. A genuinely unassigned user still resolves to the empty set; only
   a failed *read* raises. No path widens to `ALL_SITES` on error.
2. `_effective_site_ids` resolved admin through project assignments alone, while
   `core/scope.py:44-45` defines admin as `project_site_ids | assigned_site_ids`.
   The dropped half is the only one with a working writer, so an admin granted
   sites through User Management resolved to nothing.

An existing test was asserting defect 1 rather than catching it — its operator
resolved to an empty set through the swallowed failure, and its own comment
("here empty, no DB") records that the empty was known not to be an answer. It
now asserts the 503.

---

## 4. Open, in the order I would take them

### a. Nothing sends a Clerk token yet

`db/client.py` connects as `service_role` and bypasses RLS. The 50 policies are
correct and dormant. All the Clerk/JWKS/030 work **unblocks** client-side
Supabase access; it does not switch it on, and today's runtime behaviour is
unchanged. This is the decision that gives the RLS work its value.

### b. L1 — leave `SCOPE_ENFORCEMENT` off

Investigated this session; the recommendation is the status quo, with reasons.
The review frames L1 as a default that could be flipped when convenient. It is
not.

`user_site_assignments` exists (`007_assignments.sql:51-60`) but **nothing has
ever written to it**. The only writer is `PUT /users/{id}/sites`, super_admin
only, and no backfill exists — `PERMISSIONS_REVIEW_PACKAGE.md:216` specified one
and it was never written. Zero assignments does not mean org-wide; it resolves
to an empty frozenset, which denies everything.

Two things the review's write-up gets wrong:

- **It omits `GET /sites`**, which is the consequential call site, not the
  obligations registry. With enforcement on it returns `{"sites": []}`, and
  `Sidebar.tsx:202-208` sets `activeSite` from `names[0]` — so an unassigned user
  gets a blank sidebar and empty dashboards, with no explanatory empty state.
- **Admins are hit harder than operators**, resolving through a `sites.project_id`
  column that `007` added NULL with no backfill.

The on-state is also essentially untested at endpoint level.

Prerequisites before the default could flip: confirm `007` is applied; write the
backfill (one row per existing user × every site in their org, plus
`sites.project_id`); give the frontend an empty-scope state; assign sites at
invite time so new users do not start locked out; and make the flag per-org
rather than a process-wide env var, since it cannot otherwise be staged per
tenant as intended.

### c. Residual items already recorded elsewhere

- `SECURITY_REVIEW_COMPLIANCE.md` — H1, H2, M1, M2, M3, L2, L3, L4 fixed; L1 open
  by choice. The PLAUSIBLE section (CORS `*`, `evaluate` trusting one stored
  value, module `notes` exposure) was never worked.
- No write path is scoped at all (`PERMISSIONS_IMPLEMENTATION_STATUS.md:27`), so
  enforcement would block reads while leaving writes open — UI narrowing, not an
  access boundary.
- `/users/invite` is audited but not rate-limited, and email matching is
  `strip().lower()` only, so plus-addressing can still produce two pending rows
  for one address (noted in `ca4376e`).

---

## 5. Gotchas worth not rediscovering

- **The gateway is port 54321.** Port 8000 is the container-internal port and
  returns 404 for everything from the host.
- **`db/queries.py` does `from .client import get_client`**, binding the name into
  the queries module. Patching `db.client.get_client` alone leaves tests talking
  to the live stack and passing for the wrong reason — patch both. See
  `_patch_client` in `tests/test_scope_resolution_failure.py`.
- **A test that asserts an empty result may be asserting a swallowed failure.**
  This bit twice in one session: once in `test_resolver_authz.py`, once in a
  newly written test. Against a fail-closed system, an empty result set makes a
  broken database look like a secure one — assert the caller sees their *own* row
  first, as `tests/test_rls_clerk_identity.py` does.
- **No `load_dotenv` exists anywhere in the Python source.** `.env` is read by
  `core/config.py:secret()` at call time, not loaded into the process
  environment. Whatever serves the API may still need a restart depending on how
  it is launched — this was never determined.
