# Handoff — 2026-08-17

Written after a session that resumed work interrupted by an unplanned machine
shutdown on 2026-08-15. Records verified state, not intended state: everything
marked "verified" was checked against the live stack on the date above, and
everything still open is named with the reason it is open.

Branch `feat/dm-compliance-phase-1`, **version 1.9.0**. Fourteen commits added
this session. **The v1.9.0 tag does NOT exist and nothing is pushed** — see §8.

| Commit | What |
|---|---|
| `84621ab` | Reads run under the caller's token; anon key closes the fail-open hole |
| `454f0e0` | Observability layers 0-2 — correlation, reason codes, workflow spine |
| `4d694a4` | The read side — `/system/*` endpoints and the System Health screen |
| `b0cb0c3` | Layer 3 — crash reporting, inert unless a DSN is set |
| `4892237` | A partial reading is INCOMPLETE, and no longer a 500 |
| `4f1c9aa` | The correlation id is something a user can quote |
| `b8a420a` | A failed read is no longer indistinguishable from empty data |
| `da5ccbf` | The dashboards stop asserting verdicts they do not know |
| `3222ff0` | Alerts fixed, Vitest added, migration 032 drafted |
| `e675f3e` | `chore(release): v1.9.0` |
| `24f0b83`, `c585687` | Strip the parent build's identity from this repo (§9) |
| `dc3a999`, `f0dc90b`, `8b70d1a` | This handoff |

Three bodies of work. Scoped reads, **verified end to end against a real Clerk
user** (§2.1). The observability system (§3), built because the app could not
report where it broke. And the UI honesty work (§4), because it turned out the
app would state compliance verdicts it had never established.

**Tests: 804 Python passed / 10 skipped, and 16 Vitest passed.** At session
start: 674 Python, and no frontend test framework at all. Run with
`python -m pytest -q` and, in `frontend/`, `npx vitest run`. Some Python tests
hit the live stack, so it must be up.

One habit worth keeping, because it earned its place repeatedly: **a test is not
believed until it fails against a deliberately broken implementation.** It
caught a scoped-read guard (12 of 17 failed on revert), a tenant-isolation guard
(2 failed), and the partial-reading fix (15 of 16). It also caught two *false*
verifications, which is the subtler lesson: once where the mutation string did
not match the code, and once where it matched but changed no behaviour. Both
look exactly like a passing test. **Confirm the mutation landed AND that it
altered semantics.**

---

## 1. The one thing blocking someone else

Unchanged from the last handoff. `CLERK_DEV_SECRET_KEY` is **still not set** —
verified again this session, and `.env`'s mtime was still 2026-08-15 20:21, so
the edit never reached the file. `POST /users/invite` returns 503 at
`api_server.py:999` until it is. Nothing else depends on it.

Add to `C:\AI\DM-Tech-Apps\.env` (gitignored at `.gitignore:6`):

```
CLERK_DEV_SECRET_KEY=sk_test_…
```

The `sk_test_` key from the `touching-baboon-1305` Clerk dashboard
(Configure → API keys). **The name matters.** `api_server.py:109-118` prefers a
dev secret key only when a dev *publishable* key is also present, which it is;
and the pairing guard at `api_server.py:1002-1012` refuses the invite outright
if the two keys name different Clerk instances. A `sk_live_…` paired with the
configured `pk_test_…` does not half-work — it 503s with a mismatch message.
`.env.example:22` shows `CLERK_SECRET_KEY=sk_live_...`; that is the production
pairing, not this one.

Verify without printing the value:

```bash
python -c "
from core.config import secret
for k in ('dev_secret_key','secret_key','dev_publishable_key'):
    v = secret('clerk', k)
    print(f'  clerk.{k:20} -> ' + ('SET' if v else 'NOT SET'))
"
```

---

## 2. What this session changed — reads now run under the caller's token

The previous handoff listed "nothing sends a Clerk token yet" as the top open
item. That is now half-closed: **reads are scoped, writes are not.** This was a
deliberate split, not a partial job — see §5 for why writes cannot follow yet.

### The state that was found, and was worse than filed

`PERMISSIONS_REVIEW_DISCOVERY.md:54` said the token was dropped at 18 call
sites. The real shape:

