-- ── 029: super_admin is a TENANT role, and RLS must stop treating it as a
--         platform one (security review H2) ──
--
-- Every policy written between schema_rls.sql and 028 carries some form of
--
--     OR public.get_user_role() = 'super_admin'
--
-- written as though super_admin meant "staff of the vendor". It does not. It is
-- the ordinary top role INSIDE a tenant — core/authz.py calls it Executive
-- Management — and api_server.py auto-provisions it to any user who signs in
-- with no existing profile, each in a fresh organisation of their own. So the
-- clause reads: "or the caller is an admin of literally any organisation,
-- including one they made thirty seconds ago". On a SELECT that is every
-- tenant's data; on a FOR ALL it is every tenant's data, writable.
--
-- 41 policies across 9 files carried it. The most damaging, in the words of
-- 023's own header: select_obligations, "the single most damaging table in the
-- schema to leak", and mutate_organization_entitlements, which exposes
-- price_agreed and lets one customer rewrite another's commercial terms.
--
-- WHY THIS WAS NEVER EXPLOITED, AND WHY IT STILL MATTERS
--
-- The backend connects as service_role, which bypasses RLS entirely, so no
-- policy in this schema has ever executed. Enforcement today is the API layer's
-- _ensure_permission checks plus the .eq("organization_id", …) filters in
-- db/queries.py. That is also why the defect survived review: the policies are
-- unreachable, so they were never tested, and their being wrong cost nothing.
--
-- It matters because the documented posture (PERMISSIONS_MATRIX.md) calls RLS
-- the second line of defence. It is not one. It is a hole waiting for the day a
-- JWT-carrying client ships — and on that day the failure is silent and total,
-- because a policy that returns extra rows looks exactly like a policy that
-- works. This migration makes the backstop real BEFORE anything leans on it.
--
-- WHAT THIS DOES NOT FIX
--
-- The policies resolve identity through auth.uid() against user_profiles.id,
-- which references auth.users(id). This app authenticates with Clerk and keys
-- profiles on clerk_id. A Supabase JWT for a Clerk user does not exist, so
-- get_user_organization() would return NULL and match nothing. These policies
-- are therefore correct-but-inert until get_user_organization()/get_user_role()
-- are re-keyed onto the Clerk subject. That re-keying is a PREREQUISITE for any
-- client-side Supabase access and is deliberately not attempted here: it cannot
-- be tested without the client it exists to serve, and shipping an untestable
-- rewrite of the identity helpers alongside 41 policy changes would make both
-- harder to review. Fixing the holes is worth doing on its own — a re-key onto
-- correct policies is a small change, a re-key onto these would have activated
-- every one of them.
--
-- TWO CLASSES OF TABLE, TWO DIFFERENT FIXES
--
-- The 41 sites are not one problem. They split exactly along whether the table
-- has an organization_id:
--
--   Tenant tables (organization_id present, or reachable by join) — the clause
--   is pure cross-tenant reach with no legitimate use. Stripped, leaving the
--   organisation predicate that was always the real rule. Where super_admin was
--   the SOLE predicate on a mutation, it is re-scoped to that tenant rather than
--   deleted, because a tenant's Executive Management genuinely should be able to
--   write its own rows — the bug was the missing organisation test, not the role.
--
--   Global reference tables (no organization_id: the DM corpus, the standards,
--   the module catalogue, the shared checklist and severity scaffolding) — these
--   are vendor-curated data that customers read and never write. The clause let
--   any customer's admin set a module's status='available' or provenance=
--   'verified', or rewrite list_price_monthly, which is precisely the guarantee
--   023:776-778 says the policy exists to protect. Their write policies are
--   DROPPED outright rather than re-scoped, because the only writers that have
--   ever existed are the operator-run CLI loaders db/load_guidelines.py and
--   db/seed_standards.py, which connect as service_role and bypass RLS. No
--   platform_staff table or JWT claim is introduced: there is no API path that
--   would use one today, and an unused privilege mechanism is a liability. If a
--   vendor-facing catalogue admin UI is ever built, add the predicate then — the
--   deletions here are identical either way, so nothing is foreclosed.
--
-- Every SELECT policy on the global tables is USING (true) and is untouched, so
-- reads are entirely unaffected by the drops.
--
-- No table, column, index or grant changes. Policies only.

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════
-- PART 1 — Tenant tables: strip the clause, keep the organisation predicate
-- ═══════════════════════════════════════════════════════════════════════════

