# SaaS Setup Skill — Dubai Lagoons Compliance Platform

> Purpose: hand this file to Claude to assist with **finalizing the SaaS setup**
> (Clerk auth + Supabase multi-tenancy + Stripe per-site billing). It records the
> architecture, the integration steps already completed, the non-obvious gotchas
> that cost real debugging time, and the outstanding work to reach production.
>
> Last updated: 2026-06-30. Secrets are referenced by location, never by value.

---

## 1. Architecture at a glance

| Layer | Tech | Location | Port |
|-------|------|----------|------|
| Frontend | Vite + React 19 | `frontend/` | 5173 (falls back to 5174) |
| Backend API | FastAPI | `api_server.py` | 8000 |
| Database | Supabase (Postgres + RLS) | project ref `aahekvsznsceqkmtcnhl` | — |
| Auth | Clerk (`@clerk/react`) | frontend + backend JWT verify | — |
| Billing | Stripe per-site | `billing.py` | — |

- Frontend dev server proxies `/api/*` → `http://localhost:8000` (see `frontend/vite.config.ts`, rewrites `^/api` → ``).
- Backend reads Supabase + Clerk + Stripe config from `.streamlit/secrets.toml`.
- Frontend reads `VITE_CLERK_PUBLISHABLE_KEY` from `frontend/.env.local`.

### Secret locations (do NOT print values)
- `.streamlit/secrets.toml` → `[supabase]` (url + service_role key), `[clerk]` (publishable + secret), `[stripe]` (secret_key, webhook_secret, price IDs).
- `frontend/.env.local` → `VITE_CLERK_PUBLISHABLE_KEY`.

---

## 2. Auth model (Clerk → Supabase profiles)

Identity is owned by **Clerk**; authorization (role + org) lives in Supabase
`user_profiles`. The two are joined by `clerk_id`.

### `user_profiles` schema (after migration `db/migrations/002_clerk.sql`)
- `id UUID` (PK, no longer FK to `auth.users`)
- `clerk_id TEXT UNIQUE` — Clerk user id (`user_...`), primary lookup key
- `email TEXT` — used to match a pending invite to a Clerk user on first sign-in
- `organization_id UUID` → `organizations.id` (nullable)
- `role TEXT` ∈ `super_admin | admin | operator | auditor`

### Request flow
1. Browser signs in via Clerk `<SignIn />` (`frontend/src/components/Login.tsx`).
2. `AuthContext.tsx` calls `getToken()` and fetches `/api/profile` with headers:
   - `Authorization: Bearer <clerk_jwt>`
   - `X-User-Email: <primary email>`  ← needed because the default Clerk session token has **no email claim**.
3. Backend `get_current_user_profile` (dependency in `api_server.py`):
   - `get_user_from_token` verifies the JWT against the Clerk **instance JWKS**.
   - `get_user_profile` looks up by `clerk_id`; if none, matches a pending invite by `email` (where `clerk_id IS NULL`) and links it.
   - If still no profile → **new uninvited user → auto-create `super_admin`**.

### Role assignment rules (product requirement)
- **New user, no invite (incl. social login)** → `super_admin`, `organization_id = NULL`.
- **Invited user** → keeps the role the host set on the pending profile; `clerk_id` linked on first sign-in.
- **Returning user** → existing role kept.

---

## 3. Steps already completed

### Frontend
- `npm install @clerk/react`; **removed** `reactjs-social-login` (React 19 peer conflict; Clerk does social natively) and frontend `@supabase/supabase-js`. Deleted `frontend/src/supabase.ts`.
- `main.tsx`: wrapped app in `<ClerkProvider publishableKey={...} afterSignOutUrl="/">`.
- `Login.tsx`: replaced custom Supabase form with Clerk `<SignIn />` inside branded header.
- `AuthContext.tsx`: rewritten on `useAuth`/`useUser` from `@clerk/react`; same public interface (`user, loading, role, organizationId, token, signOut`) so downstream components are untouched.

### Backend
- `get_user_from_token`: verifies Clerk JWT via JWKS (PyJWT + cryptography).
- `_clerk_jwks_url()`: derives the per-instance JWKS URL from the publishable key.
- `get_user_profile`: `clerk_id` lookup + email-invite linking.
- `_create_super_admin_profile`: auto-provisions new users.
- `invite_user` (`POST /users/invite`): creates a **pending** profile row (`email` + role + org, `clerk_id` NULL) instead of calling Supabase auth.
- `requirements.txt`: added `PyJWT[crypto]==2.10.1`.

### Database
- `db/migrations/002_clerk.sql` applied in Supabase SQL editor: drop FK `user_profiles_id_fkey`, add `clerk_id` + `email`, drop `on_auth_user_created` trigger.

---

## 4. Gotchas that cost real time (read before debugging)

### 4.1 Clerk JWKS URL — the #1 trap
`https://api.clerk.com/v1/jwks` returns **0 keys** for a frontend instance.
The real keys are at the **instance** URL derived from the publishable key:

