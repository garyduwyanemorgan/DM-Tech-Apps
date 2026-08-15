-- ── 029 DOWN: restore the pre-029 policies ──
--
-- READ THIS BEFORE RUNNING IT.
--
-- This file is a faithful reversal, which means it REINTRODUCES A KNOWN
-- CROSS-TENANT VULNERABILITY (security review H2). It puts back
--
--     OR public.get_user_role() = 'super_admin'
--
-- on 32 tenant-table policies, and restores the 9 write policies on the global
-- reference tables that let any tenant's Executive Management rewrite the module
-- catalogue, its prices and its provenance. After running this, any user holding
-- super_admin in ANY organisation — a role every self-provisioned signup
-- receives automatically — can read and in most cases write every other
-- organisation's data, including obligations, entitlements, price_agreed, and
-- credential records about named individuals.
--
-- It exists because the repository's rule is that every migration has a matching
-- reversal, and because a down file that silently kept the fix would be lying
-- about what it does. It is not a file you should ever have a reason to run.
--
-- If you are here because 029 broke something: the likely cause is a client that
-- was relying on the cross-tenant read to work, which is the finding rather than
-- a regression. Fix the caller. If you are here to restore vendor write access
-- to the catalogue, do NOT run this — add a platform-staff predicate to the
-- specific table you need, as 029's header describes.
--
-- Note that both 029 and this file only ever DROP and CREATE policies. Nothing
-- here can lose data.

BEGIN;

-- ═══════════════════════════════════════════════════════════════════════════
-- PART 1 — Tenant tables: put the cross-tenant clause back
-- ═══════════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS select_org ON public.organizations;
CREATE POLICY select_org ON public.organizations
  FOR SELECT USING (
    id = public.get_user_organization() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_org ON public.organizations;
CREATE POLICY mutate_org ON public.organizations
  FOR ALL USING (
    public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS select_sites ON public.sites;
CREATE POLICY select_sites ON public.sites
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS select_readings ON public.readings;
CREATE POLICY select_readings ON public.readings
  FOR SELECT USING (
    site_id IN (SELECT id FROM public.sites WHERE organization_id = public.get_user_organization())
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS select_predictions ON public.predictions;
CREATE POLICY select_predictions ON public.predictions
  FOR SELECT USING (
    site_id IN (SELECT id FROM public.sites WHERE organization_id = public.get_user_organization())
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS select_profiles ON public.user_profiles;
CREATE POLICY select_profiles ON public.user_profiles
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR id = auth.uid() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS select_lab_samples ON public.lab_samples;
CREATE POLICY select_lab_samples ON public.lab_samples
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS select_lab_results ON public.lab_results;
CREATE POLICY select_lab_results ON public.lab_results
  FOR SELECT USING (
    sample_id IN (SELECT id FROM public.lab_samples WHERE organization_id = public.get_user_organization())
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS select_report_types ON public.report_types;
CREATE POLICY select_report_types ON public.report_types
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS select_asset_types ON public.asset_types;
CREATE POLICY select_asset_types ON public.asset_types
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS select_specification_sets ON public.specification_sets;
CREATE POLICY select_specification_sets ON public.specification_sets
  FOR SELECT TO authenticated USING (
    organization_id IS NULL
    OR organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_specification_sets ON public.specification_sets;
CREATE POLICY mutate_specification_sets ON public.specification_sets
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id IS NOT NULL
        AND organization_id = public.get_user_organization()
        AND public.get_user_role() = 'admin')
  );

DROP POLICY IF EXISTS select_spec_limits ON public.spec_limits;
CREATE POLICY select_spec_limits ON public.spec_limits
  FOR SELECT TO authenticated USING (
    spec_set_id IN (
      SELECT id FROM public.specification_sets
      WHERE organization_id IS NULL OR organization_id = public.get_user_organization()
    )
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_spec_limits ON public.spec_limits;
CREATE POLICY mutate_spec_limits ON public.spec_limits
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (spec_set_id IN (
          SELECT id FROM public.specification_sets
          WHERE organization_id IS NOT NULL AND organization_id = public.get_user_organization()
        )
        AND public.get_user_role() = 'admin')
  );

DROP POLICY IF EXISTS select_organization_entitlements ON public.organization_entitlements;
CREATE POLICY select_organization_entitlements ON public.organization_entitlements
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_organization_entitlements ON public.organization_entitlements;
CREATE POLICY mutate_organization_entitlements ON public.organization_entitlements
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS select_obligations ON public.obligations;
CREATE POLICY select_obligations ON public.obligations
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_obligations ON public.obligations;
CREATE POLICY mutate_obligations ON public.obligations
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization() AND public.get_user_role() = 'admin')
  );

DROP POLICY IF EXISTS select_certificates ON public.certificates;
CREATE POLICY select_certificates ON public.certificates
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR subject_user_id = auth.uid()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_certificates ON public.certificates;
CREATE POLICY mutate_certificates ON public.certificates
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization() AND public.get_user_role() = 'admin')
  );

