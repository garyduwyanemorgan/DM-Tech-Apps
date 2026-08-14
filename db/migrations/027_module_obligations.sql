BEGIN;

-- ── Migration 027: module_obligations — the duties a guideline states ────────
-- WHY. Ticking a module currently creates nothing. §4.5 says the ticking
-- exercise is simultaneously the onboarding flow, the billing driver and the
-- scope of what the app monitors — but there is no table holding what a module
-- actually obliges you to do, so the third of those cannot happen. Every
-- obligation has to be typed in by hand, which for eighty guidelines is not a
-- product.
--
-- `obligations` (023) is deliberately per-client: it carries organization_id,
-- site_id, an entitlement, a due date and a status. What it cannot hold is the
-- guideline's own statement — "a cooling tower must be sampled quarterly" — which
-- is true for every client and belongs with the standard, not with any one of
-- them. Loading the corpus made this concrete: 25 extracted obligations had
-- nowhere to go, because they describe a duty rather than an instance of one.
--
-- So: module_obligations is the template, obligations is the instance, and
-- entitlement is what turns one into the other.
--
-- GLOBAL, NOT ORG-SCOPED, for the same reason `standards` is. What GU44 requires
-- does not vary by tenant. A client who needs a different cadence than the
-- guideline states changes it on their own obligation row, not here.

CREATE TABLE IF NOT EXISTS public.module_obligations (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module_id         UUID NOT NULL REFERENCES public.guideline_modules(id) ON DELETE CASCADE,
    standard_id       UUID NOT NULL REFERENCES public.standards(id) ON DELETE RESTRICT,
    spec_set_id       UUID REFERENCES public.specification_sets(id) ON DELETE RESTRICT,

    obligation_type   TEXT NOT NULL,
    label             TEXT NOT NULL,
    applies_to        TEXT,             -- the asset or subject, in the document's words
    applies_to_scope  TEXT,             -- mirrors specification_sets.applies_to_scope

    -- Exactly one of the three modes, same as obligations (023). A template that
    -- is self_declared_review is the guideline stating a duty and NOT stating a
    -- frequency — 41 of the extracted obligations are this, and pretending
    -- otherwise would invent a deadline nobody agreed to.
    cadence_months    INTEGER,
    cadence_days      INTEGER,
    trigger_event     TEXT,
    self_declared_review BOOLEAN NOT NULL DEFAULT FALSE,

    -- The default a client's obligation starts with. Overridable per instance.
    grace_days        INTEGER NOT NULL DEFAULT 0,

    -- Provenance, on the same terms as spec_limits. A template obligation is
    -- content read off a PDF, so it carries the same burden of proof: §7.1 makes
    -- an uncitable duty unverifiable, and an unverified one unsellable.
    source_page       INTEGER,
    source_quote      TEXT,
    confidence        TEXT,

    created_at        TIMESTAMPTZ DEFAULT now(),
    UNIQUE (module_id, label)
);

ALTER TABLE public.module_obligations DROP CONSTRAINT IF EXISTS module_obligations_type_check;
ALTER TABLE public.module_obligations
    ADD CONSTRAINT module_obligations_type_check
    CHECK (obligation_type IN (
        'sampling', 'examination', 'inspection', 'self_inspection', 'health_screening',
        'cleaning', 'deep_cleaning', 'disinfection', 'pest_control', 'waste_removal',
        'maintenance', 'competency', 'permit_renewal', 'reporting', 'review',
        'risk_assessment', 'process', 'isolation_and_notification'));

-- Identical in shape to obligations_cadence_check. Kept as its own constraint
-- rather than shared, because the two tables can drift apart legitimately — a
-- client may put a cadence on an instance whose template had none, which is the
-- entire point of self_declared_review.
ALTER TABLE public.module_obligations DROP CONSTRAINT IF EXISTS module_obligations_cadence_check;
ALTER TABLE public.module_obligations
    ADD CONSTRAINT module_obligations_cadence_check
    CHECK (
        ((cadence_months IS NOT NULL OR cadence_days IS NOT NULL)
         AND coalesce(btrim(trigger_event), '') = ''
         AND coalesce(self_declared_review, false) = false)
     OR (cadence_months IS NULL AND cadence_days IS NULL
         AND coalesce(btrim(trigger_event), '') <> ''
         AND coalesce(self_declared_review, false) = false)
     OR (cadence_months IS NULL AND cadence_days IS NULL
         AND coalesce(btrim(trigger_event), '') = ''
         AND coalesce(self_declared_review, false) = true));