```
pk_test_<base64>  →  base64-decode  →  <domain>$  →  strip '$'
JWKS = https://<domain>/.well-known/jwks.json
```
Example domain: `quality-gobbler-20.clerk.accounts.dev`.
If JWKS has 0 keys, **every token silently fails** and users fall through to the
anonymous `operator` fallback (no profile row is created — that's the tell).

### 4.2 Clock skew on short-lived tokens
Clerk session tokens are ~60s with `nbf`/`exp`. PyJWT with no leeway rejects them
on the slightest clock difference. Always decode with `leeway=60` and
`options={"verify_aud": False}` (no `aud`/`iss` set by default).

### 4.3 Stale uvicorn process on Windows
A prior backend was bound to port 8000 under the process name **`python3.11`**,
not `python`. `Stop-Process -Name python` missed it, so the server kept serving
**old code** (old JWKS URL) while edits appeared to do nothing. Symptom:
`[Errno 10048] only one usage of each socket address`. Kill by port/PID:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
# or broadly:
Get-Process | Where-Object { $_.ProcessName -like 'python*' } | Stop-Process -Force
```

### 4.4 PowerShell `$pid` is read-only
Don't assign to `$pid` (reserved automatic var). Use `$procId`.

### 4.5 stderr buffering hides diagnostics
With `--reload` + redirected stderr, `print(..., file=sys.stderr)` may never flush.
For debugging, run **single process, unbuffered**:

```powershell
$env:PYTHONUNBUFFERED = "1"
Start-Process -NoNewWindow -FilePath python `
  -ArgumentList "-u -m uvicorn api_server:app --port 8000" `
  -RedirectStandardError "clerk_auth.log" -RedirectStandardOutput "clerk_out.log"
```
`get_user_from_token` logs `[clerk-auth] token verification failed: ...` on failure.

### 4.6 Billing endpoint shape must be complete
`/billing/status` for a user with **no org** must return the *full* object shape
(`plan_name`, `plan_description`, `available_plans`, `stripe_configured`, …).
A partial body passes the frontend `if (!status) return null` guard and then
**crashes the whole Settings page** on `status.plan_name.toUpperCase()` /
`Object.entries(status.available_plans)`. Frontend now also has defensive defaults.

---

## 5. Operational runbook

```powershell
# Backend (from project root E:\Compliance-lagoons-dashboard)
$env:PYTHONUNBUFFERED = "1"
python -m uvicorn api_server:app --port 8000      # add --reload only when NOT debugging stderr

# Frontend (from frontend/)
npm run dev        # http://localhost:5173 (or 5174)
npm run build      # tsc -b && vite build — run to typecheck the whole app

# Health + smoke
Invoke-WebRequest http://localhost:8000/health
Invoke-WebRequest http://localhost:8000/billing/status   # anonymous = no-org shape
```

### Inspecting / fixing profiles directly (service role bypasses RLS)
```python
import sys; sys.path.insert(0, '.')
from db.client import get_client
c = get_client()
c.table('user_profiles').select('*').execute()          # list
c.table('user_profiles').update({'organization_id': '<org-uuid>'}).eq('clerk_id', 'user_...').execute()
```

### Driving the real `/profile` route end-to-end without Clerk UI
Mint RS256 tokens with a throwaway keypair and inject its public JWK into
`api_server._clerk_jwks_cache`, then hit the route with FastAPI `TestClient`.
This exercises HTTP → JWT verify → DB → response (used to validate all role paths).

---

## 6. Outstanding finalization tasks (the actual TODO)

Priority order for getting to a working paid product:

1. **Org onboarding for new super_admins** — a fresh `super_admin` has
   `organization_id = NULL`, so `site_limit = 0`: they **cannot add sites or
   subscribe**. Need a first-run flow that creates an `organizations` row and
   attaches the user (set `user_profiles.organization_id`). This is the current
   blocker the user hit. Until built, attach manually (see §5).

2. **Server-side email resolution (security)** — `X-User-Email` is set by the
   client. A crafted request (valid JWT for account A + someone else's invited
   email) could claim that invite's role/org. Once the **Clerk secret key** is in
   `[clerk]`, resolve the verified email server-side from the Clerk API using the
   token `sub`, and stop trusting the header for invite matching.

3. **Stripe webhook secret** — `[stripe].webhook_secret` is empty. Set it and
   confirm `POST /billing/webhook` verifies signatures, so plan changes/cancels
   sync. Stripe `secret_key` and price IDs are already populated (LIVE keys — be careful).

4. **Invite email delivery** — `invite_user` creates the pending profile but does
   **not** send an email yet (`TODO` in code). Wire Clerk Invitations API or a
   transactional email provider.

5. **CORS** — `api_server.py` uses `allow_origins=["*"]`. Tighten to the real
   frontend origin(s) before production.

6. **Lower priority audit items** (pre-existing): `list_users` fetches all auth
   users and filters in Python; dead first query in `get_or_create_site_id`;
   `insert_reading` writes redundant `site_name`.

---

## 7. Key files map

| Concern | File |
|---------|------|
| Clerk provider | `frontend/src/main.tsx` |
| Sign-in UI | `frontend/src/components/Login.tsx` |
| Auth context / profile fetch | `frontend/src/context/AuthContext.tsx` |
| JWT verify + role resolution | `api_server.py` (`get_user_from_token`, `get_user_profile`, `get_current_user_profile`, `_create_super_admin_profile`) |
| Profile endpoint | `api_server.py` `GET /profile` |
| Invites | `api_server.py` `POST /users/invite` |
| Billing endpoints | `api_server.py` `/billing/*`; logic in `billing.py` (`PLANS`, `get_org_billing`, `is_configured`) |
| Settings + billing panel | `frontend/src/components/Settings.tsx` |
| Clerk DB migration | `db/migrations/002_clerk.sql` |
| DB client (RLS vs service role) | `db/client.py` |
| Plans/limits | `billing.py` `PLANS` (starter 1 / growth 5 / professional 15 / dev 999-hidden) |