DROP POLICY IF EXISTS select_inspections ON public.inspections;
CREATE POLICY select_inspections ON public.inspections
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_inspections ON public.inspections;
CREATE POLICY mutate_inspections ON public.inspections
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'operator'))
  );

DROP POLICY IF EXISTS select_inspection_findings ON public.inspection_findings;
CREATE POLICY select_inspection_findings ON public.inspection_findings
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_inspection_findings ON public.inspection_findings;
CREATE POLICY mutate_inspection_findings ON public.inspection_findings
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'operator'))
  );

DROP POLICY IF EXISTS select_risk_assessments ON public.risk_assessments;
CREATE POLICY select_risk_assessments ON public.risk_assessments
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_risk_assessments ON public.risk_assessments;
CREATE POLICY mutate_risk_assessments ON public.risk_assessments
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'operator'))
  );

DROP POLICY IF EXISTS select_risk_assessment_entries ON public.risk_assessment_entries;
CREATE POLICY select_risk_assessment_entries ON public.risk_assessment_entries
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_risk_assessment_entries ON public.risk_assessment_entries;
CREATE POLICY mutate_risk_assessment_entries ON public.risk_assessment_entries
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'operator'))
  );

DROP POLICY IF EXISTS select_people_credentials ON public.people_credentials;
CREATE POLICY select_people_credentials ON public.people_credentials
  FOR SELECT TO authenticated USING (
    subject_user_id = auth.uid()
    OR (organization_id = public.get_user_organization() AND public.get_user_role() = 'admin')
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_people_credentials ON public.people_credentials;
CREATE POLICY mutate_people_credentials ON public.people_credentials
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization() AND public.get_user_role() = 'admin')
  );

DROP POLICY IF EXISTS select_credential_prerequisites ON public.credential_prerequisites;
CREATE POLICY select_credential_prerequisites ON public.credential_prerequisites
  FOR SELECT TO authenticated USING (
    (organization_id = public.get_user_organization() AND public.get_user_role() = 'admin')
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_credential_prerequisites ON public.credential_prerequisites;
CREATE POLICY mutate_credential_prerequisites ON public.credential_prerequisites
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization() AND public.get_user_role() = 'admin')
  );

-- ═══════════════════════════════════════════════════════════════════════════
-- PART 2 — Global reference tables: restore the authenticated write policies
-- ═══════════════════════════════════════════════════════════════════════════
-- Each of these makes vendor-curated data writable by any tenant's Executive
-- Management. That is the defect, restored verbatim.

DROP POLICY IF EXISTS mutate_standards ON public.standards;
CREATE POLICY mutate_standards ON public.standards
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS mutate_laboratories ON public.laboratories;
CREATE POLICY mutate_laboratories ON public.laboratories
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS mutate_guideline_modules ON public.guideline_modules;
CREATE POLICY mutate_guideline_modules ON public.guideline_modules
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS mutate_module_obligations ON public.module_obligations;
CREATE POLICY mutate_module_obligations ON public.module_obligations
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS mutate_severity_scales ON public.severity_scales;
CREATE POLICY mutate_severity_scales ON public.severity_scales
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS mutate_severity_scale_values ON public.severity_scale_values;
CREATE POLICY mutate_severity_scale_values ON public.severity_scale_values
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS mutate_checklist_templates ON public.checklist_templates;
CREATE POLICY mutate_checklist_templates ON public.checklist_templates
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS mutate_checklist_items ON public.checklist_items;
CREATE POLICY mutate_checklist_items ON public.checklist_items
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS mutate_coverage_requirements ON public.coverage_requirements;
CREATE POLICY mutate_coverage_requirements ON public.coverage_requirements
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

COMMIT;