- `api_server.py` **was** already doing its part — `get_current_user_profile`
  returns `"token": token` (`:371`, `:385`) and ~16 endpoints passed
  `token=profile["token"]` into `db.queries`.
- `db/queries.py` accepted `token` in 21 signatures and **dropped every one of
  them** at `get_client()`. 65 bare calls, zero scoped. That was the whole gap.
- `_read_site_id` (`:87`) and `find_site_id` (`:1310`) took no `token` at all,
  so even the "ready" read functions broke the chain from inside.

### The load-bearing half is the anon key, not the threading

**There was no anon key anywhere in the repo.** The only configured Supabase
key decoded to `role: service_role`. So `get_client(token)` built its
"scoped" client from the service_role key and relied on `.postgrest.auth()`
overriding the Authorization header. That works, but it fails **open**: any
path that forgets the token silently regains a full RLS bypass.

`db/client.py` now resolves `SUPABASE_ANON_KEY` for the scoped branch and
**returns None when it is absent** rather than falling back. Verified by
execution, not by reading: with the key blanked, `get_client("abc.def.ghi")`
returns `None`.

`get_client()` with no token is untouched — still the service_role singleton,
which ~57 remaining call sites and every seed/cron/background script rely on.

### What was threaded

Seven read functions (`get_readings_for_site`, `get_site_names`,
`reading_exists`, `get_validated_predictions`, `get_site_reading_count`,
`get_sludge_zones`, `get_open_data_requests`) plus the two helpers. Counts
reconcile: 57 bare + 8 scoped = 65, the original total.

### 2.1 Proven end to end with a real Clerk user

Done after the commit, against the live stack with the dev servers up
(API `:8010`, Vite `:5173` — Vite binds IPv6, so use `localhost`, not
`127.0.0.1`). `uvicorn` is in `requirements.txt` but was not installed; it is now.

**Step 1 — Clerk → api_server.** Signing in created
`user_3I2TVNgiIgcM9VCC5GjDtzRWiv2 / super_admin`. That row is written only by
`_create_super_admin_profile()` (`api_server.py:297-318`), reachable only after
`get_user_from_token` verifies the signature against Clerk's live JWKS and
passes the `iss`/`azp` checks. Before this, every test had used a self-signed
token.

It also confirms §5: the bootstrap succeeded **because writes are still
service_role**. Under RLS both inserts would have been denied.

**Step 2 — the scoped read, under that token.** A throwaway site plus one
reading, then `GET /api/status/RLS-Verify-Temp`. It returned 500 — and the 500
is the proof, so do not "fix" this reasoning later:

```python
# api_server.py:1716
if not readings:
    return {..., "note": "No readings stored yet."}
```

An RLS denial returns **200 with that note** and cannot reach line 1723. The
crash was *at* 1723 (`_assess`), so rows came back; and line 1710 passes
`token=profile["token"]`, so they came through the anon-key scoped client.
Real Clerk token → anon client → PostgREST → RLS → the caller's own row.

That also settles the `role` claim: without it PostgREST rejects the token, the
swallow returns `[]`, and the response would have been the 200-with-note.

**Do not use `GET /sites` for this test.** `list_sites` (`api_server.py:643`)
calls `get_client()` unscoped, so a site appears there whether RLS works or
not. It will report a false pass. Use `/status/{site}` or `/readings/{site}`,
and insert an actual reading first — an empty result is ambiguous.

The 500 itself was a genuine pre-existing bug, unrelated to tokens; see §7e.

### The tests were mutation-checked

`tests/test_scoped_read_client.py`, 17 tests. Reverting both implementation
files fails **12 of 17** — so they genuinely detect the token being dropped
again.

**The 4 live tests are not among the 12.** They drive `psql` directly with
`SET LOCAL request.jwt.claims`, so they prove the *policies* work, not that the
application uses them. The unit half is what pins application behaviour. Do not
read "live tests pass" as end-to-end proof.

---

## 3. The observability system

Built after the token work, in answer to a direct question: the system could
not report where and why it broke. Four layers, all committed and pushed
(`454f0e0`, `4d694a4`, `b0cb0c3`).

### Why this shape, and not just an error tracker

