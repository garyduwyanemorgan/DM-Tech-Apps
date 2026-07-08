# SaaS Stack Gotchas & Fixes — Proactive Checklist for Claude

> **Purpose:** A portable record of every error/fix worked through on the Compliance-Lagoons
> SaaS app. Drop this into any app on the same stack. When Claude opens that app, it
> should **read this file first and proactively verify each "Proactive check"** before
> deploying or debugging — most of these are silent footguns that only surface in
> production or at runtime.
>
> **Stack this applies to:** React + Vite (TypeScript) frontend · FastAPI (Python) backend
> that *also serves the built SPA* (unified app) · Supabase (Postgres + PostgREST) ·
> Clerk (auth/JWT) · Stripe (billing) · Render (host) · optional Vercel · Windows + PowerShell dev.
>
> **No secrets are in this file.** Keep it that way.

---

## 0. Fast pre-deploy checklist (run these before shipping)

- [ ] Code you tested locally is **committed AND pushed** to the branch the host builds from.
- [ ] The host (Render/etc.) is connected to the **correct repo** (matches `git remote get-url origin`).
- [ ] Every secret read from `secrets.toml` **also has an env-var fallback** (hosts have no `secrets.toml`).
- [ ] All required env vars are set on the host (Supabase, Clerk, Stripe, Anthropic, `VITE_*` for the frontend build).
- [ ] API routes the frontend calls (`/api/...`) actually exist on the deployed build (curl them).
- [ ] DB migrations are applied on the target Supabase project (don't assume).
- [ ] Stripe webhook URL points at the live app **with the correct path prefix**.

---

## 1. Local dev — ports, processes, Windows/PowerShell

### 1.1 `localhost` hits the wrong server (IPv6 vs IPv4)
- **Symptom:** API returns 404/“Not Found” via `localhost:8000` but works on `127.0.0.1:8000`.
- **Root cause:** On Windows `localhost` resolves to IPv6 `::1` first. A stale process (e.g. an old **Docker container**) was bound to `::8000` while the new server bound `0.0.0.0:8000` (IPv4 only). Requests silently hit the old one.
- **Fix:** Stop the stale listener (`docker ps --filter publish=8000`, `docker stop <name>`); test with `127.0.0.1` to force IPv4.
- **Proactive check:** `Get-NetTCPConnection -LocalPort <port>` — if both `::` and `0.0.0.0` are listening, you have two servers. Bind/test explicitly on `127.0.0.1`.

### 1.2 Port already in use — `[Errno 10048] / WinError 10048`
- **Symptom:** `only one usage of each socket address ... is normally permitted` on server start.
- **Root cause:** A previous server process is still holding the port.
- **Fix:** `Get-NetTCPConnection -LocalPort <port> -State Listen | %{ Stop-Process -Id $_.OwningProcess -Force }` then restart.

### 1.3 PowerShell can’t background with `&`
- **Symptom:** `The ampersand (&) character is not allowed.`
- **Root cause:** `cmd &`/bash backgrounding isn’t valid PowerShell.
- **Fix:** Use the runner’s real background mechanism (or `Start-Process`), not a trailing `&`.

### 1.4 git: “dubious ownership”
- **Symptom:** `fatal: detected dubious ownership in repository`.
- **Root cause:** Repo dir owned by `Administrators` while you run as a normal user.
- **Fix:** `git config --global --add safe.directory <path>`.

### 1.5 git/native stderr looks like a PowerShell “error”
- **Symptom:** `git push` shows a red PowerShell error block but the push succeeded (`... -> main`).
- **Root cause:** git writes progress to **stderr**; PowerShell wraps stderr as `NativeCommandError` even on exit 0.
- **Proactive check:** Read the actual result line (e.g. `<old>..<new>  main -> main`), not the PS wrapper. Don’t redirect native stderr in PS 5.1.

---

## 2. Build & config (Vite / env vars / secrets)

### 2.1 `npm run dev -- --port 5173` is silently ignored
- **Symptom:** `npm warn Unknown cli config "--port"`, vite serves from a folder named `5173`, every route 404s.
- **Root cause:** npm swallowed `--port`; vite received `5173` as a **positional root dir**.
- **Fix:** Set the port in `vite.config.ts` (`server: { port: 5173, strictPort: true }`), run plain `npm run dev`.

### 2.2 Vite dev proxy strips the `/api` prefix
- **Symptom:** Frontend `/api/*` calls 404 in dev against a backend that serves under `/api`.
- **Root cause:** `proxy['/api'].rewrite = p => p.replace(/^\/api/, '')` removed the prefix the backend expects.
- **Fix:** Only rewrite if the backend serves at root. If the backend mounts under `/api`, **do not** rewrite.
- **Proactive check:** Match the proxy rewrite to the backend’s mount prefix (see §3.1).

### 2.3 Frontend env var missing at build time
- **Symptom:** Console: `Missing VITE_CLERK_PUBLISHABLE_KEY`; auth UI broken.
- **Root cause:** `VITE_*` vars are **baked in at build time**, read from `frontend/.env.local` locally and from host build env vars in CI/host. Easy to forget on a new machine/host.
- **Fix:** Create `frontend/.env.local` locally; set `VITE_*` as a build env var on the host. Rebuild after changing.

### 2.4 Config/secret files absent on a fresh machine
- **Symptom:** App falls back to sample data / Stripe “not configured” / DB not connecting.
- **Root cause:** `secrets.toml` and `.env.local` are git-ignored (correctly) — they don’t arrive with a clone.
- **Fix:** Recreate them from the setup bundle. **Never commit them.** Verify with `git check-ignore <file>`.

### 2.5 Missing Python deps not in the obvious place
- **Symptom:** `ModuleNotFoundError: stripe` / multipart upload route 500s.
- **Root cause:** Some deps (`stripe`, `python-multipart` for `UploadFile`) weren’t installed / not pinned.
- **Fix:** `pip install -r requirements.txt` **and** ensure `python-multipart` is present if any endpoint uses file uploads.

---

## 3. Frontend ↔ Backend routing

### 3.1 Know your API mount prefix: `/api/*` vs root `/*`
- **Symptom:** `/api/health` 404 but `/health` 200 (or vice-versa) depending on the build.
- **Root cause:** Two app shapes coexisted: an **inner** FastAPI app (routes at root) and a **unified outer** app that mounts the inner one under `/api` *and* serves the SPA. Deploys/proxies/webhooks must agree on which one is running.
- **Proactive check:** `curl https://<host>/api/health` AND `curl https://<host>/health`. Whichever answers tells you the prefix. Make the Vite proxy, the Vercel rewrite, and the Stripe webhook path all match it.

### 3.2 `Unexpected token '<', "<!DOCTYPE"... is not valid JSON`
- **Symptom:** Frontend throws this when calling an API.
- **Root cause:** `fetch('/api/...')` got **HTML, not JSON**. Two common reasons:
  1. The request fell through to the **SPA catch-all** (route not under the API mount, or wrong prefix) → `index.html` returned.
  2. The service was **mid-deploy / cold-starting** and the host returned its own HTML 502/holding page.
- **Fix / Proactive check:**
  - Confirm the endpoint exists and is under the right prefix (§3.1).
  - In the frontend, **guard `res.json()`**: check `res.ok` and `content-type` includes `application/json` before parsing; surface a clean error otherwise.
  - During/just after a deploy, expect transient HTML — retry/hard-refresh.

---

## 4. Deployment (Render / Vercel / “rebuild”)

### 4.1 Host builds from the WRONG repo (the big one)
- **Symptom:** Deployed backend is missing endpoints you know exist (`/profile`, `/billing`, `/users` → 404), behaves like an older app.
- **Root cause:** The host service was connected to a **different/older repository** than your local code (e.g. `*-dashboard` vs `*-app`). Auto-deploys were updating a repo you weren’t editing.
- **Fix:** Point the service at the correct repo, or create a new service from the right repo. Confirm the **deployed commit** matches local.
- **Proactive check:** Compare `git remote get-url origin` against the host service’s connected repo, and the host’s **last deployed commit hash/message** against `git log -1`.

### 4.2 The code you tested was never committed
- **Symptom:** Deploy builds a structure different from what runs locally (e.g. routes at root instead of `/api`, no SPA served).
- **Root cause:** A refactor (e.g. the unified outer app) lived only in the **working tree**; `origin/main` still had the old structure.
- **Fix:** `git status` before deploying; commit + push what you actually tested. Verify with `git diff origin/main`.

### 4.3 Vercel (serverless) can’t run a persistent FastAPI process
- **Symptom:** Expectation that `vercel deploy` runs the FastAPI server like Render does.
- **Root cause:** Vercel runs static sites + **serverless functions**, not always-on processes. A unified FastAPI+SPA app doesn’t map without restructuring.
- **Options (no code rewrite):** keep a persistent-process host (Render/Railway/Koyeb/Cloud Run), OR add a **Dockerfile** (packaging only — zero app-code changes) and deploy the image anywhere. Use Vercel only for the static frontend, rewriting `/api/*` to the backend host.
- **Proactive check:** If asked to “put the backend on Vercel/Supabase”, remember: Supabase Edge Functions are **Deno/TS** (can’t run Python), and Vercel needs serverless restructuring. A Dockerfile + container host is the no-rewrite path.

### 4.4 Heavy build needs Node available for the frontend step
- If the backend host builds the SPA (`npm --prefix frontend run build`) inside a Python runtime, confirm Node is available in that build image, or build the frontend separately / via Docker.

---

## 5. Auth (Clerk / JWT / new users)

### 5.1 Clerk JWKS resolved only from `secrets.toml`
- **Symptom:** Login works client-side but the backend treats the user as unauthenticated (`/profile` returns operator/None); server-side JWT verification silently fails on the host.
- **Root cause:** The instance JWKS URL is derived from the Clerk **publishable key**, which was read only from `secrets.toml`. On a host without that file it fell back to a generic/wrong JWKS endpoint → tokens never validated.
- **Fix:** Add an env-var fallback (`CLERK_PUBLISHABLE_KEY`) and set it on the host. Keep `secrets.toml` precedence for local.
- **Proactive check:** Grep for any secret read that opens `secrets.toml` with **no** `os.environ` fallback — every one of those breaks on the host.

### 5.2 New uninvited user has no organization (can’t use the app)
- **Symptom:** First-time user is a “pending” super_admin with `organization_id = NULL`; can’t create sites or reach billing.
- **Root cause:** First-login logic created the profile with `organization_id = None` and no org-creation path existed for self-serve signups.
- **Fix:** On first login (and for any user left without a role/org), **auto-provision a personal organization** with sane billing defaults and link the profile to it.
- **Proactive check:** Trace the “user with no profile / no role” branch of the auth dependency — make sure it ends with a usable org, not a dead-end pending state.

---

## 6. Database (Supabase / PostgREST / migrations)

### 6.1 A migration was never applied on the target project
- **Symptom:** `PGRST204: Could not find the '<col>' column of '<table>' in the schema cache`. Writes that touch those columns silently no-op.
- **Root cause:** `001_billing.sql` (and similar) adds columns via `ALTER TABLE`, but it was never run on this Supabase project. Don’t assume migrations are applied.
- **Fix:** Run the migration in **Supabase → SQL Editor** (service_role/PostgREST **cannot run DDL**). Then PostgREST reloads its schema cache automatically.
- **Proactive check:** `GET /rest/v1/<table>?limit=1` and inspect the returned keys to confirm expected columns exist before relying on them.

### 6.2 Arithmetic/logic on a missing-or-NULL column → 500
- **Symptom:** Endpoint 500s with `TypeError: '<' not supported between 'int' and 'NoneType'` (e.g. `sites_used < site_limit` where `site_limit` is NULL/absent).
- **Root cause:** `dict.get('k', default)` returns `None` when the key exists with a NULL value (default only applies to *missing* keys); and absent columns read as None.
- **Fix:** **Coalesce** at the read boundary: `value = data.get('site_limit') or DEFAULT`. Make insert helpers set explicit defaults, with a **fallback insert** when the columns don’t exist yet.
- **Proactive check:** Any code doing comparisons/math on a DB-sourced number should coalesce NULL → default first.

### 6.3 PostgREST URL encoding
- **Symptom:** `http.client.InvalidURL: URL can't contain control characters` when filtering by a value with spaces/apostrophes.
- **Root cause:** Filter values (e.g. `name=eq.Some Org's Workspace`) weren’t URL-encoded.
- **Fix:** `urllib.parse.quote()` (or the client lib) on all query-string filter values.

---

## 7. Stripe (billing)

### 7.1 Webhook URL/path stale or missing the API prefix
- **Symptom:** Subscriptions/plan changes don’t reflect in the app; webhook deliveries fail.
- **Root cause:** Webhook endpoint pointed at an old domain and/or `/billing/webhook` without the `/api` prefix the unified app uses.
- **Fix:** Update the **existing** webhook endpoint’s URL in place (keeps the same signing secret → no env-var change) to `https://<app>/api/billing/webhook`. Confirm `STRIPE_WEBHOOK_SECRET` on the host matches that endpoint.
- **Proactive check:** `POST /api/billing/webhook` (unsigned) should return **400** (route live, signature rejected), not 404. List `webhook_endpoints` and verify the URL/prefix.

### 7.2 Live Checkout blocked until a business/account name is set
- **Symptom:** `InvalidRequestError: In order to use Checkout, you must set an account or business name at https://dashboard.stripe.com/account`.
- **Root cause:** Stripe requires the account to have a business/account name before any **live** Checkout session can be created. Not a code bug.
- **Fix (account owner):** Set the name in the Stripe Dashboard → Account/Business settings. No code change.

### 7.3 Customer not persisted → duplicate Stripe customers
- **Symptom:** A new Stripe customer is created on every checkout attempt.
- **Root cause:** `get_or_create_customer` saves `stripe_customer_id` via an UPDATE that silently failed because the column didn’t exist (see §6.1).
- **Fix:** Apply the billing migration; once the column exists, the customer ID persists and is reused.

### 7.4 Test vs Live keys
- **Symptom / risk:** A **live** Stripe secret key (`sk_live_…`) on a dev/staging box risks real charges.
- **Proactive check:** On non-production, prefer `sk_test_…`. Flag any `sk_live_…` found in a dev config. Never enter card/payment details on the user’s behalf — generating a Checkout URL is fine; completing payment is the user’s action.

---

## 8. General principles distilled

1. **Hosts have no `secrets.toml`.** Every secret needs an env-var fallback, and every env var must be set on the host.
2. **Deploy what you tested.** Commit + push first; verify the host builds the right repo and the right commit.
3. **Agree on the API prefix** across proxy, rewrite, frontend fetches, and webhook path.
4. **Never assume DB state.** Check columns/migrations before relying on them; coalesce NULLs.
5. **HTML where JSON is expected = wrong route or mid-deploy.** Guard `res.json()`.
6. **Some blockers are account settings, not code** (Stripe business name, GitHub/host repo access, DB DDL must run in the SQL editor).
7. **Serverless ≠ persistent process.** A Dockerfile keeps you portable with zero code rewrite.
