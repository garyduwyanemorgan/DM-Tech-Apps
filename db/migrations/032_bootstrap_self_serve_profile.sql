-- ── 032: a SECURITY DEFINER escape hatch for the one write RLS cannot permit ──
--
-- THE PROBLEM
--
-- mutate_org and mutate_profiles are both `FOR ALL` with no WITH CHECK, so
-- Postgres reuses their USING clause as the INSERT check:
--
--   organizations.mutate_org       id = get_user_organization() AND get_user_role() = 'super_admin'
--   user_profiles.mutate_profiles  organization_id = get_user_organization() AND get_user_role() IN ('admin','super_admin')
--
-- _create_super_admin_profile() (api_server.py:297-318) provisions a brand-new
-- organisation and the caller's own user_profiles row on first sign-in, for a
-- caller who by definition has NEITHER yet. For that caller
-- get_user_organization() and get_user_role() both resolve to NULL (they read
-- user_profiles WHERE clerk_id = clerk_subject(), and no such row exists), and a
-- freshly-generated org id can never equal NULL. Both predicates are false, both
-- INSERTs are denied. There is no policy shape that fixes this: the check
-- necessarily needs to know the row doesn't exist yet to allow creating it, which
-- is exactly what a per-row USING/WITH CHECK clause cannot express — it evaluates
-- against a row, not against the absence of one, and "does the caller already
-- have a profile" is a query the tenant-scoped policies are not written to ask.
--
-- mutate_profiles predates 029/030 and was never touched by either: both
-- migrations rewrote select_profiles, not this one.
--
-- WHAT THIS DOES
--
-- A single SECURITY DEFINER function that provisions both rows atomically, for a
-- caller who currently has neither, and refuses every other request. It is a
-- narrow, one-time hole through RLS, not a general bypass: the only two INSERTs
-- it can ever issue are "one new organisation" and "one new user_profiles row,
-- owned by the caller, as super_admin of that organisation, in the same
-- transaction". Nothing about which table, which columns, or which values is
-- reachable from outside the function body.
--
-- SECURITY PROPERTIES, AND THE ATTACK EACH ONE CLOSES
--
-- 1. Identity comes ONLY from public.clerk_subject() (auth.jwt()->>'sub'). The
--    function takes NO parameters at all — there is no user id, email or
--    organisation id argument to supply, so there is nothing for a caller to
--    substitute to provision on someone else's behalf. Attack closed: "call with
--    a stolen/guessed clerk_id" is not expressible — the argument does not exist.
--
-- 2. Refuses if the caller already has a profile (SELECT ... WHERE clerk_id =
--    v_subject before either INSERT). Without this, any existing operator could
--    call the function repeatedly to mint themselves a fresh super_admin
--    organisation on demand — a privilege-escalation primitive available to
--    every authenticated role, not just admins. The clerk_id column also carries
--    a UNIQUE constraint (002_clerk.sql), so even a concurrent double-call from
--    two overlapping transactions cannot both succeed: the loser's INSERT raises
--    a unique-violation instead of silently creating a second profile. The
--    read-then-check gives the friendly error in the common case; the UNIQUE
--    constraint is the backstop that makes the refusal atomic, not merely usual.
--
-- 3. Never joins an existing organisation and never accepts a role. The function
--    body always INSERTs a brand-new organizations row and always writes
--    role = 'super_admin' as a literal — there is no code path, parameter or
--    branch that can target an existing organization_id or a different role.
--    Attack closed: a caller cannot use this to attach themselves to another
--    tenant's organisation, nor to hand themselves 'admin' quietly to look less
--    conspicuous than 'super_admin'.
--
-- 4. search_path pinned to `public, pg_temp`, exactly like clerk_subject(),
--    get_user_organization(), get_user_role() and get_user_profile_id() in 030.
--    A SECURITY DEFINER function with a mutable search_path is the standard
--    escalation shape: a caller able to create objects earlier on their own
--    search_path could shadow public.organizations or public.user_profiles and
--    have this function silently read or write the shadow instead, still running
--    with the definer's privileges. Pinning closes that off the same way 030
--    documents for the identity helpers.
--
-- 5. EXECUTE is granted to `authenticated` only, never `anon`. An unauthenticated
--    caller cannot invoke this function at all — PostgREST rejects the call
--    before the body ever runs, which is a stronger guard than the in-body
--    "subject IS NULL" check alone. Both are present: the grant is the primary
--    control, the in-body check is defence in depth for any future caller that
--    reaches this function directly in psql/plpgsql rather than through
--    PostgREST (where request.jwt.claims, and therefore clerk_subject(), may be
--    unset).
--
-- WHAT AN AUTHENTICATED CALLER CAN STILL DO
--
-- Exactly what the design intends: a caller with no profile row can call this
-- once and become super_admin of exactly one brand-new organisation containing
-- exactly one site's worth of nothing — the same outcome _create_super_admin_profile()
-- already produces today via service_role, just reachable under RLS. That is not
-- a new capability, it is the existing self-serve signup made expressible without
-- bypassing RLS. Nothing here lets a caller read, write or join any OTHER
-- tenant's data, nor repeat the provisioning once a profile exists.
--
-- WHAT THIS DOES NOT DO
--
-- This does not move any write path onto RLS. db/client.py still connects with
-- SERVICE_ROLE_KEY, which bypasses RLS entirely, and _create_super_admin_profile()
-- is not changed to call this function — that is an application-layer change,
-- out of scope here and not attempted. Applying this migration changes NOTHING
-- about today's runtime behaviour; it only makes self-serve signup EXPRESSIBLE
-- under RLS for the day writes move off service_role. Until then this function
-- simply exists, unused, like clerk_subject() sat unused between 030 and now.
--
-- No table, column, index or existing-policy change. One new function only.
--
-- Requires 002 (clerk_id), 029 (fixed mutate_org/mutate_profiles predicates) and
-- 030 (clerk_subject()). Reversible: see 032_bootstrap_self_serve_profile_down.sql.