Of the bugs found in this branch, an exception tracker would have caught
exactly one. The rest returned plausible-looking data: a token silently
dropped, a read denied by RLS, a client that failed to build. **This system
fails silently, not loudly** — an RLS denial, an unreachable database, a
dropped token and a genuinely empty tenant all arrive at the caller as `[]`,
and several screens then fall back to sample data and look healthy.

So the work was making silence testify. Crash reporting is Layer 3, last and
least, precisely because it is the least useful here.

The codebase had already invented the right primitive once: `ScopeUnavailable`
in `core/scope.py` — "an unknown scope is not an empty one". Layers 1 and 2
generalise that instinct.

### What each layer is

| Layer | Where | What |
|---|---|---|
| 0 Correlation | `core/observability.py` | per-request id, contextvar-based; `X-Request-Id` in and out; stamped on every audit event |
| 1 Reason codes | `core/reasons.py`, `db/client.py`, `db/queries.py` | closed vocabulary; 34 read swallows now emit before returning their fallback |
| 2 Workflow spine | `core/workflow.py`, migration 031, `ingestion/` | per-entity pipeline step outcomes: ingest → parse → validate → persist → assess → obligation → report |
| Read side | `api_server.py`, `SystemHealth.tsx` | `/system/health`, `/system/failures`, `/system/runs/{id}`, gated on `audit.read` |
| 3 Crash reporting | `core/errors.py` | inert unless `SENTRY_DSN` is set |

### Things that look like bugs and are not — do not "fix" these

- **`RLS_DENIED` is always `suspected`, never asserted.** PostgREST does not
  raise on a denial; it returns zero rows. A denied read and an empty tenant
  are genuinely indistinguishable. Claiming certainty here would be a
  confident wrong signal, which is worse than none.
- **`reading_exists` does not emit a suspected denial**, unlike the other
  seven token-scoped reads. It is a predicate called before every insert where
  "no" is the happy path; emitting there fires on every upload and buries the
  real signals.
- **The four `workflow_events` reads do not emit one either.** An empty table
  is the designed state of a quiet tenant, and the UI renders it as a positive
  result. Emitting there means the observability read path corrupts the
  observability record every time someone opens the dashboard.
- **`core/workflow.py::_persist` refuses to write under pytest.** The
  ingestion tests drive the instrumented gates against the live dev stack and
  were writing 63 real org-less rows per suite run into what is meant to be
  evidence. Tests that need persistence opt in with
  `WORKFLOW_PERSIST_IN_TESTS=1` and inject a fake client.
- **`SENTRY_SEND_SOURCE` defaults to off.** Stripping frame locals is not
  sufficient on its own — a value also appears in the source line that assigns
  it, so with source context on, the data walks back out through
  `pre_context`. Verified against the real SDK; unit tests of the scrubber
  passed while the live payload still leaked. It also stops proprietary source
  reaching whoever runs the collector.

### Defects caught during integration

Eight, none shipped. Recorded because each looked fine in review and only
surfaced under direct testing:

1. `RequestIdMiddleware` is registered on both the outer app and the mounted
   `api_app`, so it ran twice and minted two ids — the user got one, the audit
   rows the other. Nesting is now idempotent.
2. An unhandled exception meant the response header was never set, so the 500
   — the one response anyone reports — carried no id.
3. `get_client()` failure → audit emit → `_persist` → `get_client()`: 51 frames
   before `RecursionError` was silently swallowed, firing exactly when the
   database is unreachable. Guarded; now 2.
4. `reason_code` fell back to the exception class name, giving a supposedly
   closed vocabulary unbounded cardinality.
5. Ordering by `created_at` alone returned runs reversed on shared timestamps —
   the "chronological" timeline was not chronological. `id` is the tiebreak.
6. The suspected-denial signal wired into the `workflow_events` reads (above).
7. The pytest pollution (above).
8. Sentry source-context leakage (above).

### Not done

- **Migration 031 is applied to the LOCAL dev stack only.** Production needs it
  by hand, like 029 and 030.
- **No crash report has ever reached a collector.** The scrubbing was verified
  by capturing a real exception through the real SDK with a fake transport and
  grepping the outgoing payload. The first live report still needs a DSN and a
  look at what actually arrives.
