# DM Compliance Monitoring — Scoping Document

> Status: **decisions taken, ready to build.** Written against the code at
> v1.8.0. Revision 3 — supersedes revision 2; re-sequences the build around the
> quantitative/laboratory family (§8 decision 7) and models laboratory
> accreditation as a first-class gate (§8 decision 8).
>
> Companion documents: `PRODUCT_OVERVIEW.md` (describes the lagoon product and
> is now partly stale — see §2.2), `PERMISSIONS_MATRIX.md`, `db/migrations/README.md`.

---

## 1. Thesis

The reusable asset in this codebase is not water chemistry. It is a loop:

```
guideline module (sellable)
  → entitlement                       (this client has bought this module)
    → registered asset
      → obligation on a cadence       (this asset must be tested/inspected every N)
        → evidence                    (lab certificate, examination certificate, checklist)
          → verdict against a versioned standard
            → alert
              → corrective action with approval
                → auditable report
```

Water quality is one instantiation. The DM technical guidelines list
(https://www.dm.gov.ae/municipality-business/technical-guidelines-list/) is
roughly eighty instantiations of the same loop, against the same buyer — the
facilities management contractor accountable to Dubai Municipality.

The build already contains the beginning of this generalisation. It was not
accidental: migration 019 and `core/assets.py` deliberately moved specification
scope onto the asset, with the reasoning recorded in both places. This document
carries that decision to its conclusion and adds the commercial layer above it.

---

## 2. Product context

### 2.1 Who this is for

The client on the existing engagement is **Al Ghurair**, the facilities
management group operating Dubai Safari Park — the park is the site, Al Ghurair
is the buyer. The engagement is live with real, ongoing DM reporting
obligations.

The market is **every FM contractor operating under Dubai Municipality
regulation**. Al Ghurair is the first of many, not a special case. A contractor
manages many sites, for many different clients, under many different guidelines
— so the product must be designed for that shape, not for an owner with one
lagoon.

### 2.2 Note on `PRODUCT_OVERVIEW.md`

That document describes the buyer as "master-planned community developers, HOAs,
and facilities/asset managers" and the commercial model as site-count
subscription tiers. Both are now superseded: the buyer is the FM contractor, and
pricing is modular per guideline (§3.6). `PRODUCT_OVERVIEW.md` should be rewritten
once Phase 1 lands; until then treat this document as authoritative where they
disagree.

---

## 3. What exists, and what is new

### 3.1 Existing and generic — reusable with no domain change

| Capability | Location | Notes |
|---|---|---|
| Multi-tenant org/site isolation | `db/schema_rls.sql` | RLS on every table |
| Role permissions (*what*) | `core/authz.py` | 4 roles, atomic permissions |
| Data scope (*where*) | `core/scope.py` | site/project/portfolio resolution, pure functions |
| Asset registry + taxonomy | `core/assets.py`, mig. 010/019/020 | `equipment` vs `sampled` split |
| Evidence ingestion | `extract.py`, mig. 016 | PDF/vision → `lab_samples` + `lab_results` |
| Forensic audit trail | mig. 016 | immutable `raw_extraction`, `value_raw`, SHA-256 of source |
| Human review gate | `lab_samples.reviewer_status` | pending → approved/corrected/rejected |
| Corrective-action workflow | `core/corrective.py`, mig. 008 | generic state machine, permission-gated |
| Standard edition currency | `core/standards.py` | flags certificates citing a superseded edition |
| Audit events | `core/audit.py`, mig. 006/012 | append-only |
| Report generation | `reporting.py` | watermark-gated PDF |
| Payment provider abstraction | `payments/` | Checkout.com live, Stripe ready |

### 3.2 Existing and lagoon-specific — does not generalise

| Thing | Location | Disposition |
|---|---|---|
| `COMPLIANCE_LIMITS` (10 params) | `core/constants.py` | becomes one seeded specification set |
| Alert thresholds, treatment actions | `core/constants.py` | lagoon-only; stays behind lagoon scope |
| Species, nutrient sources, enzymes | `core/constants.py` | lagoon-only reference data |
| Bloom forecasting / digital twin | `science/` | premium specialist module for one scope |
| Seasonal phases | `core/constants.py` | lagoon-only |
| Site-count billing tiers | `billing.py` | **replaced** by modular entitlements (§3.6) |

### 3.3 The gap that forces the work

`assets.scope` permits `'lagoon' | 'facilities'`, and `core/report_types.py`
documents the facilities scope as governed by DM technical guidelines.

**But no facilities limit set exists in the code.** `COMPLIANCE_LIMITS` is
lagoon-only and `core/calculations.py` reads from it exclusively. A facilities
result today is judged either by the laboratory's verbatim `specification`
string on `lab_results.specification`, or not at all (`NOT_ASSESSED`).

The half-built generalisation has a hole where the second scope's limits belong.
Filling it *properly* rather than by adding a second hardcoded dict is Phase 1,
and it is the fork in the road: `FACILITIES_LIMITS` beside `COMPLIANCE_LIMITS`
works for one guideline and becomes unmaintainable at five — let alone at eighty
sellable ones.

---

## 4. Target data model

Five new concepts. Everything in §3.1 stays.

### 4.1 `standards` — the guideline, and which edition is in force

Promotes `core/standards.py`'s in-code `KNOWN_EDITIONS` dict to a table, keeping
the module as loader and validator.

```
standards
  id, authority          'DM'  — data, not hardcoded (§8 decision 2)
  code                   'DM-HSD-GU44-LCWS2'   as laboratories print it
  guideline_no           44
  title, version
  issued_on              2025-08-19
  supersedes_id          → standards.id (nullable)
  source_url             the published PDF
  language               'en' | 'ar' | 'both'
  verified_by, verified_on   provenance — see §7.1
  UNIQUE (authority, code, version)
```

Editions chain via `supersedes_id` rather than the current flat
`current_issue`/`superseded_issue` pair, so a certificate can be judged against
the edition in force *at its sampling date* — which
`core/standards.py::citation_is_stale` already reasons about correctly and
should keep doing.

`authority` exists from day one at effectively zero cost. All seed data, UI
vocabulary and report templates stay Dubai Municipality-specific; adding OSHAD
or Sharjah later is content and relabelling work, not a migration.

### 4.2 `specification_sets` and `spec_limits` — what "compliant" means

```
specification_sets
  id, organization_id    NULL = built-in, seeded; non-NULL = org override
  standard_id            → standards.id (nullable: client-specific sets exist)
  key                    'lagoon_dm_water', 'facilities_potable_tank', …
  label, applies_to_scope

spec_limits
  id, spec_set_id
  parameter_key          'ph', 'legionella_pneumophila', 'co2_ppm', 'wbgt'
  parameter_label, unit
  min_val, max_val       NULL = unbounded (same semantics as ComplianceLimit)
  display                verbatim human-readable limit
  qualifier_rule         how '<1' / 'ND' / 'Absent' is judged against this limit
  UNIQUE (spec_set_id, parameter_key)
```

`qualifier_rule` is new and necessary. Migration 016 is emphatic that verbatim
non-numeric results (`'<1'`, `'Not Detected'`, `'Absent/100mL'`) must never be
coerced to 0 — a below-LOQ non-detect is regulatorily distinct from a measured
zero. A limit must therefore state how a qualified value is judged rather than
leaving each call site to improvise.

### 4.3 `obligations` — the cadence, and what is overdue

The single biggest product addition. Today the app knows what a certificate
*said*; it does not know a certificate was **due and never arrived**. For an FM
contractor that inversion is the whole value: the risk is the missing test, not
the failed one.

```
obligations
  id, organization_id, site_id
  asset_id               → assets.id (nullable: some obligations are site-level)
  standard_id            → standards.id
  spec_set_id            → specification_sets.id (nullable)
  entitlement_id         → organization_entitlements.id   (§4.5 — required)
  obligation_type        'sampling' | 'examination' | 'inspection' | 'competency'
  cadence_months | cadence_days
  grace_days
  next_due_on, last_satisfied_at
  last_satisfied_by      → lab_samples.id | certificates.id | inspections.id
  status                 'compliant' | 'due_soon' | 'overdue' | 'suspended'
  responsible_user_id
```

An obligation is satisfied by evidence and otherwise ages `due_soon` →
`overdue`, raising an alert and optionally opening a corrective action through
the existing `core/corrective.py` machine.

> **Not every obligation has a cadence, and this table cannot yet say so.** The
> GU44 extraction turned up a sampling obligation triggered by an *event* — take
> a sample after a tank is cleaned or disinfected — rather than by a schedule.
> With only `cadence_months` / `cadence_days`, such a row has null cadence and is
> indistinguishable from one where nobody filled the field in. It would then sit
> in the registry never becoming due, which is the silent-gap failure this table
> exists to eliminate.
>
> **The `obligation_type` vocabulary is far too narrow, and real documents prove
> it.** §4.3 lists four types — sampling, examination, inspection, competency —
> derived from GU44's shape. Loading the extracted corpus against migration 023
> refused 25 obligations, most of them because the document requires something
> outside that list: `cleaning`, `deep_cleaning`, `disinfection`, `pest_control`,
> `waste_removal`, `maintenance`, `permit_renewal`, `health_screening`,
> `isolation_and_notification`, `noise_control`, `reporting`, `self_inspection`,
> `appeal_window`. These are not exotic — they are what an FM contractor is
> actually on the hook for, and several are the recurring duties a client would
> most expect the product to track.
>
Migration 025 widens it to sixteen values, grouped by whether the duty produces
judgeable evidence, is an operational task with only a completion record, is
administrative, or is incident-driven. The list deliberately stops short of the
extraction's tail — `third_party_examination_anchorage`,
`waste_covering_at_landfill`, `subcontractor_verification` and similar are
*descriptions of one duty in one guideline*, not types. `obligation_type` answers
"what kind of duty", which is what a dashboard groups by and what decides whether
§4.7's accreditation gate applies; `obligations.label` answers "which duty" and
is NOT NULL so the specific thing is always recorded. Adding a value per document
would grow the CHECK without bound and put categories on the dashboard with one
member each.

> **But the vocabulary was the smaller problem.** With 025 applied, the dominant
> blocker is different and more awkward: **41 obligations state a duty with no
> frequency at all.** The guideline says the grease trap must be cleaned, or a
> risk assessment kept current, without saying how often — the trigger, where one
> exists, is prose in `cadence_note`.
>
> 023's `obligations_cadence_check` requires exactly one of a cadence or a
> trigger, which is correct: an obligation with neither cannot age toward overdue
> and would sit in the registry forever looking satisfied. So these cannot be
> loaded, and that is the constraint doing its job.
>
> The consequence for the product is real. **A large share of DM duties are not
> automatically trackable from the guideline text alone** — somebody has to
> decide the frequency, and often that decision is genuinely site-specific
> (how often a particular kitchen needs deep cleaning depends on the kitchen).
> So the onboarding flow needs a step where a client sets cadences for duties the
> guideline leaves open, and the module catalogue should be honest that some
> obligations arrive as templates requiring a local decision rather than as
> ready-made schedules. That prose must be promoted by a human, never parsed — a
> mis-parsed trigger produces a compliance deadline nobody agreed to.
>
> Add `trigger_event TEXT` and make the model explicit that an obligation is
> *either* periodic *or* event-triggered, with a CHECK that exactly one is set —
> the same both-or-neither discipline 022 applies to verification provenance.
> Event-triggered obligations become due when the triggering event is recorded
> and overdue when the evidence does not follow within `grace_days`. Worth doing
> in Phase 1: retrofitting it means revisiting every obligation already loaded.

### 4.4 `certificates` — third-party examination with an expiry

The plant-certificate primitive (§6, Phase 3). Distinct from `lab_samples`
because nothing is measured and nothing is judged against a limit: a competent
person examines a crane and issues a certificate with a validity period.

```
certificates
  id, organization_id, site_id
  asset_id               → assets.id      (plant: crane, boiler, MEWP)
  subject_user_id        → user_profiles  (person: lifeguard, OHS officer)
  standard_id            → standards.id
  certificate_no, issuer, issuer_accreditation
  issued_on, valid_until
  outcome                'pass' | 'pass_with_conditions' | 'fail'
  conditions             TEXT
  source_filename, source_sha256, raw_extraction   (forensic pattern from 016)
  reviewer_status
  CHECK (exactly one of asset_id / subject_user_id is set)
```

Plant and people share the expiry primitive but are never the same row.

### 4.5 `guideline_modules` and `organization_entitlements` — the commercial layer

The unit of sale is a **guideline module**, not a site. A client ticks the
reports they need; the charge rises with the number ticked.

```
guideline_modules                      the catalogue — every module, sellable
  id, standard_id → standards.id
  key, label, category
  obligation_type
  list_price_monthly
  status              'available' | 'coming_soon' | 'retired'
  provenance          'verified' | 'unverified'    (§7.1)

organization_entitlements
  id, organization_id
  module_id           → guideline_modules.id
  active_from, active_until
  price_agreed        NULL = list price
  UNIQUE (organization_id, module_id) WHERE active
```

**The governing rule: an obligation may only exist for an entitled module.**
That single constraint makes the ticking exercise simultaneously the onboarding
flow, the billing driver, and the scope of what the app monitors. It is why
entitlements must land *with* the obligation registry in Phase 1 rather than
arriving later as a billing afterthought.

It also produces a self-generating upsell: an unentitled module whose asset
types are present on a client's sites can be surfaced as "you have assets that
look like this and you are not monitoring them." The product writes its own
compliance-gap pitch.

**Pricing shape (§8 decision 4):** a base platform fee covering sites, users and
the platform, plus a per-module add-on. `billing.py`'s site-count tiers are
replaced. `payments/` is unaffected — the provider abstraction does not care
what is being charged for.

### 4.6 Checklists (Phase 3)

`checklist_templates` (versioned against a `standard_id`) → `checklist_items` →
`inspections` → `inspection_findings`, with findings feeding the existing
corrective-action table.

> **Reading the documents showed this model is half right, and that Phase 4
> needs a second primitive it does not currently budget for.**
>
> **GU137 — the Phase 4 lead — is not a checklist at all.** It sets no
> checkpoint, no acceptance criterion and no failure condition. Its Appendix A is
> a *register*: the inverse shape of a checklist, with fixed columns and variable
> unbounded rows, one per hazard identified. It cannot be expressed as
> `checklist_items` without pretending ten columns are ten items. Phase 4
> therefore needs `risk_assessments` → `risk_assessment_entries` alongside the
> checklist tables. GU137 is `module_kind = process` (§7.12) — it cannot say
> COMPLIANT. Its 3×3 matrix is labelled "an example" and is asymmetric (High
> probability × Low impact = Low), so it must never be recomputed as
> probability × severity.
>
> **The `inspections` → `findings` half fits well.** The template half needs:
> `parent_item_id` (GU84 has 43 unscored group-header rows; GU83 is flat, from
> the same DM template), `spec_limit_id` (about thirty items across four of five
> documents require a *measurement* — GU85 alone carries 19 numeric thresholds,
> so checklists and limits are a hybrid, not alternatives), an applicability
> predicate, and a `template_provenance` flag — because **GU85 states outright
> that its scored checklist lives in DM's internal system, not in the published
> document.** Some templates can only ever be partial.
>
> **Severity vocabulary must be namespaced per standard, never global.** GU83 and
> GU84 use incompatible vocabularies: "Minor" is a risk *outcome* in GU83 and a
> severity *input* in GU84; "Medium" is the reverse; GU83 grades A–F with no E,
> GU84 grades A–E with no F, and grade A means different things in each. A single
> enum will silently mis-map. It also has no slot for **Catastrophic**, and
> collapsing that into `critical` is substantive — one Catastrophic is grade F
> alone, where five Criticals would be needed otherwise.
>
> **Do not implement either grading formula.** Both join bands with an
> undecidable `&/or`, GU83's grades A and B overlap, and a zero-violation
> establishment matches no band at all. Emit violation counts and let the grade
> stay the regulator's to assign.
>
> Also confirmed: templates are genuinely versioned against an edition — GU85's
> change log shows the requirement set changing between editions — which
> validates hanging them off `standard_id`.

### 4.7 `laboratories` — who is permitted to produce the evidence (Phase 1)

Dubai Municipality accredits the laboratories. An FM contractor may not
self-test: every quantitative obligation must be discharged by an **independent,
DM-accredited** laboratory. Evidence from a laboratory that was not accredited —
or whose accreditation had lapsed **on the sampling date** — is rejected by DM.

Today the app cannot see that failure. `issuer_accreditation` on §4.4 is a free
text field on a table that does not yet exist, and nothing checks it.

```
laboratories
  id
  name                   'Wimpey Laboratories'
  authority              'DM'  — same reasoning as §4.1
  accreditation_no
  accredited_from, accredited_until
  scope_of_accreditation → parameter keys or test families this lab may certify
  status                 'active' | 'lapsed' | 'withdrawn'
  verified_by, verified_on   provenance — same rule as §7.1
```

Two design points follow from the constraint:

- **The check is against the sampling date, not today.** A certificate issued
  while the laboratory was accredited stays valid after the accreditation
  lapses. This is the same reasoning `core/standards.py::citation_is_stale`
  already applies to guideline editions, and it should be implemented the same
  way.
- **Accreditation is scoped by test family, not held wholesale.** A laboratory
  accredited for chemistry but not for *Legionella* enumeration cannot certify a
  GU44 result. The gate therefore checks the *parameter*, not merely the
  laboratory — which is why `scope_of_accreditation` exists rather than a bare
  boolean. See §8 still-open.

Implemented as a new gate in `ingestion/gates.py`, which is where the existing
assurance gateway lives and already classifies failures rather than repairing
them. Surfaced as a first-class report status, per the dashboard tile already
sketched in `Lab Reports Example/Extraction and reporting protocol.md`.

---

## 5. Migration path off `core/constants.py`

Non-breaking, in this order.

**Step 1 — introduce, don't switch.** Create `standards`, `specification_sets`,
`spec_limits`. Seed a built-in set `lagoon_dm_water` generated *from*
`COMPLIANCE_LIMITS`. Seed `standards` from `KNOWN_EDITIONS` (one row today,
GU44 V.6).

**Step 2 — read through a resolver.** Add `core/specs.py` exposing
`resolve_limits(asset) -> SpecSet | None` and `judge(result, limits) -> verdict`.
Reimplement `core/calculations.py` on top of it. `COMPLIANCE_LIMITS` remains in
`core/constants.py` as seed source and test fixture, but nothing outside the
seeder reads it directly.

> **Step 2 is larger than it looks.** A codebase audit found the verdict logic
> is not one implementation but **eight**, and they already disagree:
> `core/calculations.py:15-51` (the canonical one), a second inline copy of all
> ten limits in `core/alert_engine.py:88-110`, a private limits dict in
> `ui/monitoring.py:41-66`, a hand-copied TypeScript duplicate in
> `frontend/src/constants.ts:10-21`, three further TS verdict engines in
> `Dashboard.tsx:21-27`, `ComplianceReport.tsx:290-292` and `Chemistry.tsx:244-246`,
> and `ingestion/gates.py:99-179`, which judges the laboratory's own printed
> specification.
>
> **The good news first, because it bounds the risk: not one limit VALUE differs
> anywhere.** All eight sites use 6.0/9.0, 4.0, 50, 75, 50, 5.0, 5.0, 10, 200,
> 1000 wherever they carry a number, and `frontend/src/constants.ts` is
> character-for-character identical to `core/constants.py`. Every divergence below
> is an operator, a band, a label or a coverage gap — never a different number.
> Consolidation is therefore a tractable job rather than an archaeology exercise.
>
> Verified divergences, all confirmed by reading the code:
>
> - **Strictness, and it is nine of ten parameters, not one.** Every Python site
>   is strict (`value < max`, `value > min`); all three TypeScript engines are
>   inclusive. Only pH agrees, because it is inclusive everywhere. So DO = 4.0,
>   TSS = 50, COD = 50, turbidity = 75, ammonia = 5.0, phosphate = 5.0,
>   oil & grease = 10, E. coli = 200 and coliforms = 1000 each render **green on
>   screen and red in the PDF for the same reading.** Laboratories report values
>   on exactly these round numbers routinely, so this is live, not theoretical.
> - **`ingestion/gates.py` is the eighth site and the one that matters most.**
>   Its regex at `gates.py:143` explicitly matches the `<` or `≤` glyph on the
>   laboratory's printed specification — and then discards it, judging inclusively
>   at `gates.py:173`. A printed `"<1000"` and a printed `"1000"` become the same
>   limit. This is the only divergence that sits on a document the regulator has
>   actually seen, and after seeding, a coliform result of exactly 1000 against a
>   printed `"<1000"` is a PASS by the gate and a breach by the resolver. Under
>   decision 6 that surfaces as a finding — which is right, but the finding would
>   be *ours*, not the laboratory's. Fix the gate before it starts generating
>   false disagreements. Note also that the comment at `gates.py:163` argues the
>   opposite of what the branch beneath it does.
> - **Four risk-band schemes, not two.** `calculations.py:35-40` uses 10/30;
>   `Dashboard.tsx:37-49` uses 20/50; `ComplianceReport.tsx:310-322` uses 0/25;
>   `ui/monitoring.py:57-65` uses 0.8×/1.2× of the raw limit rather than a margin
>   percentage at all.
> - **The pH margin formula differs structurally.** `calculations.py:25` divides
>   the two-sided margin by the range size; `Dashboard.tsx:32-33` and
>   `ComplianceReport.tsx:295-300` test the maximum first and so compute
>   `(9.0 − v)/9.0`, ignoring the lower bound entirely. pH 6.1 — nearly on the
>   floor — is 3.3% and HIGH risk in Python, 32% and LOW in the UI. This will
>   surface during consolidation as a parity failure that looks like a bug in the
>   new resolver and is not.
> - **Coverage gaps masquerading as agreement.** `ui/monitoring.py` judges six of
>   the ten parameters; `Chemistry.tsx:69-78` judges eight, silently omitting
>   E. coli and total coliforms. A parameter that is never judged agrees with
>   everything.
> - **The verdict string, and the trap behind it — now fixed.**
>   `compliance_summary` emits `NON-COMPLIANT` where the lab path and database use
>   `NON_COMPLIANT`, and `status.ts` bridged the two with a `.includes('NON')`
>   substring test. That bridge failed in the dangerous direction: any status
>   outside the vocabulary — `INCOMPLETE`, `NOT_ASSESSED`, an unrecognised value,
>   or an absent one — contains no `NON` and no failing parameters, and so fell
>   through to **green**.
>
>   **Corrected scope, verified rather than assumed:** this was *latent*, not a
>   live miscolouring. `readings[].compliance` is fed only by
>   `compliance_summary`, which emits just the two verdicts; certificates carrying
>   `INCOMPLETE` travel in a separate array that `ComplianceReport.tsx` and
>   `Monitoring.tsx` already render amber correctly. So the defect was armed and
>   one producer change away from firing — which is exactly what landing
>   `core/specs.py` would have done, since it emits `NOT_ASSESSED`.
>
>   Fixed by normalising both spellings to one canonical verdict at a single
>   boundary and giving unjudged results their own grey light. Green is now
>   reachable only on an explicit `COMPLIANT`. Confirmed against the old
>   implementation over a 24-case table: every transition is green → grey, with no
>   green↔red movement and no case newly rendering green.
>
> Step 2 is therefore a consolidation, not a swap. Sequence it as: land the
> resolver, prove parity against `check_compliance` over a value grid for all ten
> parameters *at exactly the bound*, then retire the copies one at a time behind
> that parity test.
>
> **Progress: two of the three Python copies are retired.**
> `core/alert_engine.py` and `ui/monitoring.py` now judge through
> `core/specs.py::lagoon_spec_set()`, which builds the built-in set from
> `core/constants.py` without a database — so a limit corrected in one place
> reaches every in-process caller. `BOUND_RULES` moved from `db/seed_standards.py`
> into `core/constants.py` for the same reason: it is domain data, and runtime
> code must not import from `db/`.
>
> Both were verified by differential runs against the retired implementations —
> 632 readings for the alert engine, 210 cells for the monitoring view — rather
> than by trusting that the values matched. The alert engine's differential
> earned its keep: verdicts and precedence were identical, but the *wording* had
> drifted, because `SpecLimit` carries the limit's real unit while the old
> messages used shorter ones (pH gained "pH Units", E. coli became "CFU/100mL").
> That is the failure mode of a consolidation — the logic is right and the output
> changes underneath somebody. `tests/test_alert_breach_wording.py` now pins every
> string.
>
> Deliberately NOT changed in the same pass: `ui/monitoring.py`'s amber band
> (0.8x / 1.2x) is a fourth risk-band scheme, and unifying the bands changes what
> users see. This pass changed only where the *breach* comes from.
>
> Remaining: `core/calculations.py` stays as the canonical implementation and the
> parity reference. The three TypeScript engines and `ingestion/gates.py`'s
> printed-spec path are separate — the first flip verdicts and need the owner's
> decision (`frontend/VERDICT_DIVERGENCE.md`), the second is intentionally a
> second opinion under §8 decision 6. The data half of that proof already exists in
> `tests/test_seed_standards.py`, written before the resolver so that it
> constrains the resolver rather than agreeing with it by construction.

**Step 3 — prove with a second scope.** Add the facilities Legionella set
(GU44) — the gap in §3.3 — and judge the existing `lab_samples` rows against it.
This is the first real test that the resolver generalises, and it uses data
already in the database.

**Step 4 — widen.** Further guidelines become seed data plus a limit table.
**Acceptance criterion for the phase: a new guideline requires no Python change.**

Guardrails that already exist and must not regress:

- A `sampled` asset with no scope resolves to `None`, never a default.
  `resolve_limits` returns `None` and the result stays `NOT_ASSESSED`.
  Defaulting produces a confident wrong verdict — see the `assets.scope` column
  comment in migration 019.
- `raw_extraction` and `value_raw` stay immutable and verbatim.
- Org overrides may narrow limits, never silently replace a built-in set without
  recording that they did.

---

## 6. Build order

Sequenced so the risky generalisation happens before there is much to
generalise, and so the first modules to reach market are the ones that reuse the
laboratory pipeline this codebase already has (§8 decision 7).

> **Revision 3 re-sequenced this section.** Revision 2 led with the plant
> certificate modules on the reasoning that they sell to every FM contractor
> regardless of site type. That advantage is real but was outweighed: the
> certificate and checklist primitives are both *new*, whereas the quantitative
> family reuses `ingestion/`, `extract.py`, `core/specs.py` and the whole
> lab-data assurance gateway. Building certificates first would also have
> deferred the two known pipeline defects (§7.7 and the §5 step-2 note) behind a
> primitive that does not touch them, leaving them live under the Safari Park
> deployment. The old Phase 2 and 3 become Phase 3 and 4; the old Phase 4 leads.

### Phase 1 — Registries, entitlements, laboratories, and proof on GU44
Migrations per §4.1–4.3, §4.5 and §4.7, plus `core/specs.py` and the §5
migration path. Ships an Obligations view (due / due soon / overdue per site), a
module catalogue with entitlement ticking, and the laboratory accreditation gate.

**GU44 Legionella completes inside this phase, not as a Phase 2 SKU.** Not for
revenue — because it is the only guideline with real certificates already in the
database, and therefore the only way to prove the registry works before three
SKUs are built on top of it. Al Ghurair also carries a live obligation against
it.

Also in scope: replace `billing.py`'s site-count tiers with base + per-module.

### Phase 2 — Quantitative guidelines (first revenue modules)
Every module here is a numeric limit judged by `core/specs.py` against evidence
the existing pipeline already ingests. **Acceptance criterion from §5 step 4
applies: each of these should be seed data plus a limit table, with no Python
change.** If one of them forces a code change, that is a defect in the resolver
and should be fixed there rather than special-cased.

Ordered by how many clients carry the obligation — **revised against the actual
documents**, which contradicted the assumptions this table was first built on:

| Guideline | Subject | Evidence | Status after reading it |
|---|---|---|---|
| **GU119** | Indoor air quality | instrument | **Leads.** The only one with explicit "must not be exceeded" limits |
| GU81 / GU80 | Public / private swimming pools | laboratory | Solid; 49 limits extracted |
| GU142 | Mould remediation and control | laboratory | Solid |
| GU120 / GU145 | Water features; water coolers and dispensers | laboratory | GU145 is **Arabic** — see §7.2 |
| GU133 / GU17 | Water systems in emergencies; un-bottled drinking water | laboratory | GU17 is **English**, not Arabic as previously recorded |
| GU38 | Heat stress at work | instrument | **Cannot yield a verdict** — see below |
| GU141 | EIAQI index | instrument | **Deferred** — see below |
| GU34 | Pool plan approval | — | Process document, no limits |
| GU10 | Classroom ventilation | instrument | **Not self-contained** — delegates to ASHRAE 62.1 |
| GU78 | Ionizing radiation | dosimetry service | **Dead link** on the DM portal (§7.11) |

> **Three corrections that came from reading the documents rather than the list.**
>
> **GU38 is not a WBGT guideline and sets no compliance limit.** The string
> "WBGT" does not appear in V3.0 and there is no work/rest ratio table; it uses
> **Heat Index**, in a four-row table whose third column is headed "Control
> Approach" — management effort, not permissibility. Even the top band (46 ºC+)
> says "enhanced controls", not stop work. The only stop-work language sits in an
> Annex A chart legend that contradicts the main table for the same temperature
> range, and the actual midday-break rule is delegated to a MoHRE regulation GU38
> neither reproduces nor cites by number. Its only hard ceilings are core body
> temperature (≤38.5 / ≤38 ºC) — clinical, measured on a person, not an
> instrument parameter anyone sells monitoring for.
>
> **So a GU38 report cannot claim COMPLIANT or NON-COMPLIANT.** It can classify a
> risk band and track obligations, which is a real product — but it is a
> *monitoring* module, not a *compliance* module, and it must not be sold or
> templated as the latter. This is the §7.12 distinction in its first concrete
> instance, and it needs settling before GU38 is priced.
>
> **GU141 is a calculation engine, not a limit table, and it is internally
> inconsistent.** It publishes two mutually incompatible methods for the final
> score (§7.8 weighted summation versus Figure No.1's integer-weightage scheme),
> its weights table is contradicted by its own worked example, and it never states
> which EIAQI band constitutes compliance. It would breach the §5 step-4
> no-Python-change criterion *and* could not produce a verdict even if implemented
> perfectly. Deferred until DM clarifies; GU119 carries the indoor-air module
> alone.
>
> **GU10 delegates its binding requirement wholesale to ASHRAE 62.1.** The 295 /
> 345 CFM figures it prints are explicitly area-dependent. What remains is a
> floor-plan and register check, not an instrument reading — closer to the Phase 4
> checklist primitive than to this phase.

> **The family is wider than "laboratory".** WBGT, EIAQI and classroom
> ventilation are quantitative measurements against numeric limits, so
> `core/specs.py` judges them identically — but the evidence arrives from an
> instrument or a monitoring contractor, not a sample sent away. That is good for
> the product (more SKUs on one resolver) and it means the §4.7 accreditation
> gate applies to the laboratory subset only. Do not conflate the two when
> sizing either the ingestion work or the laboratory relationship.

### Phase 3 — Universal plant certificates
Builds the §4.4 certificate primitive — a new primitive, reusing nothing from
`ingestion/`. **Reading the five documents cut this from five SKUs to three.**

| Guideline | Subject | Verdict after reading it |
|---|---|---|
| GU48 | Lifting appliances | **Fits.** EIAC third-party examination, 12-month |
| GU67 | MEWP | **Fits.** EIAC third-party examination, 6-month |
| GU146 | Safe forklift operations | **Fits.** EIAC third-party examination, 12-month |
| GU47 | Boilers and pressure vessels | **Arabic-only** (§7.2). V5.0, 2026-01-20 — the newest document in the group, so translating it is not wasted work |
| GU74 | Mobile access towers | **Moved to Phase 4.** No accredited third party at all: the recurring duty is an in-house 7-day inspection, and the only third-party artefact is a one-off BS EN 1004 product conformity certification that never expires |
| GU41 | Guarding of dangerous machinery | **Moved to Phase 4.** Names no accreditation body, issues no certificate; thirteen asset types of guard-design specification. A checklist guideline |

Building GU74 or GU41 as certificate SKUs would ship a module whose central
artefact the source document never requires.

> **The finding that has to be settled before the primitive is built: not one of
> the five documents states a certificate validity period.** They all state an
> examination *interval* and stop. So §4.4's `valid_until` **cannot be derived
> from the standard.** It must either come from the uploaded certificate itself,
> or from an `issued_on + interval` assumption that is explicitly recorded as an
> assumption. Silently computing it would put an expiry date on a
> regulator-facing report that no published document supports.
>
> **Two model gaps §4.4 does not cover.** First, an `examinations` layer is
> needed between `standards` and `certificates`: GU146 alone imposes three
> different examinations at three cadences on one asset, so examination
> requirements are not a property of the certificate. Second, **one asset must
> not generate two overdue obligations** — GU48 and GU146 both impose a 12-month
> EIAC test on forklifts, and a contractor entitled to both modules would
> otherwise see the same test due twice. Obligation de-duplication across
> overlapping guidelines is a Phase 1 design question, not a Phase 3 one.
>
> Of the 29 examination requirements extracted, **14 are event-triggered with no
> cadence** — after repair, after modification, before first use. That
> independently confirms the `trigger_event` column added to §4.3.

### Phase 4 — Risk assessment (checklist primitive)
GU137 (H&S risk assessment) and GU135 (built-environment establishments). Also
near-universal, but needs the §4.6 checklist engine — the third new primitive,
which is why it follows the other two rather than accompanying them.

### Phase 5 — People, competency and permits

> **This phase was scoped as cheap and is not.** The plan was to reuse the Phase 3
> expiry primitive against `subject_user_id`. Reading twelve of the documents
> shows the expiry half reuses directly and four things do not:
>
> - **Validity is derived, not stored.** The Lifeguard scheme sets certification
>   validity at MIN(2 years, remaining training-record validity). A plain
>   `valid_until` date goes silently wrong when a *different* row lapses.
> - **Renewal anchors to the previous expiry, not to the examination.** Computing
>   `issued_on + 24 months` over-grants by up to two months — a mis-issuance, on a
>   certificate naming a person.
> - **Status is not a function of dates.** The Lifeguard scheme lists six
>   revocation grounds; a *sector change* invalidates an OHS Person in Charge
>   certificate; an establishment's inspection grade can cancel individuals'
>   certificates. A date-driven model reports these as valid.
> - **The requirement is coverage, not holding.** One certified Person in Charge
>   is required *per shift per location*, present throughout. That is a roster
>   question, and no set of certificate rows answers it.
>
> Two further mismatches with §4.4 specifically: specialty scope gates validity
> (a Shallow Water lifeguard supervising 2 m of water holds a valid certificate
> and is non-compliant), and person-certificates are site-tied, which §4.4's
> exactly-one-of-asset-or-person CHECK forbids.
>
> A `people_credentials` + `coverage_requirements` shape is sketched in
> `data/dm_guidelines/competency_group_notes.md` §3.9. Budget Phase 5 as a new
> primitive, not a reuse.

**Two documents are in the wrong phase.** SP06 (NOC to practise H&S activities)
is not a competency document at all — "health and safety activities" is a
*commercial licence category* (salons, spas, gyms, laundries) and the document is
a premises permit assessed against a furniture-layout drawing, with no competency
content, no expiry and nothing to schedule. It belongs at the front of the Phase 6
bundle it delegates to. GU42 likewise has no people content, and contrary to the
catalogue's classification sets **no thorough-examination requirement at all**.

**GU43 is `delegating` and that has a commercial consequence.** It sets no
exposure value of any kind; §5-1 points at the ACGIH TLVs. A verdict-bearing GU43
therefore needs an ACGIH licence — those values are copyrighted and sold. Until
that is bought it can only ship as an obligations module.

**GU66 is `monitoring`, not `compliance`.** It is full of numbers — 12h/8h
shifts, 54/108/215 lux — but every one sits under a heading reading
"Recommended", with controls "may be exercised as applicable". Telling a client
they are NON-COMPLIANT for a 13-hour shift asserts a rule DM did not make. Its
mandatory core — risk assessment, clinic health screening, training plan — is
what makes it sellable.

Reuses the Phase 3 expiry primitive where it fits, adds permit-to-work.

| Guideline | Subject |
|---|---|
| — | OHS Practitioner / OHS Person in Charge certification schemes |
| — | Lifeguard scheme; NOC to practise H&S activities |
| GU131 | H&S officer in labour accommodations |
| GU39 / GU35 | Confined space entry; rope access |
| GU72 / GU99 / GU66 | Eyewash and showers; safety signs; night and shift work |
| GU50 / GU43 / GU42 | Asbestos; industrial organic solvents; paint spray booths |
| GU59–61, 65, 97, 98 | PPE: eye/face, clothing, hearing, head, foot, hand |

PPE is an issuance-and-inspection register and should ride on
`core/inventory.py` rather than get its own module.

### Phase 6 — Establishment compliance checklists
Broad catalogue expansion once the checklist engine is proven: GU83, GU84,
GU85, GU93, GU90, GU129, GU125, GU15, GU13, GU19, GU75, GU77, GU95, GU76,
GU118, GU136, GU46, GU121, GU02, GU130, GU124.

---

## 7. Risks and standing costs

**7.1 Content is the product line, not overhead.** Under modular pricing every
guideline encoded is a SKU, so editorial work converts directly into sellable
inventory — the opposite of a cost centre. But it raises the stakes: **a wrong
limit in a sold module is a liability, not a bug.**

The decision taken (§8, decision 5) is a **narrow verified catalogue**: only
modules personally verified against the published DM PDF go on sale. This
matches the rule already written into `core/standards.py` — only add an entry
when you have the document in front of you, because a wrong "your citation is
out of date" warning sends the client to argue with their laboratory over
nothing. The `provenance` field on `guideline_modules` and `verified_by` /
`verified_on` on `standards` enforce it in the schema rather than by good
intentions. Revisit resourcing once modules are selling.

**7.2 Arabic-only sources — corrected against the published catalogue.** The
earlier list in this section was wrong in both directions, and the correction
changes phase priorities rather than merely tidying a footnote.

**Wrong in our favour:** GU17 and GU129 are now published in **English**. GU17
(un-bottled drinking water) was called out as a Phase 2 obstacle and is not one.

**Wrong against us:** thirteen documents are Arabic, ten of which were unnamed
here. Two sit on the critical path:

| Guideline | Subject | Phase | Why it hurts |
|---|---|---|---|
| **GU145** | Water coolers and dispensers | **2** | A leading revenue module needs translation before its limits can be encoded |
| **GU47** | Boilers and pressure vessels | **3** | One of the three priority certificate SKUs |
| GU135 | Risk assessment of buildings | 4 | Pairs with GU137, which is English |
| GU72, GU97, GU90 | Eyewash/showers, PPE, temporary structures | 5–6 | Later, but budget for them |

Remaining Arabic: GU143, GU130, GU125, GU124, GU118, GU115, GU29.

So translation is not a tail-end problem to sequence last — it is a **Phase 2 and
Phase 3 dependency** with two priority SKUs behind it. Budget a native-Arabic
reviewer before those phases begin, not within them. Note also that the catalogue
distinguishes seven documents *explicitly stated* as Arabic from six *inferred
from an Arabic filename*; the inferred ones should be confirmed by opening them
before any translation is commissioned.

Source: `data/dm_guidelines/catalogue.json`, extracted from the DM technical
guidelines list. Unverified per §7.1 — confirm before acting on the budget.

**7.3 The science layer demotes.** `science/` does not generalise beyond
lagoons. It stops being the headline and becomes a premium module for one scope.
That is a deliberate marketing loss — but it remains the most defensible
technical work in the repo and should be re-shelved, not hidden.

**7.4 Scope-resolution safety must survive generalisation.** The most dangerous
failure mode is applying one scope's limits to another scope's asset and
returning a confident wrong verdict. With two scopes this is a small risk; with
eighty modules it is the central one. `resolve_limits` returning `None` must
stay a first-class, visible UI outcome ("cannot be judged — asset
unclassified"), never a silent pass.

**7.5 Entitlement must not become a compliance hole.** If a client un-ticks a
module, their obligations under it stop being monitored — which is commercially
correct and a genuine safety consideration. Deactivating an entitlement must
retain history, warn explicitly about what stops being tracked, and never
silently delete obligations or evidence.

**7.6 Two-repo divergence is now bounded.** `DECCA-Lagoons-App` is a frozen
rollback point (§8 decision 1). It receives no changes, so there is no porting
burden — but it also means the live Safari Park deployment must eventually be
served by this repo. Plan that cutover explicitly during Phase 1.

**7.7 The vision extraction path fabricates magnitudes, and must be fixed
before the resolver consumes it.** `extract.py:72` instructs the model: *"For
values like '< 0.05' or 'ND', use the detection limit number and note it"*, and
its schema is `Optional[float]`, so the qualifier cannot survive.
`ingestion/router.py:77-81` then applies a bare `float(value)`, dropping
qualifiers entirely. Both contradict `ingestion/wimpey.py:178-193`, which models
`'<1'` as `(1.0, '<')` honestly, and both contradict migration 016's explicit
rule that a below-LOQ non-detect must never be collapsed into a measured value.

This is a pre-existing defect, not one this work introduces — but it becomes
load-bearing the moment `qualifier_rule` starts judging these rows, because
careful below-LOQ logic built on invented numbers is worse than no logic. Fix it
in Phase 1, before step 3.

**7.8 A parser per laboratory looks like a treadmill and is not.** `wimpey.py`
is a hand-written positional parser for one laboratory's LIMS forms, and the
obvious fear is that every new laboratory costs another one, forever. It does
not: **DM accredits the laboratories, so the set is closed and knowable.**
Supporting all of them is a project with an end, and completing it means owning
the ingestion layer for the whole regulated market — a far harder position to
displace than a catalogue of limit tables, which a competitor can retype.

Treat the accredited list as the parser backlog, sequenced by how many client
sites each laboratory serves. Two cautions: the vision fallback in `extract.py`
must remain the honest low-confidence path for anything unparsed (§7.7), never a
silent substitute for a missing parser; and a laboratory changing its form
revision breaks a deterministic parser loudly, which is correct — `gates.py`
already classifies parser-bug versus source anomaly, and that classification is
what stops a layout change becoming a wrong number.

**7.9 The independence requirement cuts both ways.** DM requires the laboratory
to be independent of the FM contractor. A product that let the contractor lean on
the laboratory — silently overriding a certified statement, or quietly
re-judging a result until it passed — would be structurally unacceptable to the
regulator and to the laboratory. Decision 6 is therefore not merely good manners:
it is what makes the platform admissible to both sides of a relationship the
regulation deliberately keeps at arm's length. It must not be weakened for
convenience later.

**7.11 What the published catalogue actually contains.** The DM technical
guidelines list carries **81 entries** — 77 numbered guidelines plus four
unnumbered scheme documents (Lifeguard, OHS Practitioner, OHS Person in Charge,
NOC to practise H&S activities). All 81 are captured in
`data/dm_guidelines/catalogue.json`. Four findings change how the registry is
loaded:

- **No issue date is published anywhere.** Each page shows a `Date` field that is
  the CMS record date, not the edition date — GU44's page reads 27/07/2026 while
  its V.6 edition issued 2025-08-19. It is stored as `portal_document_date` and
  **must never be loaded into `standards.issued_on`.** Doing so would feed
  `citation_is_stale` a fabricated date and produce exactly the wrong-staleness
  warnings §7.1 exists to prevent. Issue dates come from inside the PDF only.

  Worse than first recorded: **25 rows differ from the real issue date in the
  *year*,** and GU115's portal date falls a year *earlier* than its issue date,
  so it is not even a safe upper bound.

  80 of 81 editions have since been read off the PDFs themselves
  (`catalogue_editions.json`), each with a page and the printed line. Only GU78
  could not be — its link redirects to the DM home page.

- **The day/month ambiguity is bounded, and less dangerous than it looks.**
  Thirteen editions print their date numerically with both components ≤ 12, so
  that document alone cannot fix the convention. Seven were settled from internal
  evidence and none of the seven changed a date. The important structural point:
  **all thirteen carry a four-digit year in third position, so transposing day
  and month cannot move the year** — and `citation_is_stale` compares years only.
  The false "your citation is out of date" warning §7.1 forbids is therefore
  *impossible* for this set, resolved or not.

  The residual exposure is the `sampled_at < current_issue` guard, which is a
  full-date comparison. The widest unresolved window is GU67 at three months, and
  none of the six unresolved documents is in `KNOWN_EDITIONS` yet.

  Two findings from that pass worth acting on: **GU120's cover contains a one-day
  typo** — it reads 12/03/2024 where the history log and all seven page footers
  say "11th March 2024", eight printings against one, so the log is kept and DM
  should be asked to correct the cover. And GU99 was recorded as an internal
  disagreement but has none; its cover simply carries no date field.
- **GU78 (ionizing radiation) is a dead link** — it redirects to the DM home page
  with no PDF and no code. It is a Phase 2 module, so it needs chasing with DM
  directly rather than waiting to be found.
- **GU10 carries a number/code conflict:** listed as guideline 10, but its file is
  `DM-HSD-GU101-VSC2`. One of the two is a DM typo and there is no GU101 row to
  disambiguate. Both are recorded as printed. This is precisely the case where a
  wrong code silently breaks citation matching, so it must be resolved with DM
  before the module ships.
- **Nineteen entries are not named in §6 at all.** Two clusters are worth a
  decision: the consumer-product laboratory family (GU132/117/116/115/107/100/86/
  82/30/29/18), which reuses the Phase 2 resolver exactly but sells to *traders*
  rather than FM contractors — a different buyer and therefore arguably a
  different product; and GU62 (acetylene generators) plus GU53 (LPG cylinders),
  which share the Phase 3 certificate shape and the same buyer, making them the
  cheapest additions once that primitive exists.

Mechanically: URLs **cannot** be constructed from a guideline number — slugs use
three inconsistent conventions and the host alternates between `dm.gov.ae` and
`www.dm.gov.ae` — so `page_url` is stored per entry. Codes and versions exist
only inside PDF filenames, so `file_label` holds the exact printed filename as
the audit trail behind every extracted code, and is the right key to diff on when
refreshing: a new edition changes the filename while the list-page title does not.
The list needs no browser, just an HTTP fetch and a table parse; the WordPress
REST API is closed.

**7.12 Not every guideline can produce a verdict, and the catalogue must say
which.** Reading the first four documents properly turned up a distinction the
data model does not yet carry. A guideline can be any of:

| Kind | What a report can claim | Example |
|---|---|---|
| **Compliance** | COMPLIANT / NON-COMPLIANT against a stated limit | GU119, GU81 |
| **Monitoring** | a risk band and a control obligation, but no verdict | GU38 |
| **Process** | that a procedure was followed; no measurement | GU34 |
| **Delegating** | nothing on its own — the limit lives in an external standard | GU10 → ASHRAE 62.1 |
| **Unusable** | nothing; the document contradicts itself | GU141 |

This matters commercially and legally. Under modular pricing each of these is
still sellable — an FM contractor genuinely needs to track GU38 obligations — but
they are **not the same product**, and a report that claims compliance against a
guideline setting no compliance limit is a misrepresentation to a regulator. It
is also the precise failure §7.4 warns about, arriving from an unexpected
direction: not the wrong limits applied to an asset, but a verdict rendered where
the source document authorises none.

`guideline_modules` therefore needs a `module_kind` column alongside
`provenance`, and the resolver must refuse to emit a verdict for a module that is
not of kind `compliance`. Add it when §4.5 is built — retrofitting it after
reports exist means reissuing them.

**Verification traps found while extracting, which apply to every future
guideline:**

- **Never take `version` from a filename — and never take a *date* from one
  either.** GU119's URL says `_V2` while the document is V4; GU67's PDF sits
  under `/2021/05/` though the edition is 2024; GU74's under `/2021/01/` for a
  2025 edition; GU146's filename ends `10.5.26` for a December 2025 document.
  Upload paths record when a file was uploaded, not what is in it. Versions and
  issue dates come from inside the document, always.
- **Codes are not uniform.** GU146's code is `DM-HSD-146-FL2` — it omits the `GU`
  prefix every other guideline uses. Together with the GU10/GU101 conflict
  (§7.11), that is two of roughly eighty documents whose code would silently
  break citation matching if assumed to follow the pattern.
- **Omit an ambiguous cell, never guess it.** GU119's ozone short-term value
  prints as `0.1 2 ppm`; it was left out rather than assumed to be 0.12.
- **Verify column-to-unit mapping by x-coordinate, not text order.** A number
  attached to the wrong unit is a wrong verdict that looks entirely plausible,
  and this is the likeliest place for a silent transcription error.
- **Band tables have gaps, and gaps must resolve to NOT_ASSESSED.** A heat index
  of 34.5 or a CO₂ reading of 380 ppm falls between published bands. Snapping to
  the nearest band is exactly the confident wrong answer §7.4 forbids.

**7.13 A published guideline is not necessarily a live one.** GU93 is an
unrevised COVID-19 emergency measure (v2, January 2021) that now **contradicts**
GU85: GU93 requires one person per dining table while GU85 sizes the hall for a
third of the workforce at once. Both are currently published on the DM portal,
and nothing in the catalogue distinguishes them.

Selling GU93 as a live module would have a client enforcing a superseded
emergency rule against a current one. `standards` therefore needs
`lifecycle_status` — live / emergency / dormant / withdrawn — orthogonal to
`module_kind` (§7.12), which asks what a module can *claim* rather than whether
it still *applies*. Neither field substitutes for the other, and both gate
sellability.

This also means **currency cannot be derived from the edition chain alone.** A
document that nothing supersedes may still be dead — nobody issued a successor,
they simply stopped meaning it. `supersedes_id` answers "is there a newer
edition"; it cannot answer "is this still in force".

**7.13a Published DM documents contain defects, and encoding one is our
problem, not theirs.** Five found while extracting twelve people-and-competency
documents, all recorded as printed rather than normalised:

- **The OHS Person in Charge scheme's Annex D requires "a minimum total of
  twenty (20) hours" from components that sum to 24**, and §8.3.4 independently
  says 24. Encoded as 24. Reading Annex D alone ships a check four hours short of
  what the same document requires elsewhere.
- **Sibling schemes issued the same day disagree on failing grades** — one says
  "D or F", the other "D or E". Recorded as printed; normalising them would
  invent a rule.
- **GU131 clause 1.1 cross-refers to a clause 2.9 that does not exist** — the
  numbering stops at 2.8 — leaving its ≤50-room exemption unresolved.
- **The Lifeguard scheme lists "Lagoons & other water features Lifeguards" in
  scope with no prerequisites, no specialty examination and no depth rule.**
  Directly relevant to the current client base: do not assume the pool specialty
  covers a lagoon.
- **SP06's permitted-services matrix is 5×7 of tick and cross glyphs whose text
  layer returns the headers and not one cell value** — the strongest case yet for
  §7.14's render-and-read default.

Each of these is a question to put to DM, not a thing to fix in code. The
consistent rule: record what is printed, flag the contradiction, and let a human
adjudicate. A guideline that contradicts itself cannot be sold as a compliance
module until it is resolved (§7.12).

**7.14 Two extraction lessons that should become standing practice.**

- **Render-and-read must be the default for checklist guidelines, not the
  fallback.** Text extraction alone loses roughly a quarter of GU93 — pages 5, 7
  and 9 return blank while holding flowcharts, including the document's only
  decision point. A silently empty page is indistinguishable from a page with
  nothing on it.
- **Cross-references in DM documents cannot be trusted without checking.** GU83's
  annex cross-references are systematically off by one, and GU84 proves why: it
  cites the same annex numbers and they are correct there, so GU83's body was
  copied from GU84 without renumbering. Relatedly, GU83's cover and footers say
  V4.1 while its own history log tops out at 3, and its Part E is titled
  "Business activity Annexes" with **no activity-to-annex mapping printed
  anywhere** — the largest single content gap found so far, and one only DM can
  close.

**7.15 Pre-existing items unchanged by this proposal.** CORS is still
`allow_origins=["*"]`; invite email is not wired to a transactional provider;
billing has never processed a live payment.

Two undeclared dependencies, both of the same kind: `python-multipart` is missing
from `requirements.txt` despite `api_server` importing it, and **`pydantic` is
missing despite `ingestion/schema.py` importing it directly** — it resolves only
transitively through `fastapi`, unpinned. Between them, five test modules fail to
collect in a clean environment (`test_integration_phases`,
`test_lab_sample_persistence`, `test_report_types`, `test_resolver_authz`,
`test_wimpey_parser`). That is most of the coverage over the ingestion path this
build now depends on, and it directly contradicts the header of
`requirements.txt`, which promises that a rebuild installs exactly the tested
versions. All should close before the first paid module sale.

---

## 8. Decisions taken

| # | Decision | Choice |
|---|---|---|
| 1 | Role of `DECCA-Lagoons-App` | **Frozen rollback point.** DM-Tech-Apps becomes the single product with lagoon as one scope. No porting burden; cutover planned in Phase 1. |
| 2 | Multi-emirate support | **Authority as data, DM-only content.** `standards.authority` from day one; all seed data, UI and reports stay DM-specific. |
| 3 | Guideline build order | ~~Universal modules first — GU48, GU47, GU67, then GU137.~~ **Superseded by decision 7.** GU44 completing inside Phase 1 as the registry's proof survives unchanged. |
| 4 | Pricing shape | **Base platform fee + per-module add-on.** Replaces site-count tiers. |
| 5 | Guideline currency | **Narrow verified catalogue.** Only personally verified modules go on sale; provenance recorded in the schema. Revisit once selling. |
| 6 | Our limits vs the lab's printed specification | **Both verdicts; disagreement is a finding.** `ingestion/gates.py` keeps judging the laboratory's own printed spec; the resolver adds ours alongside. Where they differ, surface it — that usually means the lab judged against a superseded edition or the wrong limit for the asset, which is what `core/standards.py` already exists to catch. Never silently override an accredited laboratory's certified statement. |

| 7 | Which family to build first | **The quantitative/laboratory family, ahead of certificates and checklists.** Those two are new primitives; the quantitative family reuses `ingestion/`, `extract.py` and the assurance gateway that is already the most defensible work in the repo. It also forces the two known pipeline defects (§5 step 2, §7.7) to be fixed as part of shipping rather than deferred behind primitives that never touch them. §6 re-sequenced accordingly. |
| 8 | The laboratory's role | **Mandatory counterparty, and accreditation is modelled and gated.** DM accredits the laboratories and the FM may not self-test, so every quantitative obligation necessarily passes through an accredited independent lab — the lab is neither a marketing channel nor a customer but the other half of a transaction the platform already sits inside. `laboratories` registry per §4.7, checked at the sampling date and scoped by test family, surfaced as a first-class report status. The obligation registry (§4.3) is simultaneously the contractor's compliance alert and the laboratory's forward book of demand. |

### Still open

- **The accredited-laboratory list.** Whether DM publishes it in a form we can
  consult programmatically or must transcribe, and how often it changes. Governs
  whether §4.7 is maintained by import or by the same verified-catalogue
  discipline as §7.1. Needed before the accreditation gate ships.
- **Whether accreditation is scoped by test type.** If a laboratory can hold
  accreditation for chemistry but not for *Legionella* enumeration, the gate must
  check the parameter and not merely the laboratory — which is why §4.7 carries
  `scope_of_accreditation` rather than a boolean. Confirm against DM's published
  scope documents before that column's shape is fixed.
- **Selling to laboratories.** Decision 8 settles that labs are counterparties,
  not a channel. It does not settle whether a laboratory-side product (sample
  tracking, certificate issuance, client portals) is worth building later. That
  is a second product, not a module; defer until modules are selling.
- **Product name.** The repo is `DM-Tech-Apps`, which is a folder-and-repo name,
  not a product name. Deferred deliberately; needed before customer-facing UI
  and report templates are written (late Phase 1).
- **Al Ghurair's full reporting register.** Not a blocker for Phase 1, but the
  Phase 2 and 3 module priority should be sanity-checked against what they actually
  file across their whole portfolio before the three SKUs are finalised.
- **Safari Park cutover timing** (§7.6).