ALTER TABLE public.module_obligations DROP CONSTRAINT IF EXISTS module_obligations_one_unit_check;
ALTER TABLE public.module_obligations
    ADD CONSTRAINT module_obligations_one_unit_check
    CHECK (cadence_months IS NULL OR cadence_days IS NULL);

ALTER TABLE public.module_obligations DROP CONSTRAINT IF EXISTS module_obligations_positive_check;
ALTER TABLE public.module_obligations
    ADD CONSTRAINT module_obligations_positive_check
    CHECK ((cadence_months IS NULL OR cadence_months > 0)
       AND (cadence_days IS NULL OR cadence_days > 0)
       AND grace_days >= 0);

ALTER TABLE public.module_obligations DROP CONSTRAINT IF EXISTS module_obligations_scope_check;
ALTER TABLE public.module_obligations
    ADD CONSTRAINT module_obligations_scope_check
    CHECK (applies_to_scope IS NULL
           OR applies_to_scope IN ('lagoon', 'facilities', 'consumer_product'));

ALTER TABLE public.module_obligations DROP CONSTRAINT IF EXISTS module_obligations_confidence_check;
ALTER TABLE public.module_obligations
    ADD CONSTRAINT module_obligations_confidence_check
    CHECK (confidence IS NULL OR confidence IN ('high', 'medium', 'low'));

CREATE INDEX IF NOT EXISTS module_obligations_module_idx
    ON public.module_obligations (module_id);

-- Records which template an instance came from, so that a later edition of a
-- guideline can be diffed against what clients are actually tracking. NULL means
-- hand-created, which stays legal: a client may have duties the catalogue does
-- not know about.
--
-- ON DELETE SET NULL, deliberately NOT RESTRICT: retiring a module template must
-- not be blocked by, nor cascade into, live client obligations. The obligation
-- and its evidence survive with the link cleared (§7.5 — history is retained,
-- monitoring is what stops).
ALTER TABLE public.obligations
    ADD COLUMN IF NOT EXISTS module_obligation_id UUID
    REFERENCES public.module_obligations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS obligations_module_obligation_idx
    ON public.obligations (module_obligation_id);

COMMENT ON TABLE public.module_obligations IS
    'What a guideline module OBLIGES, as the document states it — the template. '
    'Global reference data like standards: what GU44 requires does not vary by '
    'tenant. obligations (023) holds the per-client INSTANCE with its due date '
    'and status; entitlement is what turns one into the other. Created by 027 '
    'because ticking a module previously created nothing, leaving §4.5''s claim '
    'that entitlement defines monitoring scope unimplementable.';
COMMENT ON COLUMN public.module_obligations.self_declared_review IS
    'TRUE when the guideline states a duty but NO frequency. 41 of the extracted '
    'obligations are this. An instance created from such a template has no due '
    'date and must not read as compliant — core/obligations.py reports it as '
    'needing a cadence to be agreed with the client. Inventing one here would '
    'manufacture a deadline the document does not support.';
COMMENT ON COLUMN public.obligations.module_obligation_id IS
    'The template this instance came from, or NULL when hand-created. ON DELETE '
    'SET NULL so retiring a template neither blocks on nor destroys live client '
    'obligations and their evidence.';

-- ── RLS ──────────────────────────────────────────────────────────────────────
ALTER TABLE public.module_obligations ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.module_obligations TO service_role;

-- Readable by any authenticated user, writable only by super_admin — the same
-- posture as standards and guideline_modules, and for the same reason: this is
-- the published record of what a guideline requires, and a tenant admin editing
-- it would change what every other tenant is monitored against.
DROP POLICY IF EXISTS select_module_obligations ON public.module_obligations;
CREATE POLICY select_module_obligations ON public.module_obligations
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS mutate_module_obligations ON public.module_obligations;
CREATE POLICY mutate_module_obligations ON public.module_obligations
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

COMMIT;
