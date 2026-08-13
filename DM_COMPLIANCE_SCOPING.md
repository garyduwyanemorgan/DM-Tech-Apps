# DM Compliance Monitoring — Scoping Document

> Status: **decisions taken, ready to build.** Written against the code at
> v1.8.0. Revision 2 — supersedes the initial draft; incorporates the modular
> commercial model and the five decisions recorded in §8.
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

### 4.4 `certificates` — third-party examination with an expiry

Tier 2's primitive, and the basis of the first three sellable modules (§6,
Phase 2). Distinct from `lab_samples` because nothing is measured: a competent
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
corrective-action table. Specified here only so earlier phases do not foreclose
it.

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
generalise, and so the first modules to reach market are the ones every FM
contractor must buy (§8 decision 3).

### Phase 1 — Registries, entitlements, and proof on GU44
Migrations per §4.1–4.3 and §4.5, plus `core/specs.py` and the §5 migration
path. Ships an Obligations view (due / due soon / overdue per site) and a module
catalogue with entitlement ticking.

**GU44 Legionella completes inside this phase, not as a Phase 2 SKU.** Not for
revenue — because it is the only guideline with real certificates already in the
database, and therefore the only way to prove the registry works before three
SKUs are built on top of it. Al Ghurair also carries a live obligation against
it.

Also in scope: replace `billing.py`'s site-count tiers with base + per-module.

### Phase 2 — Universal plant certificates (first revenue modules)
Builds the §4.4 certificate primitive, then three to six SKUs off it. These sell
to very nearly every FM contractor regardless of site type, which is why they go
first.

| Guideline | Subject |
|---|---|
| GU48 | Cranes, hoists, lifts and other lifting appliances |
| GU47 | Boilers and pressure vessels |
| GU67 | Mobile elevated work platforms (MEWP) |
| GU74 | Mobile access towers |
| GU146 | Safe forklift operations |
| GU41 | Guarding of dangerous machinery |

GU48, GU47 and GU67 are the priority three; the rest are cheap additions once
the primitive exists.

### Phase 3 — Risk assessment (checklist primitive)
GU137 (H&S risk assessment) and GU135 (built-environment establishments). Also
near-universal, but needs the §4.6 checklist engine, which is why it follows
rather than accompanies Phase 2.

### Phase 4 — Numeric-limit guidelines
Cheap once Phase 1 is proven — these reuse the existing lab pipeline and add
only limit tables.

| Guideline | Subject |
|---|---|
| GU81 / GU80 / GU34 | Public / private swimming pools; pool plan approval |
| GU120 / GU145 | Water features; water coolers and dispensers |
| GU133 / GU17 | Water systems in emergencies; un-bottled drinking water *(GU17 Arabic only)* |
| GU141 / GU119 | Environmental indoor air quality (EIAQI) |
| GU142 | Mould remediation and control |
| GU38 | Heat stress at work (WBGT) |
| GU10 / GU78 | Classroom ventilation; ionizing radiation |

### Phase 5 — People, competency and permits
Reuses the Phase 2 expiry primitive against `subject_user_id`, adds
permit-to-work.

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

**7.2 Arabic-only sources.** GU17, GU124, GU125, GU129, GU130 are published in
Arabic only. Limit encoding and extraction need Arabic handling and a
native-Arabic reviewer. Sequence last within their phase.

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

**7.7 Pre-existing items unchanged by this proposal.** CORS is still
`allow_origins=["*"]`; invite email is not wired to a transactional provider;
billing has never processed a live payment. All three should close before the
first paid module sale.

---

## 8. Decisions taken

| # | Decision | Choice |
|---|---|---|
| 1 | Role of `DECCA-Lagoons-App` | **Frozen rollback point.** DM-Tech-Apps becomes the single product with lagoon as one scope. No porting burden; cutover planned in Phase 1. |
| 2 | Multi-emirate support | **Authority as data, DM-only content.** `standards.authority` from day one; all seed data, UI and reports stay DM-specific. |
| 3 | Guideline build order | **Universal modules first** — GU48, GU47, GU67 (Phase 2), then GU137 (Phase 3). GU44 completes inside Phase 1 as the registry's proof. |
| 4 | Pricing shape | **Base platform fee + per-module add-on.** Replaces site-count tiers. |
| 5 | Guideline currency | **Narrow verified catalogue.** Only personally verified modules go on sale; provenance recorded in the schema. Revisit once selling. |

### Still open

- **Product name.** The repo is `DM-Tech-Apps`, which is a folder-and-repo name,
  not a product name. Deferred deliberately; needed before customer-facing UI
  and report templates are written (late Phase 1).
- **Al Ghurair's full reporting register.** Not a blocker for Phase 1, but the
  Phase 2 module priority should be sanity-checked against what they actually
  file across their whole portfolio before the three SKUs are finalised.
- **Safari Park cutover timing** (§7.6).