- **The empty and unavailable states of `SystemHealth.tsx` have not been seen
  rendered** — verified by unit test and by reading the component only. To see
  *unavailable*, stop the API and reload the page.

---

## 4. The UI honesty work — three fabricated-verdict paths

Found by auditing the frontend for the same failure class as §3: a failed read
presented as a fact. All three are fixed. This mattered more than the backend
half, because these screens can inform what a contractor reports to a regulator.

**The governing rule, and the one to defend in review: the UI must never present
a compliance verdict, alert level, or risk figure that the system does not
actually know. "We could not find out" must be visibly distinct from "everything
is fine" and from "nothing has been submitted yet."** Those are three states,
not two.

| Was | Consequence |
|---|---|
| `Dashboard.tsx` — no `res.ok` check; `catch` set `alertLevel = 1` | A green "compliant" chip during an outage |
| `lib/status.ts` — a failed per-site fetch became `'blue'` | An executive rollup that under-reported risk: `needsAttention` fell, `avgCompliancePct` was diluted |
| `Alerts.tsx` — no `res.ok` check | **A live Level 3/4 emergency could go unshown** while the page read as a calm reference document |

The third is the worst: it suppresses an escalation rather than blanking a
number.

`TrafficLight` gained `'unavailable'`. It could not reuse what existed —
`'blue'` means *awaiting lab results* and `'grey'` means *a reading exists but
carries no usable verdict*. Neither means *we could not find out*, and borrowing
one would have moved the conflation rather than removed it. Because
`LIGHT_STYLE` is a `Record<TrafficLight, …>`, the compiler forced every consumer
to account for the new case.

`rollup()` excludes unavailable sites from the `avgCompliancePct` **denominator**
rather than scoring them 0 or 100, and reports `compliancePctBasis` — how many
sites actually contributed a number. That is deliberately NOT `total -
unavailable`: a blue site is reachable but contributes nothing, so quoting the
reachable count overstates the sample the figure rests on.

### Five defects caught reviewing those fixes, four inside the fixes themselves

1. The traffic-light chip was gated but the larger **"Current Alert Level" badge**
   still rendered the stale level — the same fabricated verdict in a bigger font,
   two elements below the card announcing the failure.
2. State was not cleared when `activeSite` changed between two non-empty sites,
   so one lagoon's verdict rendered under another's name until the new fetch
   resolved.
3. `ProjectDashboard` showed **"Outstanding actions: 0" in compliant-green** for
   an unreadable site, contradicting the "could not be checked" line directly
   beneath it. Unknown is not zero.
4. The KPI captions said "of N reachable" while the average covered only sites
   that returned a number — the first fix's own caption quietly reintroduced a
   smaller version of the bug it fixed.
5. The outage card used `tier="critical"`, the exact palette of a **confirmed**
   critical alert, leaving copy as the only thing distinguishing "we don't know"
   from "confirmed bad".

Finding 1 is the same shape as the partial-reading 500 in §7e: fixing the site
named in the report rather than the property. **`tsc` now enforces part of it** —
`alertLevel` is `null` until known, so `ALERT_BG[alertLevel]` fails to compile
if the badge is not gated.

### Vitest exists now

`frontend/` had no test framework at all. It now has Vitest + jsdom +
@testing-library, `npx vitest run`, 16 tests pinning the guarantees above rather
than the code that implements them. Mutation-checked.

### Sample data is a FEATURE, not a bug

`show_sample_data` is a persisted user preference with a toggle and a Settings
page. The bug was never that sample data exists — it was that *"you asked for
demo data"* and *"your data failed to load"* were the same state. On a failed
read `useMonthlySeries` now shows **nothing** rather than the sample baseline:
substituting demo figures at the moment we know the real ones are missing is the
worst possible time, and it is pixel-identical to the deliberate feature.

Only 3 of the 6 sample-data components consume that hook. `Chemistry`, `Ecology`
and `Drivers` attempt no live read at all — they always compute from the static
baseline — so `'unavailable'` cannot arise there.

---

## 5. Why writes deliberately stayed on service_role

Not laziness — the policies genuinely deny them, and two of the denials are
structural.

### The bootstrap is broken under RLS (verified against the live DB)