BEGIN;

CREATE OR REPLACE FUNCTION public.bootstrap_self_serve_profile()
  RETURNS TABLE(organization_id uuid, profile_id uuid)
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = public, pg_temp
AS $$
DECLARE
  v_subject text;
  v_org_id  uuid;
  v_profile_id uuid;
BEGIN
  v_subject := public.clerk_subject();

  -- Defence in depth: the EXECUTE grant already keeps anon out, but a caller
  -- reached some other way (direct psql, a future SECURITY DEFINER wrapper)
  -- with no usable JWT must still be refused rather than silently matching NULL.
  IF v_subject IS NULL THEN
    RAISE EXCEPTION 'bootstrap_self_serve_profile: no Clerk subject on this request'
      USING ERRCODE = '28000';  -- invalid_authorization_specification
  END IF;

  -- Refuse outright if the caller already has a profile. Without this check the
  -- function is a privilege-escalation primitive: any existing operator could
  -- call it again and again to mint themselves a fresh super_admin organisation
  -- each time.
  PERFORM 1 FROM public.user_profiles WHERE clerk_id = v_subject;
  IF FOUND THEN
    RAISE EXCEPTION 'bootstrap_self_serve_profile: caller already has a profile'
      USING ERRCODE = '42710';  -- duplicate_object
  END IF;

  -- Always a NEW organisation. There is no parameter through which an existing
  -- organization_id could be supplied.
  INSERT INTO public.organizations (name)
  VALUES (v_subject || '''s Organization')
  RETURNING id INTO v_org_id;

  -- Always super_admin of the org just created, never a caller-chosen role and
  -- never a caller-chosen organisation. The unique constraint on clerk_id
  -- (002_clerk.sql) makes a concurrent double-provision fail loudly rather than
  -- silently creating a second profile, even though the FOUND check above
  -- already rejects the common sequential case.
  INSERT INTO public.user_profiles (id, clerk_id, role, organization_id)
  VALUES (gen_random_uuid(), v_subject, 'super_admin', v_org_id)
  RETURNING id INTO v_profile_id;

  RETURN QUERY SELECT v_org_id, v_profile_id;
END;
$$;

COMMENT ON FUNCTION public.bootstrap_self_serve_profile() IS
  'Atomically provisions a new organisation and the calling Clerk user''s own '
  'super_admin profile in it. Refuses if the caller already has a profile. '
  'Identity comes only from clerk_subject() — no parameters accepted. Not '
  'currently called by any application code; db/client.py still writes as '
  'service_role. See migration 032 header for the full threat analysis.';

REVOKE ALL ON FUNCTION public.bootstrap_self_serve_profile() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.bootstrap_self_serve_profile() TO authenticated;

COMMIT;
