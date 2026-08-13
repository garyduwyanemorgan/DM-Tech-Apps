# DM Compliance Monitoring — Scoping Document

> Status: **proposal, not yet approved.** Written against the code at v1.8.0.
> Purpose: define what it takes to generalise this product from lagoon water
> quality (Dubai Safari Park) to a Dubai Municipality compliance platform
> covering the published technical guidelines, and to sequence that work.
>
> Companion documents: `PRODUCT_OVERVIEW.md` (what the product is today),
> `PERMISSIONS_MATRIX.md` (roles and scope), `db/migrations/README.md`.

---

## 1. Thesis

The reusable asset in this codebase is not water chemistry. It is a loop:

```
registered asset
  → obligation on a cadence          (this asset must be tested/inspected every N)
    → evidence                        (lab certificate, inspection report, checklist)
      → verdict against a versioned standard
        → alert
          → corrective action with approval
            → auditable report
```

Water quality is one instantiation of that loop. The DM technical guidelines
list (https://www.dm.gov.ae/municipality-business/technical-guidelines-list/)
is roughly eighty instantiations of the same loop, against the same buyer —
the facilities manager who is accountable to Dubai Municipality for a site.

The build already contains the beginning of this generalisation. It was not
accidental: migration 019 and `core/assets.py` deliberately moved specification
scope onto the asset, with the reasoning recorded in both places. This document
proposes carrying that decision to its conclusion.

---

## 2. What exists today (verified against the code)

Generic — reusable across any guideline with no domain change:

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
| Inventory | `core/inventory.py`, mig. 009/011 | |
| Report generation | `reporting.py` | watermark-gated PDF |
| Billing / tenancy tiers | `billing.py`, `payments/` | provider-abstracted |

Lagoon-specific — does **not** generalise:

| Thing | Location | Disposition |
|---|---|---|
| `COMPLIANCE_LIMITS` (10 params) | `core/constants.py` | becomes one seeded specification set |
| Alert thresholds, treatment actions | `core/constants.py` | lagoon-only; stays behind lagoon scope |
| Species profiles, nutrient sources, enzymes | `core/constants.py` | lagoon-only reference data |
| Bloom forecasting / digital twin | `science/` | demotes to a premium specialist module |
| Seasonal phases | `core/constants.py` | lagoon-only |

### 2.1 The gap that forces the work

`assets.scope` permits `'lagoon' | 'facilities'`. `core/report_types.py`
documents the facilities scope as "governed by Dubai Municipality technical
guidelines (GU44) and, for chemistry, by client-specific DM-derived limits."

**But no facilities limit set exists in the code.** `COMPLIANCE_LIMITS` is
lagoon-only, and `core/calculations.py` reads from it exclusively. A facilities
result today is judged either by the laboratory's verbatim `specification`
string carried through on `lab_results.specification`, or not at all
(`status = 'NOT_ASSESSED'`).

So the half-built generalisation currently has a hole where the second scope's
limits should be. Filling that hole *properly* — rather than by adding a second
hardcoded Python dict — is the whole of Phase 1 below, and it is the fork in
the road. Adding `FACILITIES_LIMITS` next to `COMPLIANCE_LIMITS` would work for
one guideline and become unmaintainable at five.

---

## 3. Target data model

Four new concepts. Everything else stays.

### 3.1 `standards` — the guideline, and which edition is in force

Promotes `core/standards.py`'s in-code `KNOWN_EDITIONS` dict to a table, keeping
the module as the loader/validator. One row per DM guideline edition.

```
standards
  id, authority          'DM' (modelled as data — see §7.5)
  code                   'DM-HSD-GU44-LCWS2'   as laboratories print it
  guideline_no           44
  title                  'Technical Guidelines for Legionella Control in Water System'
  version                'V.6'
  issued_on              2025-08-19
  supersedes_id          → standards.id (nullable)
  source_url             the published PDF
  language               'en' | 'ar' | 'both'
  UNIQUE (authority, code, version)
```

Editions form a chain via `supersedes_id` rather than the current flat
`current_issue` / `superseded_issue` pair, so a certificate can be judged
against the edition in force *at its sampling date* — which
`core/standards.py::citation_is_stale` already reasons about correctly and
should keep doing.

### 3.2 `specification_sets` and `spec_limits` — what "compliant" means

```
specification_sets
  id, organization_id    NULL = built-in, seeded; non-NULL = org override
  standard_id            → standards.id (nullable: client-specific sets exist)
  key                    'lagoon_dm_water', 'facilities_potable_tank', …
  label, applies_to_scope

spec_limits
  id, spec_set_id        → specification_sets.id
  parameter_key          'ph', 'legionella_pneumophila', 'co2_ppm', 'wbgt'
  parameter_label, unit
  min_val, max_val       NULL = unbounded (same semantics as ComplianceLimit)
  display                verbatim human-readable limit
  qualifier_rule         how to judge '<1' / 'ND' / 'Absent' against this limit
  UNIQUE (spec_set_id, parameter_key)
```

`qualifier_rule` is new and necessary: `lab_results` deliberately preserves
non-numeric verbatim values (`'<1'`, `'Not Detected'`, `'Absent/100mL'`) and
migration 016 is emphatic that these must never be coerced to 0. A limit
therefore needs to state how a qualified value is judged, rather than leaving
each call site to improvise.

### 3.3 `obligations` — the cadence, and what is overdue

This is the single biggest product addition. Today the app knows what a
certificate *said*; it does not know that a certificate was **due and never
arrived**. For an FM buyer that inversion is the whole value: the risk is the
missing test, not the failed one.

```
obligations
  id, organization_id, site_id
  asset_id               → assets.id (nullable: some obligations are site-level)
  standard_id            → standards.id
  spec_set_id            → specification_sets.id (nullable)
  obligation_type        'sampling' | 'examination' | 'inspection' | 'competency'
  cadence_months         or cadence_days
  grace_days
  next_due_on
  last_satisfied_at
  last_satisfied_by      → lab_samples.id | certificates.id | inspections.id
  status                 'compliant' | 'due_soon' | 'overdue' | 'suspended'
  responsible_user_id
```

An obligation is satisfied by a piece of evidence and otherwise ages into
`due_soon` → `overdue`, which raises an alert and can open a corrective action
through the existing `core/corrective.py` machine. This is what turns the
product from a record store into a monitoring system.

### 3.4 `certificates` — third-party examination with an expiry

Tier 2's primitive. Distinct from `lab_samples` because nothing is *measured*:
a competent person examines a crane and issues a certificate with a validity
period.

```
certificates
  id, organization_id, site_id
  asset_id               → assets.id      (equipment: crane, boiler, MEWP)
  subject_user_id        → user_profiles  (competency: lifeguard, OHS officer)
  standard_id            → standards.id
  certificate_no, issuer, issuer_accreditation
  issued_on, valid_until
  outcome                'pass' | 'pass_with_conditions' | 'fail'
  conditions             TEXT
  source_filename, source_sha256, raw_extraction   (same forensic pattern as 016)
  reviewer_status
```

Exactly one of `asset_id` / `subject_user_id` must be set (CHECK constraint) —
plant certificates and people certificates share the expiry primitive but are
never the same row.

### 3.5 Checklists (Tier 3)

`checklist_templates` (versioned against a `standard_id`) → `checklist_items` →
`inspections` → `inspection_findings`. Findings feed the existing corrective
action table. Deferred to Phase 4; specified here only so the earlier phases do
not foreclose it.

---

## 4. Migration path off `core/constants.py`

Non-breaking, in this order. The constraint is that the lagoon product must keep
working unchanged throughout — it is the only deployment with real data.

**Step 1 — introduce, don't switch.** Migration 022 creates `standards`,
`specification_sets`, `spec_limits`. Seed a built-in set `lagoon_dm_water`
whose rows are generated *from* `COMPLIANCE_LIMITS`. Seed `standards` from
`core/standards.py::KNOWN_EDITIONS` (currently one row, GU44 V.6).

**Step 2 — read through a resolver.** Add `core/specs.py` exposing
`resolve_limits(asset) -> SpecSet | None` and `judge(result, limits) -> verdict`.
Reimplement `core/calculations.py` on top of it. `COMPLIANCE_LIMITS` stays in
`core/constants.py` as the seed source and as the offline/test fixture, but
nothing outside the seeder reads it directly.

**Step 3 — prove with a second scope.** Add the facilities Legionella set
(GU44) — the gap identified in §2.1 — and judge existing `lab_samples` against
it. This is the first real test that the resolver generalises, and it uses data
already in the database.

**Step 4 — widen.** Further guidelines become seed data plus a limit table, not
code. A new guideline should require **no Python change**. That is the
acceptance criterion for the phase.

Guardrails to preserve, all of which already exist and must not regress:

- A `sampled` asset with no scope resolves to `None`, never a default.
  `resolve_limits` must return `None` and the result stays `NOT_ASSESSED`.
  Defaulting produces a confident wrong verdict — see the `assets.scope`
  column comment in migration 019.
- `raw_extraction` and `value_raw` stay immutable and verbatim.
- Org overrides may narrow limits, never silently replace a built-in set
  without recording that they did.

---

## 5. Build order

Sequenced so that each phase ships something sellable and the risky
generalisation happens before there is much to generalise.

### Phase 0 — Rename and reposition (small, do first)
Product name, landing page, repo/domain. Decide the name before Phase 1 writes
it into seed data and table comments. See §7.5 on not baking "DM" in too hard.

### Phase 1 — Obligation registry + spec registry (the enabling work)
Migrations 022–024 per §3.1–3.3, `core/specs.py`, the §4 migration path, and an
Obligations page showing what is due, due soon, and overdue per site. Ships as a
real feature to the existing lagoon customer on day one: they currently have no
overdue view.

### Phase 2 — Tier 1 guidelines (measured parameter vs limit)
Nearly drop-in: reuses sampled assets, lab ingestion, the alert engine, PDF
reporting. Only new content is the limit tables.

| Guideline | Subject |
|---|---|
| GU44 | Legionella control in water systems *(partly built)* |
| GU81 / GU80 | Public / private swimming pool safety |
| GU34 | Approval of swimming pool plans |
| GU120 | Water features in public areas |
| GU145 | Water coolers and dispensers in public areas |
| GU17 | Quality of un-bottled drinking water *(Arabic only)* |
| GU133 | Water systems safety in emergency situations |
| GU141 / GU119 | Environmental indoor air quality (EIAQI) |
| GU142 | Mould remediation and control |
| GU38 | Management of heat stress at work (WBGT) |
| GU10 | Ventilation in school classes |
| GU78 | Health protection against ionizing radiation |

Recommended first three: **GU81 pools, GU141 EIAQI, GU38 heat stress** — high
site prevalence, unambiguous numeric limits, English source documents.

### Phase 3 — Tier 2 expiring certificates
New primitive (§3.4) plus obligations of type `examination`. Highest commercial
value per unit of build: an expired lifting-equipment certificate is a stop-work
finding, and almost nobody tracks these outside a spreadsheet.

| Guideline | Subject |
|---|---|
| GU48 | Cranes, hoists, lifts and other lifting appliances |
| GU47 | Boilers and pressure vessels |
| GU67 | Mobile elevated work platforms (MEWP) |
| GU74 | Mobile access towers |
| GU73 | Safe use of ladders |
| GU146 | Safe forklift operations |
| GU41 | Guarding of dangerous machinery |
| GU53 / GU138 / GU62 | LPG cylinders / helium cylinders / acetylene generators |
| GU148 | Safe storage |

### Phase 4 — Tier 3 checklist inspections
Checklist engine (§3.5) + findings → corrective actions.

| Guideline | Subject |
|---|---|
| GU137 / GU135 | H&S risk assessment / built-environment establishments |
| GU83 / GU84 | Establishments dealing with consumer products / entertainment |
| GU85 / GU93 / GU124 | Labour accommodation compliance and transport |
| GU90 / GU129 | Hotels and resorts / holiday homes |
| GU125 | Malls and shopping centres *(Arabic only)* |
| GU15 | Educational institutes |
| GU13 / GU19 / GU75 / GU77 / GU95 | Fitness, spa, salons, barbershops, home salons |
| GU76 / GU118 / GU136 | Laundry / shisha / henna |
| GU46 | Occupational H&S in kitchens and food areas |
| GU121 / GU02 | Play areas and events — permits and safety |
| GU130 | Desert tourist camps *(Arabic only)* |

### Phase 5 — Tier 4 people, competency and permits
Reuses the Phase 3 expiry primitive against `subject_user_id`, adds
permit-to-work.

| Guideline | Subject |
|---|---|
| — | Certification scheme: OHS Practitioner |
| — | Certification scheme: OHS Person in Charge |
| — | Lifeguard scheme requirements |
| — | Technical requirements for NOC to practise H&S activities |
| GU131 | H&S officer in labour accommodations |
| GU39 | Confined space entry (permit + trained persons) |
| GU35 | Rope access systems |
| GU72 | Emergency eyewash and shower provision |
| GU99 | Safety signs at work |
| GU66 | Night and shift work |
| GU50 / GU43 / GU42 | Asbestos / industrial organic solvents / paint spray booths |
| GU59–GU61, GU65, GU97, GU98 | PPE: eye/face, clothing, hearing, head, foot, hand |

PPE (six guidelines) is an issuance-and-inspection register; it is low value
standalone and should ride on `core/inventory.py` rather than get its own module.

---

## 6. Explicitly out of scope

The consumer and product-safety cluster:

> GU132 food contact materials · GU116 cosmetics and personal care · GU117
> fragrance products · GU115 handmade consumer products · GU107 consumer
> products storage · GU100 import and re-export · GU86 / GU82 biocides ·
> GU30 detergents · GU29 health supplements · GU18 e-commerce · GU122
> tobacco and smoking supplies permits · GU70 smoking area permits

These are product registration and market-surveillance workflows for importers,
manufacturers and retailers. Different buyer, different workflow, and crucially
**no asset** — the loop in §1 does not apply, because there is nothing on a site
being periodically re-verified. Pursuing them would double the product surface
and blur the positioning. Recommend declining explicitly rather than leaving
them ambiguous.

(GU70 and GU122 are permit issuance rather than product safety, and could be
revisited in Phase 5 alongside permit-to-work if a customer asks.)

---

## 7. Risks and standing costs

**7.1 Editorial burden is the real cost.** `core/standards.py` currently holds
exactly one edition, and its docstring states the operating rule correctly: only
add an entry when you have the document in front of you, because a wrong
"your citation is out of date" warning sends the client to argue with their
laboratory over nothing. Extending that discipline to ~80 guidelines is an
ongoing content operation, not a one-off import. It is simultaneously the
deepest moat (nobody else will do it) and a permanent cost line. **Budget a
named owner for guideline currency before Phase 2, not after.**

**7.2 Arabic-only sources.** GU17, GU124, GU125, GU129, GU130 are published in
Arabic only. Limit encoding and extraction for these need Arabic handling and,
realistically, a native-Arabic reviewer. Sequence them last within their phase.

**7.3 The science layer demotes.** `science/` (bloom forecasting, nutrient
attribution, digital twin) does not generalise beyond lagoons. Under the new
positioning it stops being the headline and becomes a premium module for one
scope. That is a marketing loss and should be taken deliberately — it is also
still the most defensible technical work in the repo, so it should not be
deleted or hidden, just re-shelved.

**7.4 Scope-resolution safety must survive generalisation.** The single most
dangerous failure mode in the generalised product is applying one scope's limits
to another scope's asset and returning a confident wrong verdict. With two
scopes this is a small risk; with eighty specification sets it is the central
one. `resolve_limits` returning `None` must stay a first-class, visible outcome
in the UI ("cannot be judged — asset unclassified"), never a silent pass.

**7.5 Don't bake in "DM".** Abu Dhabi (OSHAD / ADPHC) and Sharjah run parallel
regimes over identical asset types. `standards.authority` is in the model from
day one for this reason. Recommend shipping DM-first but naming the product so
it does not need renaming at the emirate border — "DM Compliance Monitoring App"
as a working title is fine internally, but weigh it against a name that
survives expansion.

**7.6 Pre-existing items unchanged by this proposal.** CORS is still
`allow_origins=["*"]`; invite email is not wired to a transactional provider;
billing has no live paying customer. All three predate this scoping and all
three should be closed before a paid pilot regardless of direction.

---

## 8. Open decisions

These need answers before Phase 1 starts; each changes the work materially.

1. **Product name and domain** — Phase 0 blocks Phase 1's seed data and table
   comments. See §7.5.
2. **Does the existing Safari Park engagement become customer zero for the
   obligations feature**, or does it stay on the lagoon product while the new
   scope is built alongside? Affects whether Phase 1 ships to production
   immediately or behind a flag.
3. **Which three Tier 1 guidelines go first** — §5 recommends GU81, GU141,
   GU38; a known customer requirement should override that.
4. **Who owns guideline currency** (§7.1). If the answer is "nobody yet", the
   staleness-warning feature should stay limited to the guidelines with a named
   owner rather than degrade into unreliable warnings.
5. **Single-emirate or multi-emirate ambition** — decided now, cheaply, in the
   data model; decided later, expensively, in a migration.