```
organizations  | mutate_org      | ALL | qual=((id = get_user_organization()) AND (get_user_role() = 'super_admin'))
user_profiles  | mutate_profiles | ALL | qual=((organization_id = get_user_organization()) AND (get_user_role() = ANY (ARRAY['admin','super_admin'])))
```

Both are `FOR ALL` with `with_check` NULL, so Postgres reuses `qual` as the
INSERT check. `_create_super_admin_profile()` (`api_server.py:297-318`) inserts
an org, then a profile. For a user with no profile yet both helpers return
NULL, and a brand-new org's `id` can never equal the caller's non-existent org.
**Both inserts are denied.** Self-serve first-sign-in is unreachable under RLS.

Note `mutate_profiles` predates the rework: 029 and 030 rewrote
`select_profiles` twice and never touched it. Closing this needs a migration or
a `SECURITY DEFINER` provisioning RPC. The invite path is fine — the inviting
admin already resolves.

### Admin billing would be denied

`billing.manage` is in the `_ADMIN` bundle (`core/authz.py:84`), but
`mutate_org` requires `super_admin`. Any org-admin managing a subscription
would be approved by `_ensure_permission` and then denied by the database.

### Sites, already documented

`queries.py:361` and `:389` already said "authenticated role lacks INSERT /
DELETE on sites".

### The subtlety worth not undoing

Three write paths resolve a site internally —
`validate_open_predictions:267`, `delete_sludge_zone:556`,
`dismiss_data_request:622`. They still call `_read_site_id` **without** a
token, on purpose. Scoping those lookups would let an RLS denial resolve the
site to `None`, and the write would silently no-op while reporting success.
Do not "finish the job" by adding a token there.

---

## 6. Verified state of the environment

The database is the **self-hosted Supabase stack at `C:\AI\supabase\docker`**.
The lagoon database is never touched. The gateway is on **port 54321**, not 8000.

Docker Desktop must be started after a reboot; it then restarts the containers
itself. By hand: `cd /c/AI/supabase/docker && docker compose up -d`.

Container env is frozen at creation, and Docker Desktop *restarts* rather than
recreates. After changing `C:\AI\supabase\docker\.env`, `docker compose up -d`
reporting "Running" means nothing was re-read.

**`docker exec supabase-rest …` currently fails** ("OCI runtime exec failed").
Read its env through `docker inspect` instead:

```bash
docker inspect supabase-rest --format '{{range .Config.Env}}{{println .}}{{end}}' | grep PGRST_JWT_SECRET
```

Verified this session — the JWKS holds exactly two keys:

```
kty=RSA alg=RS256 kid=ins_3HxUWwygVrq68HQYBjGOrllF   <- Clerk
kty=oct alg=HS256 kid=supabase-local-hs256           <- local
```

Both are required; dropping the symmetric key would reject `anon` and
`service_role` and break every existing caller.

**Correction to the previous handoff's open item.** It is no longer true that
Supabase is unconfigured for Clerk — `083bdb0` did that, and the
`api_server.py` comment claiming PostgREST answers PGRST301 for a Clerk JWT was
stale. It has been rewritten. If you see that claim repeated anywhere else,
it is wrong.

---

## 7. Open, in the order I would take them

Quick list. The first three need access this session did not have.

1. **Finish the v1.9.0 tag and push (§8)** — needs the GPG passphrase. Do this
   first; the repo is sitting on an unreleased release commit.
2. **`CLERK_DEV_SECRET_KEY` (§1)** — still unset, still 503s `/users/invite`.
   Needs the Clerk dashboard. Carried across four handoffs now.
3. **Apply migrations 031 and 032 in production** — both are applied to the
   LOCAL dev stack only (031), or not applied anywhere (032). Hand-applied by
   convention.
4. **Decide `render.yaml`'s service name (§9)** and check whether a Render
   service auto-deploys from this repo.
5. **Wire 032 into `_create_super_admin_profile()`** — the function exists
   unused, deliberately. Only worth wiring when writes actually move onto RLS.
6. **The request id is surfaced only on `SystemHealth` and the screens fixed in
   §4.** Most components still hand-roll their own fetch and show no id.
   `frontend/src/lib/requestId.ts` is the seam for that; there is still no
   central fetch wrapper, and building one is a separate, riskier job.