-- ── organizations (schema_rls.sql) ──
DROP POLICY IF EXISTS select_org ON public.organizations;
CREATE POLICY select_org ON public.organizations
  FOR SELECT USING (
    id = public.get_user_organization()
  );

-- Was: USING (get_user_role() = 'super_admin') with no organisation test at
-- all — any tenant's Executive Management could rename or re-plan any other
-- organisation on the platform. Re-scoped rather than dropped: a tenant editing
-- its own organisation row is legitimate.
DROP POLICY IF EXISTS mutate_org ON public.organizations;
CREATE POLICY mutate_org ON public.organizations
  FOR ALL USING (
    id = public.get_user_organization() AND public.get_user_role() = 'super_admin'
  );

-- ── sites, readings, predictions, user_profiles (schema_rls.sql) ──
DROP POLICY IF EXISTS select_sites ON public.sites;
CREATE POLICY select_sites ON public.sites
  FOR SELECT USING (
    organization_id = public.get_user_organization()
  );

DROP POLICY IF EXISTS select_readings ON public.readings;
CREATE POLICY select_readings ON public.readings
  FOR SELECT USING (
    site_id IN (SELECT id FROM public.sites WHERE organization_id = public.get_user_organization())
  );

DROP POLICY IF EXISTS select_predictions ON public.predictions;
CREATE POLICY select_predictions ON public.predictions
  FOR SELECT USING (
    site_id IN (SELECT id FROM public.sites WHERE organization_id = public.get_user_organization())
  );

-- id = auth.uid() is kept: a user reading their own profile row is correct and
-- is not a cross-tenant path.
DROP POLICY IF EXISTS select_profiles ON public.user_profiles;
CREATE POLICY select_profiles ON public.user_profiles
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR id = auth.uid()
  );

-- ── lab_samples, lab_results (016) ──
DROP POLICY IF EXISTS select_lab_samples ON public.lab_samples;
CREATE POLICY select_lab_samples ON public.lab_samples
  FOR SELECT USING (
    organization_id = public.get_user_organization()
  );

DROP POLICY IF EXISTS select_lab_results ON public.lab_results;
CREATE POLICY select_lab_results ON public.lab_results
  FOR SELECT USING (
    sample_id IN (SELECT id FROM public.lab_samples WHERE organization_id = public.get_user_organization())
  );

-- ── report_types (017), asset_types (020) ──
DROP POLICY IF EXISTS select_report_types ON public.report_types;
CREATE POLICY select_report_types ON public.report_types
  FOR SELECT USING (
    organization_id = public.get_user_organization()
  );

DROP POLICY IF EXISTS select_asset_types ON public.asset_types;
CREATE POLICY select_asset_types ON public.asset_types
  FOR SELECT USING (
    organization_id = public.get_user_organization()
  );

-- ── specification_sets, spec_limits (022) ──
-- organization_id IS NULL means a global, vendor-seeded set. Readable by every
-- tenant by design; the super_admin arm is what allowed cross-tenant reads of
-- OTHER tenants' private sets, and it is the only part removed.
DROP POLICY IF EXISTS select_specification_sets ON public.specification_sets;
CREATE POLICY select_specification_sets ON public.specification_sets
  FOR SELECT TO authenticated USING (
    organization_id IS NULL
    OR organization_id = public.get_user_organization()
  );

-- The old super_admin arm had no organisation test, so it granted writes to
-- BOTH other tenants' sets and the global (organization_id IS NULL) ones. The
-- IS NOT NULL guard is retained precisely so a tenant cannot write global rows.
DROP POLICY IF EXISTS mutate_specification_sets ON public.specification_sets;
CREATE POLICY mutate_specification_sets ON public.specification_sets
  FOR ALL TO authenticated USING (
    organization_id IS NOT NULL
    AND organization_id = public.get_user_organization()
    AND public.get_user_role() IN ('admin', 'super_admin')
  );

