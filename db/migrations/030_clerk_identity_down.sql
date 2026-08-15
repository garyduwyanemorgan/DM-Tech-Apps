-- ── 030 DOWN: put the identity helpers back on auth.uid() ──
--
-- This restores the pre-030 state: helpers that resolve `id = auth.uid()`
-- against user_profiles, and three policies that compare auth.uid() directly.
--
-- WHAT THAT MEANS IN PRACTICE
--
-- It does not reopen a cross-tenant hole the way 029_down does. It does the
-- opposite: it makes every policy in the schema match NOTHING again, for
-- everyone, because this application authenticates with Clerk and auth.uid() is
-- the subject of a Supabase JWT that no real user here holds. The failure mode
-- is closed, not open — a JWT-carrying client would see zero rows everywhere
-- rather than another tenant's rows.
--
-- So this is safe to run in the sense that matters (no data becomes visible that
-- should not be), and useless in every other sense. The only honest reason to
-- run it is to return the database to a known prior state during a bisect.
--
-- If you are here because 030 broke something, read this first: the most likely
-- cause is not the SQL. It is that Supabase is not yet configured to accept
-- Clerk as a JWT issuer, or that the Clerk session token does not carry
-- `"role": "authenticated"` — in which case auth.jwt() is NULL, the helpers
-- return NULL, and everything fails closed exactly as it did before 030. That is
-- a Clerk/Supabase configuration gap, and reverting this migration will not
-- close it. See 030's header.
--
-- The dropped functions are dropped, not restored, because nothing before 030
-- referenced them.
--
-- Functions and three policies only. Nothing here can lose data.

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════
-- PART 1 — Restore the policies to their auth.uid() form
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Done before the functions are dropped: these policies reference
-- get_user_profile_id(), and Postgres will refuse to drop a function a live
-- policy still depends on.

DROP POLICY IF EXISTS select_profiles ON public.user_profiles;
CREATE POLICY select_profiles ON public.user_profiles
  FOR SELECT USING (
    organization_id = public.get_user_organization()
    OR id = auth.uid()
  );

DROP POLICY IF EXISTS select_certificates ON public.certificates;
CREATE POLICY select_certificates ON public.certificates
  FOR SELECT USING (
    organization_id = public.get_user_organization()
    OR subject_user_id = auth.uid()
  );

DROP POLICY IF EXISTS select_people_credentials ON public.people_credentials;
CREATE POLICY select_people_credentials ON public.people_credentials
  FOR SELECT USING (
    subject_user_id = auth.uid()
    OR (
      organization_id = public.get_user_organization()
      AND public.get_user_role() IN ('admin', 'super_admin')
    )
  );

-- ═══════════════════════════════════════════════════════════════════════════
-- PART 2 — Restore the helpers to their plpgsql, auth.uid() form
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Reproduced as they were: plpgsql, VOLATILE by default, and with no fixed
-- search_path. Both of those are defects 030 corrected — the per-row
-- re-evaluation and the SECURITY DEFINER search_path hazard — and a faithful
-- reversal restores them along with everything else. Another reason not to sit
-- on this state.

CREATE OR REPLACE FUNCTION public.get_user_organization()
  RETURNS uuid
  LANGUAGE plpgsql
  SECURITY DEFINER
AS $function$
BEGIN
  RETURN (
    SELECT organization_id
    FROM public.user_profiles
    WHERE id = auth.uid()
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.get_user_role()
  RETURNS text
  LANGUAGE plpgsql
  SECURITY DEFINER
AS $function$
BEGIN
  RETURN (
    SELECT role
    FROM public.user_profiles
    WHERE id = auth.uid()
  );
END;
$function$;

-- ═══════════════════════════════════════════════════════════════════════════
-- PART 3 — Drop what 030 introduced
-- ═══════════════════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS public.get_user_profile_id();
DROP FUNCTION IF EXISTS public.clerk_subject();

COMMIT;