### a. ~~Nobody has ever seen a real Clerk token~~ — CLOSED 2026-08-17

This was the last open link and it is now proven end to end against a real
signed-in Clerk user. Recorded in full at §2.1. Clerk emits
`role: "authenticated"` on the **default** session token — note
`getToken()` is called with no arguments (`AuthContext.tsx:53,96`), so no JWT
template is involved and none is needed.

Do not re-open this on the strength of `get_user_from_token` extracting only
`sub` and `email`. That is true, and irrelevant: the claim's consumer is
PostgREST, not Python.

### b. A failed read is invisible in the UI — MOSTLY FIXED in §4, one gap left

Largely closed. `Dashboard.tsx`, `Alerts.tsx`, `Monitoring.tsx`,
`ComplianceReport.tsx` and the three role dashboards now distinguish a failed
read from an empty one, and `useMonthlySeries` no longer substitutes sample data
for a failure.

**The remaining gap is `Sidebar.tsx:198-218`**, which has no `res.ok` check: a
401 or 500 on `GET /sites` leaves the site list silently empty, and
`activeSite` is only set when `names.length > 0`. Downstream screens then show
their (now honest) "no site selected" state without saying the site list itself
failed to load. Ranked lower than the other three because it cannot fabricate a
verdict — it blanks the app rather than asserting something false — but it is
the same class and the audit flagged it.

Also unfixed: `Home.tsx`, `Community.tsx`, `Sludge.tsx` and
`ScienceSimulation.tsx` still fall back to generic copy on an empty site list.

So it is no longer true that the RLS flip cannot be validated by looking at the
app — but validate it on a screen from §4, not on the sidebar.

### c. The swallows now mask denials

The `except Exception: return []` / `False` / `0` handlers in the 8 scoped
functions are unchanged and pre-existing — but they are load-bearing in a way
they were not before, because these functions can now actually be denied. Same
trap the suite already warns about: an empty result set is not evidence of
tenancy.

### d. L1 — leave `SCOPE_ENFORCEMENT` off

Unchanged from the previous handoff; the recommendation is still the status quo.
`user_site_assignments` has never been written to, no backfill exists, and zero
assignments resolves to an empty frozenset that denies everything. `GET /sites`
is the consequential call site, and admins are hit harder than operators.
Prerequisites before the default could flip: confirm `007` is applied; write the
backfill; give the frontend an empty-scope state (see §7b — same gap); assign
sites at invite time; make the flag per-org rather than a process-wide env var.

### e. ~~`/status/{site}` 500s on a partially-filled reading~~ — FIXED `4892237`

Fixed after this handoff was first written. Both crash sites are guarded, and
an incomplete reading now reports **INCOMPLETE**, never COMPLIANT — averaging
over only the parameters that happen to be present would have called one
measured value out of ten "100% COMPLIANT". `bloom_probability` is None rather
than 0.0 when Chl-a is unmeasured, and unevaluated alert drivers are named so a
GREEN reading on missing data is distinguishable from a healthy one.

**The lesson is worth more than the fix.** Guarding `check_compliance` was not
enough: `_assess` also calls `evaluate_alert_level`, which had the same
unguarded comparisons. All ten unit tests passed while the endpoint still 500'd,
because the test helper happened to set `chla`. Only re-running the real
end-to-end reproduction against a NULL-metric row exposed the second site. The
original text below is kept because the reasoning still applies.



Found while verifying §2.1, unrelated to the token work, and still open.

`core/calculations.py:32` does `value < lim.max_val` with no None guard:

```
TypeError: '<' not supported between instances of 'NoneType' and 'int'
```

Isolated both ways: a reading with `cod, ammonia, phosphate, turbidity,
oil_grease, ecoli` NULL raises; fill them and `_assess` returns
`COMPLIANT / 100.0 / alert 2`. Lines 24 and 28 have the same shape.

This is reachable in production — `insert_reading` takes a partial `fields`
dict, so any partially-filled reading takes `/status/{site}` down with a 500.
Left for its own commit rather than smuggled into the RLS work.

### f. Residual items recorded elsewhere