DROP POLICY IF EXISTS select_spec_limits ON public.spec_limits;
CREATE POLICY select_spec_limits ON public.spec_limits
  FOR SELECT TO authenticated USING (
    spec_set_id IN (
      SELECT id FROM public.specification_sets
      WHERE organization_id IS NULL OR organization_id = public.get_user_organization()
    )
  );

DROP POLICY IF EXISTS mutate_spec_limits ON public.spec_limits;
CREATE POLICY mutate_spec_limits ON public.spec_limits
  FOR ALL TO authenticated USING (
    spec_set_id IN (
      SELECT id FROM public.specification_sets
      WHERE organization_id IS NOT NULL AND organization_id = public.get_user_organization()
    )
    AND public.get_user_role() IN ('admin', 'super_admin')
  );

-- ── organization_entitlements, obligations, certificates (023) ──
-- The commercial record: price_agreed lives here. One tenant reading another's
-- was the finding's clearest single loss.
DROP POLICY IF EXISTS select_organization_entitlements ON public.organization_entitlements;
CREATE POLICY select_organization_entitlements ON public.organization_entitlements
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
  );

-- Was USING (get_user_role() = 'super_admin') alone — writable by any tenant's
-- Executive Management. Re-scoped to the owning organisation, keeping
-- super_admin as the only role, which mirrors entitlements.manage being bound
-- to Executive Management alone in core/authz.py (f5747e7).
DROP POLICY IF EXISTS mutate_organization_entitlements ON public.organization_entitlements;
CREATE POLICY mutate_organization_entitlements ON public.organization_entitlements
  FOR ALL TO authenticated USING (
    organization_id = public.get_user_organization()
    AND public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS select_obligations ON public.obligations;
CREATE POLICY select_obligations ON public.obligations
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
  );

DROP POLICY IF EXISTS mutate_obligations ON public.obligations;
CREATE POLICY mutate_obligations ON public.obligations
  FOR ALL TO authenticated USING (
    organization_id = public.get_user_organization()
    AND public.get_user_role() IN ('admin', 'super_admin')
  );

-- subject_user_id = auth.uid() is kept: a person reading the certificate that
-- names them is correct, and is how an individual sees their own competency
-- record without admin rights.
DROP POLICY IF EXISTS select_certificates ON public.certificates;
CREATE POLICY select_certificates ON public.certificates
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR subject_user_id = auth.uid()
  );

DROP POLICY IF EXISTS mutate_certificates ON public.certificates;
CREATE POLICY mutate_certificates ON public.certificates
  FOR ALL TO authenticated USING (
    organization_id = public.get_user_organization()
    AND public.get_user_role() IN ('admin', 'super_admin')
  );

-- ── inspections, findings, risk assessments (024) ──
DROP POLICY IF EXISTS select_inspections ON public.inspections;
CREATE POLICY select_inspections ON public.inspections
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
  );

DROP POLICY IF EXISTS mutate_inspections ON public.inspections;
CREATE POLICY mutate_inspections ON public.inspections
  FOR ALL TO authenticated USING (
    organization_id = public.get_user_organization()
    AND public.get_user_role() IN ('admin', 'operator', 'super_admin')
  );

DROP POLICY IF EXISTS select_inspection_findings ON public.inspection_findings;
CREATE POLICY select_inspection_findings ON public.inspection_findings
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
  );

DROP POLICY IF EXISTS mutate_inspection_findings ON public.inspection_findings;
CREATE POLICY mutate_inspection_findings ON public.inspection_findings
  FOR ALL TO authenticated USING (
    organization_id = public.get_user_organization()
    AND public.get_user_role() IN ('admin', 'operator', 'super_admin')
  );

DROP POLICY IF EXISTS select_risk_assessments ON public.risk_assessments;
CREATE POLICY select_risk_assessments ON public.risk_assessments
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
  );

