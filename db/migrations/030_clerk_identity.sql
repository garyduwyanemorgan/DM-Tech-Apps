-- ── 030: re-key the RLS identity helpers onto the Clerk subject ──
--
-- 029 fixed WHAT the policies test. This fixes WHO they test it against.
--
-- Every policy in this schema resolves the caller through two helpers:
--
--     get_user_organization()  ->  SELECT organization_id FROM user_profiles
--                                   WHERE id = auth.uid()
--     get_user_role()          ->  SELECT role            FROM user_profiles
--                                   WHERE id = auth.uid()
--
-- `auth.uid()` is the subject of a **Supabase** JWT. This application
-- authenticates with **Clerk**: api_server.py verifies Clerk tokens against
-- Clerk's JWKS, and 002_clerk.sql dropped user_profiles' foreign key to
-- auth.users precisely so that Clerk could own identity. Profiles are keyed on
-- `clerk_id TEXT UNIQUE`, and `user_profiles.id` is now an independent surrogate
-- key that corresponds to no Supabase auth user at all.
--
-- So `WHERE id = auth.uid()` matches nothing, for everyone, always. Both helpers
-- return NULL, every predicate built on them is false, and all 50 policies 029
-- left behind are inert. 029's own header and db/migrations/README.md both name
-- this re-keying as the prerequisite for any client-side Supabase access, and
-- both insist it happen AFTER 029 — which it now does. Doing it before would
-- have activated the cross-tenant super_admin clauses instead of the fixed ones.
--
-- WHAT CHANGES
--
-- The helpers resolve `clerk_id = auth.jwt() ->> 'sub'` instead. `sub` is the
-- Clerk user id (`user_…`), which is exactly what api_server.py already stores
-- in clerk_id when it provisions a profile, and clerk_id carries a UNIQUE index
-- so the lookup is a single index probe.
--
-- THE THREE auth.uid() POLICIES
--
-- Three policies compare auth.uid() directly rather than through a helper, and
-- are broken in a second, subtler way:
--
--     user_profiles.select_profiles          id             = auth.uid()
--     certificates.select_certificates       subject_user_id = auth.uid()
--     people_credentials.select_…            subject_user_id = auth.uid()
--
-- These are "and you may always see your own row" arms. But subject_user_id is
-- a foreign key to user_profiles(id) — a surrogate uuid — while auth.uid() is a
-- Supabase auth uuid. The two uuid spaces are unrelated, so this is not merely
-- NULL-vs-value: it is a type-correct comparison between values that can never
-- coincide. A new helper, get_user_profile_id(), returns the caller's OWN
-- user_profiles.id, and the three policies compare against that.
--
-- Without this, re-keying the other two helpers would silently REMOVE access:
-- an individual could no longer read their own credential and certificate rows,
-- which is the one arm of those policies that exists for the data subject rather
-- than the employer.
--
-- WHY THE FUNCTION BODIES ALSO CHANGE SHAPE
--
-- All three helpers are declared `STABLE` and `SET search_path`. Neither is
-- cosmetic:
--
--   STABLE — the existing helpers are plpgsql and therefore VOLATILE by default.
--   Postgres cannot hoist a VOLATILE call out of a row filter, so it re-runs the
--   query ONCE PER ROW SCANNED on every policy-checked table. STABLE lets the
--   planner evaluate it once per statement, which for a table scan under RLS is
--   the difference between one index probe and a hundred thousand.
--
--   SET search_path — these are SECURITY DEFINER functions with no fixed
--   search_path, the standard privilege-escalation shape: a caller who can
--   create objects in a schema earlier on their own search_path can shadow
--   `user_profiles` and make the helper read a table of their choosing while it
--   runs as the definer. Pinning it closes that off.
--
-- SECURITY DEFINER itself is retained deliberately. user_profiles has RLS
-- enabled and its own select_profiles policy calls get_user_organization(); if
-- the helper ran as the invoker it would re-enter that policy and recurse.
-- Running as the definer reads the table directly and terminates.
--
-- WHAT THIS DOES NOT DO, AND WHAT MUST HAPPEN OUTSIDE POSTGRES
--
-- This migration does not switch the backend off service_role. db/client.py
-- still connects with SERVICE_ROLE_KEY, which bypasses RLS entirely, so applying
-- this changes NOTHING about how the application behaves today. That is
-- intentional: the policies become correct before anything is asked to depend on
-- them.
--
-- Before a client can hold a Clerk token that these policies understand, two
-- things must be configured in Clerk — neither expressible in SQL:
--
--   1. Supabase must accept Clerk as a JWT issuer (third-party auth), so that a
--      Clerk session token is honoured and `request.jwt.claims` is populated
--      from it. Self-hosted: the GOTRUE/JWT issuer settings in
--      C:\AI\supabase\docker\.env.
--   2. The Clerk session token must carry `"role": "authenticated"`, or PostgREST
--      keeps the caller as `anon` and every policy in this schema fails closed
--      regardless of the subject.
--
-- Until both are done, `auth.jwt()` is NULL for real users and these helpers
-- return NULL — the same fail-closed result as today, reached honestly. Verify
-- with tests/test_rls_clerk_identity.py, which sets the claim directly and
-- asserts the helpers resolve.
--
-- No table, column, index or grant changes. Functions and three policies only.

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════
-- PART 1 — The Clerk subject
-- ═══════════════════════════════════════════════════════════════════════════