- `SECURITY_REVIEW_COMPLIANCE.md` — H1, H2, M1, M2, M3, L2, L3, L4 fixed; L1
  open by choice. The PLAUSIBLE section (CORS `*`, `evaluate` trusting one
  stored value, module `notes` exposure) was never worked.
- No write path is scoped at all
  (`PERMISSIONS_IMPLEMENTATION_STATUS.md:27`).
- `/users/invite` is audited but not rate-limited, and email matching is
  `strip().lower()` only, so plus-addressing can still produce two pending rows
  for one address (noted in `ca4376e`).
- `app.py` is a **parallel Streamlit UI on Supabase GoTrue auth, not Clerk** —
  a second identity system in the repo. `app.py:84` is the one pre-existing
  caller that passed a token. Do not conflate it with the Clerk path when
  reasoning about tokens; `api_server.py` is the real request path.
- The frontend has **no central fetch wrapper** — 24 components hand-roll
  `Authorization: Bearer` headers, so there is no chokepoint and a new call site
  can silently omit auth. Three unauthenticated calls are legitimately public
  (`/api/version` ×2, `/api/access-request`).

---

## 8. The v1.9.0 release is half-cut — finish it before anything else

`scripts/release.sh auto` chose **minor → v1.9.0** (48 commits since v1.8.0, many
`feat:`; the script's default is `patch`, which would have been wrong). It got as
far as:

- `VERSION` and `frontend/package.json` → 1.9.0
- CHANGELOG section written
- commit `e675f3e chore(release): v1.9.0`

Then it **stalled and was killed**. `tag.gpgsign = true` in the user's global
`~/.gitconfig` (key `CF222D00358DC9E9`), so `git tag -a` needs a GPG passphrase
and a non-interactive shell has no TTY to prompt on. The log ends with
`error: unable to sign the tag`.

**The tag does not exist and nothing is pushed.** To finish, in an interactive
terminal:

```bash
git tag -a v1.9.0 -m "Release v1.9.0"
git push origin feat/dm-compliance-phase-1 --follow-tags
```

**Do NOT re-run `scripts/release.sh`** — the release commit already exists, so it
would bump to v1.10.0. A dry run confirms it now offers exactly that.

Signing was not bypassed with `--no-sign`. Signed tags are a deliberate choice
of the repo owner's and not something to work around; if an unsigned tag is
acceptable, that needs to be said explicitly.

---

## 9. This repo is a fork of the LOS/DECCA build, and inherited its identity

**Read this before running any script that talks to the outside world.**
`C:\AI\DM-Tech-Apps` was created by copying the completed build at
`C:\AI\LOS`, and the copy brought the parent's constants with it. The repo
owner spotted this; the release script had already been run without reading them.

| Constant | Pointed at | What it would do |
|---|---|---|
| `REPO_URL` in `scripts/release.sh` | `garyduwyanemorgan/DECCA-Lagoons-App` | Wrote CHANGELOG compare links into the frozen repo — 24 of them, every release since v1.6.0 |
| `API_URL` in `scripts/release.sh` | `lagoons.gdm-enviro.com` | `--verify` polls it to decide whether THIS release is live. A green verify would have been **the other app answering** |
| `RENDER_SERVICE` | `srv-d91t1ofavr4c73fv52d0` (`lagoon-saas`) | Printed in the rollback hint on a failed verify — a command naming another project's service, pasted during an incident |
| `create_checkout_webhook.py`, `create_stripe_webhook.py` | `lagoons.gdm-enviro.com` | Registers a **payment provider webhook** against a host this deployment does not control |

Nothing reached the other project: the push targets `origin` (DM-Tech-Apps),
`--verify` was never passed, and neither webhook script was run. Real damage was
24 dead links, now repointed.

`REPO_URL` is now **derived** from `git remote get-url origin`, so a future fork
cannot inherit a stale identity the same way. `RELEASE_VERIFY_URL` and
`PUBLIC_BASE_URL` are now **required with no default** — the first fix defaulted
them to `https://app.gdm-enviro.com`, inferred from `CLERK_AUTHORIZED_PARTIES`,
and a DNS check showed **that host has no record at all**. A default pointing at
another project and a default that cannot resolve are the same mistake: letting
a script run against a host nobody verified. There is no safe default, so there
is none.

### Still carrying the parent's identity — a decision, not an oversight

`render.yaml:13` declares `name: lagoon-app`, and its header comment names
`lagoons.gdm-enviro.com` as the custom domain. **Left deliberately unchanged.**
Renaming a service in a Render Blueprint does not rename the running service —
Render treats it as a new one and can orphan the existing deployment. That needs
an explicit decision by someone who can see the Render dashboard.

### Where this app actually runs

Verified 2026-08-17: **localhost only.** API on `127.0.0.1:8010` and Vite on
`[::1]:5173`, both loopback. Neither `app.gdm-enviro.com` (no DNS record) nor
`lagoons.gdm-enviro.com` (resolves to a Render address, serves nothing) answers,
and outbound connectivity from this machine works, so those are real results.

Two caveats. The **Supabase containers bind `0.0.0.0`** — gateway 54321, Postgres
54322, pooler 6543 — so they are reachable from the local network, unlike the app
itself. And it could **not** be verified from here whether a Render service is
connected to this repo with auto-deploy; `render.yaml` says Render deploys on
push, and this branch was pushed several times on 2026-08-17. Check the Render
dashboard.

---

## 10. Gotchas worth not rediscovering

- **The gateway is port 54321.** Port 8000 is container-internal and 404s from
  the host.
- **`docker exec supabase-rest` is broken**; use `docker inspect` (§6).
- **`db/queries.py` does `from .client import get_client`**, binding the name
  into the queries module. Patching `db.client.get_client` alone leaves tests
  talking to the live stack and passing for the wrong reason — patch both. See
  `_patch_client` in `tests/test_scope_resolution_failure.py`.
- **A test that asserts an empty result may be asserting a swallowed failure.**
  Against a fail-closed system an empty result set makes a broken database look
  like a secure one — assert the caller sees their *own* row first, as
  `tests/test_rls_clerk_identity.py` does.
- **Run tests against a reverted implementation before believing them.** Both
  agents and humans have written tests here that passed for the wrong reason.
  12-of-17 failing on revert is what "the test works" looks like. **Confirm the
  mutation actually landed** — a replacement that silently fails to match leaves
  everything passing, which looks exactly like a successful verification.
- **`uvicorn` here runs without `--reload`.** Editing Python and re-testing
  against a running server tests the OLD code. This wasted a verification round:
  a stale process on `:8010` answered without the new middleware and the header
  looked missing. Kill the PID on the port and restart after every change.
- **Vite binds IPv6 only.** `curl http://127.0.0.1:5173` returns nothing;
  `localhost` works. A `000` response code is this, not a dead server.
- **Fixing the frame in the traceback may not fix the bug.** The partial-reading
  500 had two crash sites; guarding the first left the endpoint still failing,
  and the unit tests passed because the fixture set the field the second site
  read. Re-run the original end-to-end reproduction, not just the tests.
- **Read a script's constants before running it.** This repo is a copy of the
  LOS/DECCA build (§9) and inherited that project's repo URL, production host,
  Render service id and payment-webhook base URL. Checking *where a release
  pushes* is not the same as checking *what the script thinks it is releasing*.
- **`git checkout -- <file>` discards uncommitted work.** Used it to undo a
  mutation test and it wiped the real, uncommitted fix in the same file. Back up
  to a scratchpad and restore from there.
- **A mutation test can pass for two different wrong reasons**: the replacement
  string did not match, or it matched and changed no behaviour. Both look
  identical to a green suite. Assert the mutation landed, then assert it altered
  semantics.
- **Test the payload, not your own logic.** The Sentry scrubber passed 15 unit
  tests while the real SDK still shipped every probe secret, because the values
  also live in the source lines the SDK attaches. Capture a real event through
  the real library and grep what would go on the wire.
- **No `load_dotenv` exists anywhere in the Python source.** `.env` is read by
  `core/config.py:secret()` at call time, not loaded into the process
  environment. `secret(section, key)` derives the env name mechanically
  (`SECTION_KEY.upper()`), so a new secret needs no declaration — that is why
  `SUPABASE_ANON_KEY` worked with no change to `core/config.py`.