DROP POLICY IF EXISTS mutate_risk_assessments ON public.risk_assessments;
CREATE POLICY mutate_risk_assessments ON public.risk_assessments
  FOR ALL TO authenticated USING (
    organization_id = public.get_user_organization()
    AND public.get_user_role() IN ('admin', 'operator', 'super_admin')
  );

DROP POLICY IF EXISTS select_risk_assessment_entries ON public.risk_assessment_entries;
CREATE POLICY select_risk_assessment_entries ON public.risk_assessment_entries
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
  );

DROP POLICY IF EXISTS mutate_risk_assessment_entries ON public.risk_assessment_entries;
CREATE POLICY mutate_risk_assessment_entries ON public.risk_assessment_entries
  FOR ALL TO authenticated USING (
    organization_id = public.get_user_organization()
    AND public.get_user_role() IN ('admin', 'operator', 'super_admin')
  );

-- ── people_credentials, credential_prerequisites (028) ──
-- These rows are about NAMED INDIVIDUALS — their qualifications, and the reasons
-- a credential was revoked. 028_down's header already calls this the most
-- sensitive data in the schema; the super_admin clause made it readable by every
-- tenant on the platform. subject_user_id = auth.uid() is kept so a person can
-- always see their own record.
DROP POLICY IF EXISTS select_people_credentials ON public.people_credentials;
CREATE POLICY select_people_credentials ON public.people_credentials
  FOR SELECT TO authenticated USING (
    subject_user_id = auth.uid()
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'super_admin'))
  );

DROP POLICY IF EXISTS mutate_people_credentials ON public.people_credentials;
CREATE POLICY mutate_people_credentials ON public.people_credentials
  FOR ALL TO authenticated USING (
    organization_id = public.get_user_organization()
    AND public.get_user_role() IN ('admin', 'super_admin')
  );

DROP POLICY IF EXISTS select_credential_prerequisites ON public.credential_prerequisites;
CREATE POLICY select_credential_prerequisites ON public.credential_prerequisites
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    AND public.get_user_role() IN ('admin', 'super_admin')
  );

DROP POLICY IF EXISTS mutate_credential_prerequisites ON public.credential_prerequisites;
CREATE POLICY mutate_credential_prerequisites ON public.credential_prerequisites
  FOR ALL TO authenticated USING (
    organization_id = public.get_user_organization()
    AND public.get_user_role() IN ('admin', 'super_admin')
  );

-- ═══════════════════════════════════════════════════════════════════════════
-- PART 2 — Global reference tables: no authenticated writer at all
-- ═══════════════════════════════════════════════════════════════════════════
--
-- None of these tables has an organization_id. They are the vendor's data: the
-- DM corpus, the standards seeded from core/, the sellable module catalogue and
-- its duty templates, the shared checklist and severity scaffolding, and the
-- coverage rules derived from the guidelines.
--
-- Dropping the write policy leaves each table with only its
-- select_… USING (true) policy, so every tenant continues to READ all of it
-- exactly as before. With RLS enabled and no permissive policy for INSERT,
-- UPDATE or DELETE, no `authenticated` client can write these tables at all.
--
-- The loaders are unaffected: db/load_guidelines.py and db/seed_standards.py
-- connect with the service role key, and service_role bypasses RLS. That is the
-- same reason these policies never fired in the first place, used deliberately
-- here instead of accidentally.

DROP POLICY IF EXISTS mutate_standards ON public.standards;
DROP POLICY IF EXISTS mutate_laboratories ON public.laboratories;
DROP POLICY IF EXISTS mutate_guideline_modules ON public.guideline_modules;
DROP POLICY IF EXISTS mutate_module_obligations ON public.module_obligations;
DROP POLICY IF EXISTS mutate_severity_scales ON public.severity_scales;
DROP POLICY IF EXISTS mutate_severity_scale_values ON public.severity_scale_values;
DROP POLICY IF EXISTS mutate_checklist_templates ON public.checklist_templates;
DROP POLICY IF EXISTS mutate_checklist_items ON public.checklist_items;
DROP POLICY IF EXISTS mutate_coverage_requirements ON public.coverage_requirements;

COMMIT;