-- The calling Clerk user id, or NULL when there is no usable token.
--
-- auth.jwt() returns NULL when request.jwt.claims is unset (no request context:
-- psql, a CLI loader, a background job), and `NULL ->> 'sub'` is NULL, so this
-- is null-safe without a guard. The nullif() collapses a present-but-empty sub
-- to NULL as well, so that a malformed token cannot match a row whose clerk_id
-- was somehow written as ''. Every caller below treats NULL as "no identity",
-- which fails closed.
CREATE OR REPLACE FUNCTION public.clerk_subject()
  RETURNS text
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$
  SELECT nullif(auth.jwt() ->> 'sub', '');
$$;

COMMENT ON FUNCTION public.clerk_subject() IS
  'Clerk user id (JWT sub) of the caller, or NULL. Identity root for all RLS.';

-- ═══════════════════════════════════════════════════════════════════════════
-- PART 2 — The three identity helpers
-- ═══════════════════════════════════════════════════════════════════════════

-- Was: SELECT organization_id FROM user_profiles WHERE id = auth.uid()
CREATE OR REPLACE FUNCTION public.get_user_organization()
  RETURNS uuid
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$
  SELECT organization_id
    FROM public.user_profiles
   WHERE clerk_id = public.clerk_subject();
$$;

COMMENT ON FUNCTION public.get_user_organization() IS
  'Organisation of the calling Clerk user, or NULL. Tenant boundary for RLS.';

-- Was: SELECT role FROM user_profiles WHERE id = auth.uid()
CREATE OR REPLACE FUNCTION public.get_user_role()
  RETURNS text
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$
  SELECT role
    FROM public.user_profiles
   WHERE clerk_id = public.clerk_subject();
$$;

COMMENT ON FUNCTION public.get_user_role() IS
  'Tenant role of the calling Clerk user, or NULL. One of super_admin, admin, '
  'operator, auditor — all TENANT roles; none of them denotes vendor staff.';

-- New. The caller's own user_profiles.id, for the "your own row" policy arms.
CREATE OR REPLACE FUNCTION public.get_user_profile_id()
  RETURNS uuid
  LANGUAGE sql
  STABLE
  SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$
  SELECT id
    FROM public.user_profiles
   WHERE clerk_id = public.clerk_subject();
$$;

COMMENT ON FUNCTION public.get_user_profile_id() IS
  'user_profiles.id of the calling Clerk user, or NULL. Compare FK columns '
  'that reference user_profiles(id) against this, never against auth.uid().';

GRANT EXECUTE ON FUNCTION public.clerk_subject()          TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.get_user_organization()  TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.get_user_role()          TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.get_user_profile_id()    TO authenticated, anon;

-- ═══════════════════════════════════════════════════════════════════════════
-- PART 3 — The three policies that compare auth.uid() directly
-- ═══════════════════════════════════════════════════════════════════════════

-- ── user_profiles (schema_rls.sql, org arm rewritten by 029) ──
-- The second arm lets a user read their own profile row even when their
-- organization_id is NULL — which is the state api_server.py leaves an invited
-- profile in until it is claimed, so losing this arm would break the invite
-- flow, not merely self-reads.
DROP POLICY IF EXISTS select_profiles ON public.user_profiles;
CREATE POLICY select_profiles ON public.user_profiles
  FOR SELECT USING (
    organization_id = public.get_user_organization()
    OR id = public.get_user_profile_id()
  );

-- ── certificates (028) ──
-- subject_user_id REFERENCES user_profiles(id): the individual the certificate
-- is about. They may read it regardless of which organisation holds it, which
-- matters when a credential outlives the employment that recorded it.
DROP POLICY IF EXISTS select_certificates ON public.certificates;
CREATE POLICY select_certificates ON public.certificates
  FOR SELECT USING (
    organization_id = public.get_user_organization()
    OR subject_user_id = public.get_user_profile_id()
  );

-- ── people_credentials (028) ──
-- Same data-subject arm. Note the employer arm is deliberately narrower than on
-- certificates — admin/super_admin only, scoped to the organisation — because
-- these rows are personal data about named individuals. 029 set that; only the
-- subject arm is re-keyed here.
DROP POLICY IF EXISTS select_people_credentials ON public.people_credentials;
CREATE POLICY select_people_credentials ON public.people_credentials
  FOR SELECT USING (
    subject_user_id = public.get_user_profile_id()
    OR (
      organization_id = public.get_user_organization()
      AND public.get_user_role() IN ('admin', 'super_admin')
    )
  );

COMMIT;
