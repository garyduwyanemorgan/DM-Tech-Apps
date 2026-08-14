# Checklist group — extraction notes

Guidelines extracted: **GU137** (H&S risk assessment, Phase 4 lead), **GU83**, **GU84**,
**GU85**, **GU93** (establishment checklists, Phase 6). **GU135 was skipped: it is
Arabic-only** — the portal listing says so explicitly and the catalogue records
`"language": "ar"` with the note `page/listing states "Arabic only"`. No English text
exists to extract verbatim, and §7.12's rule against guessing applies with more force to
a translation than to a number. GU135 is the other half of Phase 4, so Phase 4 cannot
close without Arabic-language capability.

Files written:

| File | Kind | Templates | Items | Severities in doc? |
|---|---|---|---|---|
| `gu137_checklist.json` | process | 5 (+1 register) | 33 | none |
| `gu83_checklist.json` | compliance | 14 annexes | 368 | yes, 4-level |
| `gu84_checklist.json` | compliance | 8 annexes | 302 (259 scorable + 43 headings) | yes, 4-level, **different vocabulary** |
| `gu85_checklist.json` | compliance | 14 sections | 136 (19 measured) | none |
| `gu93_checklist.json` | process | 9 sections (+3 flowcharts) | 72 | none |

Every version and issue date above came from **inside** the PDF (cover block and the
per-page footer), never from the filename or the portal listing date. Two cases where
that mattered: GU84's cover page carries **no version block at all**, so its V 1.1 comes
solely from the footer; and GU83's URL says `V4.1` and the cover agrees — the agreement
is coincidence and was not relied on (see the version conflict below).

---

## 1. Does §4.6's four-table model fit? Mostly no, and it fails differently for each document

§4.6 sketches `checklist_templates` (versioned against a `standard_id`) → `checklist_items`
→ `inspections` → `inspection_findings`, findings feeding the corrective-action table.
The `inspections` → `inspection_findings` half is fine. The
`checklist_templates` → `checklist_items` half does not survive contact with these five
documents. Concretely:

**1.1 GU137 has no checklist at all.** This is the largest single finding, and it lands on
the Phase 4 lead guideline. GU137 is eleven pages of method plus one blank table. Appendix A
is a **register**, not a checklist — and it is the exact inverse shape: a checklist has a
fixed item set and a variable response, whereas Appendix A has a **fixed column set and a
variable, unbounded, site-specific row set** (one row per identified hazard). You cannot
express "Hazards | Affected Person(s) | Current Controls | Risk Probability | Risk Severity |
Risk Level | Further Control Measures | Responsible Person | Planned Completion Date |
Completion Date" as `checklist_items` without pretending the ten columns are ten items,
which they are not — they are ten fields of one repeating row. Phase 4 therefore needs a
**second primitive alongside the checklist engine**: a `risk_assessments` header +
`risk_assessment_entries` rows table, keyed to an asset or activity, with its own review
date. The scoping document currently assumes the checklist engine is sufficient for Phase 4.
It is not. This is a build-order correction, not a schema detail: GU137 was scheduled as the
proving ground for the checklist engine and it is the one document in the group that does not
exercise it.

Note also that GU137's Appendix A header carries **`Date of next review`** — an assessor-set
date. That is a fourth kind of cadence the `obligations` model does not have: not periodic,
not event-triggered, not silent, but **self-declared by the duty-holder**. Any overdue flag
must read "past the date you set", never "past the DM interval", because DM sets none.

**1.2 GU84's tables are two-level; GU83's are flat.** 43 of GU84's 302 annex rows print a
requirement with the **Risk column empty**, and the rows beneath elaborate them with their
own risk classes. `checklist_items` as sketched is a flat list, so those 43 headers either
get dropped (losing the grouping an inspector navigates by) or get scored as failures they
were never meant to be — and since they carry no risk class, scoring them would feed a
grading formula with unclassifiable violations. `checklist_items` needs a self-referential
`parent_item_id` and an `is_scorable` flag. GU83, built from the same DM template, is flat
throughout — so the schema must support both within one guideline family.

**1.3 Severity cannot be a global enum.** GU83 and GU84 are the same framework with
**incompatible vocabularies on every axis**:

| | GU83 | GU84 |
|---|---|---|
| Risk outcome (what the item carries) | Minor / Major / Critical / **Catastrophic** | Low / Medium / High / **Catastrophic** |
| Severity input axis | Very Low / Low / Medium / High / Very High | Negligible / **Minor** / Moderate / **Major** / Extreme |
| Probability axis | Very Unlikely … Almost certain | **Rare/Remote** … Almost certain |
| Grades | A, B, C, D, **F** (no E) | A, B, C, D, **E** (no F) |

The words overlap and mean different things. **"Minor" is a risk outcome in GU83 and a
severity input in GU84. "Medium" is a severity input in GU83 and a risk outcome in GU84.**
A shared `failure_severity` enum will silently mis-map GU84 findings into GU83 semantics.
Severity must be **namespaced per standard** — a `severity_scale` owned by the
`standards` row, with the item carrying a scale-local value. Each extraction here stores
`source_risk_label` verbatim alongside the mapped value so nothing is lost if the enum
is later reworked.

The extraction schema's own enum (`critical|major|minor|unknown`) also has **no slot for
Catastrophic**, and collapsing it into `critical` is a substantive error, not a cosmetic
one: under GU83's formula **one Catastrophic is grade F on its own, whereas it takes five
Criticals** to reach F. The enum must be extended before anything is loaded.

**1.4 "Versioned against a standard" understates it — templates need an applicability
predicate.** See §2 below; this is the biggest content gap in the group.

**1.5 GU85 says out loud that the scored checklist is not in the document.** §4.6 assumes
DM publishes the checklist and we encode it. GU85 §3 defines "Level of compliance" as
determined by *"the extent to which the accommodation meets the items listed in the
inspection checklist, which is linked to the risk matrix and electronically registered in
the system designated for the inspection and monitoring of labor accommodations."* The
requirements are published; **the checklist and the risk matrix are DM's internal system.**
So `checklist_templates` for GU85 holds *our* rendering of DM's requirements, not DM's
inspection form. That distinction has to be visible in the schema — a
`template_provenance` field distinguishing *published DM form* from *derived from published
requirements* — or a client will reasonably believe they are filling in the regulator's
actual checklist.

**1.6 What does fit.** `inspections` → `inspection_findings` → corrective actions works
well, and GU83/GU84's `required_action` tables give it real teeth: each risk class carries a
document-stated action (Minor/Low = continue; Major/Medium = recommended corrections;
Critical/High = mandatory corrections within a proposed period, stop on non-compliance;
Catastrophic = stop until corrected, re-assess before relaunch). That is a genuine,
citable corrective-action priority — the only place in this group where §7.12's warning
about unauthorised priorities is satisfied by the source rather than worked around.

---

## 2. Are the checklists versioned against a standard edition, or generic forms?

**Genuinely versioned — decisively so.** Every document in the group carries a version, an
issue date, a superseded issue date, and (except GU84 and GU93) a document history log
recording what changed and when. GU85's log is the clearest: version 4 (3 Jan 2025) added
requirements for the building, sleeping rooms, kitchens, laundry, elevators, swimming pools,
water quality and indoor air; version 5 (30 Sep 2025) revised definitions, control and
inspection systems, individual kitchens, water quality and indoor air. **The requirement set
changes between editions.** Binding a template to a `standard_id` is correct and necessary —
an inspection recorded against GU85 v4 attests to a different item set than one recorded
against v5, and re-pointing a stored inspection at a new edition would silently change what
was attested.

Three cautions:

- **GU83 contradicts itself about its own version.** Cover and all 35 footers say **V 4.1,
  issued 9 June 2025, superseding 28 April 2024**. The document history log on page 2 tops
  out at **version 3, dated 9 June 2025** — there is no row for 4.0 or 4.1. The footer value
  was taken because it is stamped on every page, but this must be re-verified with DM before
  the module is sold. §7.1's "a wrong limit in a sold module is a liability" applies equally
  to a wrong edition label.
- **The templates are not generic, but they are shared.** GU83 and GU84 draw from a common
  DM master annex library — the toys, low-voltage, detergent and biocide annexes are
  near-identical between them, differing in risk class and in a few labelling items. GU84's
  Part E contains Annexes **1, 2, 3, 4, 5, 8, 10, 11** with 6, 7 and 9 absent: those are the
  annexes an entertainment establishment does not need, omitted from a shared numbering.
  This has a direct commercial consequence — **the same annex is content for two SKUs**, so
  editorial effort amortises across modules better than §7.1 assumes, but a correction to a
  shared annex must propagate to every module that embeds it.
- **The one place the "versioned" claim breaks is `applies_to`.** GU83's Part E is titled
  "Business activity **Annexes**" and §8 notes *"Each requirement violation assessed to its
  risk based on business activity type"* — yet **no activity-to-annex mapping is printed
  anywhere in the document.** A perfume shop is plainly not assessed against the
  swimming-pool or toys annexes, but nothing in GU83 says so. Every `applies_to` in
  `gu83_checklist.json` is derived from the annex's own heading, not from a stated scope
  rule, and is flagged as such. **This is the largest content gap in the group and it must
  be resolved with DM before the GU83 module ships** — serving the wrong annex set changes
  the violation counts, which changes the grade. It is §7.4's scope-resolution risk arriving
  through the checklist door.

---

## 3. Is GU137 a compliance module or a process module?

**Process. Unambiguously, and it is not a close call.**

GU137 states no limit, no acceptance criterion, no checkpoint, and no definition of an
adequate assessment. It says a 3×3 matrix is *"an example"* — explicitly non-normative — and
never mandates any matrix, scale or scoring. It says action *"will vary between supervision
(in lower risk activities) to complete halt of work (in case of unacceptable risk)"* but
**never defines which cell is unacceptable**, so even the halt-of-work trigger is
unencodable. There is no threshold at which an establishment fails.

A GU137 report may legitimately say: *an assessment was carried out on date X by person Y,
recorded these hazards, and is due for review on date Z (the date the assessor set).* It may
**not** say COMPLIANT. The resolver must refuse a verdict for this module, exactly as §7.12
requires.

Two consequences worth flagging:

- **The example matrix is not a product.** Its cells are asymmetric — High probability ×
  Low impact = **Low**, while Medium probability × High impact = **Medium**, and the entire
  Low-probability row is Low regardless of impact. Any engine computing
  `risk_level = probability × severity` will disagree with the published matrix on several
  cells. Since the matrix is only an example anyway, **`risk_level` must be stored as the
  assessor entered it and never recomputed.** This is the checklist-side analogue of §7.12's
  band-gap trap: a plausible-looking derived value that the source does not authorise.
- **Only one genuinely attestable template exists in GU137** — §4-5's four recording duties,
  and it is **conditional on the employer having 5 or more employees**. Below that headcount
  the document imposes no recording duty at all, so the template must not be served and its
  absence must not be scored as a failure. That conditional is encoded as an
  `applicability_condition` on the template.

**GU93 is also process**, for the same reasons — no severities, no grading, no cadence — plus
one more, covered in §5.

---

## 4. Do any items require a MEASUREMENT? Yes — the group is thoroughly hybrid

This is not an edge case. Measurement items appear in **four of the five** documents, in two
distinct flavours.

**Flavour A — the checklist item points at a limit that lives in another guideline.** The
item is a checkbox whose answer can only be produced by an instrument or a laboratory:

- GU83 A3.11 / GU84 A2.1 — *"Measurements of Indoor air pollutants concentrations within
  acceptable limits inside premise."* The limits are **GU119's**, already extracted as
  `gu119_limits.json`.
- GU83 A4.6 / GU84 A3.11 — *"Compliance of samples tested for chemical and microbiological
  contamination."* Laboratory analysis, and per §4.7 it must come from a **DM-accredited
  independent laboratory** — so this single checkbox pulls in the `laboratories` table, the
  accreditation-on-sampling-date check, and a lab report parser.
- GU83 A3.22/A3.23, GU84 A2.11/A2.12 — *"Humidity comfort level"*, *"Heat comfort recommended
  level"*. Measurements with **no range stated in either document**.

**Flavour B — the limit is printed inside the checklist item itself.** These are `spec_limits`
in checklist clothing:

- **GU84 A4.8 and A4.9 carry hard dB limits**: *"Control noise level below **55 dB** from 7AM
  to 8 PM"* and *"below **45 dB** from 8PM to 7 AM"*. **GU83's corresponding noise annex omits
  the numbers entirely** — its items say only "below acceptable daytime limit". So the older,
  narrower guideline supplies a limit that the newer, broader one drops. A client holding
  only the GU83 module cannot evaluate its own noise items.
- **GU85 is a genuine hybrid throughout — 19 of its 136 items carry a numeric threshold**:
  3 m² per person; bed ≥ 30 cm above floor; bunk clearances 100 cm and 70 cm; wardrobe 2 m;
  one toilet, shower and basin per 8 persons; one urinal per 25; dining hall sized for one
  third of the workforce; hot holding > 65 °C and cold storage 1–4 °C; chimney ≥ 2 m above the
  nearest building; ≥ 3 cooling units; ceramic tiling ≥ 2 m; storage clearances 20/50/30 cm;
  cleaning ≥ twice daily; deep clean ≤ every 3 months.
- GU93 carries the 2-metre distancing rule in seven separate items.

**Design consequence.** The two models must not be built as alternatives. A `checklist_item`
needs an optional **`spec_limit_id`**, so the item states *what is checked* and the limit
states *what passes* — the limit living in the §4.2 `spec_limits` table where it can be
versioned, unit-checked and cited, whether it came from the same guideline (GU85, GU84 noise)
or a different one (GU119, GU44). Building the checklist engine with free-text items and
adding measurement later means re-encoding all five of these documents.

**Two thresholds could not be resolved and were deliberately left null**, per §7.12's
"omit an ambiguous cell, never guess it":

- GU85 6.3 — *"Each room must accommodate no more than **8 to 10** workers"*
- GU93 6.3 — *"Workers distribution in maximum **3 to 5** workers per group"*

A maximum cannot be two numbers. Snapping either to its upper bound would authorise an
occupancy DM may not permit; snapping to the lower would forbid one it does. Both are stored
with `value: null` and an `ambiguity` note.

---

## 5. Other findings that change decisions

**5.1 GU83's annex cross-references are systematically wrong — and GU84 proves why.**
GU83 §10 cites the wrong annex number for **everything after Annex 1**, consistently off by
one: toys → "Annex 5" (actually 6), food contact → "Annex 6" (actually 7), cosmetics → 7
(actually 8), low voltage → 8 (actually 9), health supplements → 9 (actually 10), detergents →
10 (actually 11), biocides → 11 (actually 12), tobacco → 12 (actually 13); indoor air →
"Annex 2" (actually 3); and §10-2 cites "Annex 1, Annex 13" for public and operational safety
when the actual safety annex is Annex 2.

Reading GU84 explains it. **GU84's §10 cites exactly the same annex numbers, and in GU84 they
are correct** — toys really are Annex 5, low voltage really is Annex 8, detergents Annex 10,
biocides Annex 11, indoor air Annex 2, noise Annex 4. GU83's body text was copied from GU84
and its annex pointers were never renumbered when GU83's Part E was rebuilt. This is a
copy-paste defect in the source, confirmed across two documents, not a misreading on our
side. **Templates are bound to the annex as printed in Part E** (whose own headings are
unambiguous); §10's pointers are ignored, and no applicability routing should ever be built
from them.

**5.2 The grading formulas must not be implemented.** Both GU83 and GU84 print their bands
joined by **`&/or`**, which is not a decidable operator — whether the conditions are
conjunctive or disjunctive changes the grade for most real inspections. GU83 is worse still:
**grades A and B overlap and are not separable as printed** (0 Critical, 0 Major, 2 Minor
satisfies both), neither band mentions Catastrophic, **and a zero-violation establishment
matches no band at all**. GU84's table is cleaner (grade A = zero of everything, no overlap)
but shares the `&/or` defect.

Recommendation: **emit violation counts by class, and at most a provisional grade explicitly
marked as derived.** A wrong grade letter on a report is precisely the misrepresentation
§7.12 warns about, and the grade is the number a client will put in front of DM. Note too
that **grade A does not mean the same thing in the two documents** — GU83 grade A tolerates
1–2 Minor violations, GU84 grade A requires zero of everything — so a cross-guideline
"compliance score" would be meaningless.

**5.3 GU93 should not be sold as a live module.** GU93 is a COVID-19 emergency measure —
version 1 issued 5 April 2020, version 2 on 1 January 2021, no revision since. It never names
the disease but is unmistakable: facemasks, 2 m distancing, isolation rooms, symptom screening
at every entry and exit, DHA quarantine referral, no gatherings above three, one person per
dining table, no fingerprint attendance, remote work for eligible staff, and unnamed
"re-opening circulars" that cannot be resolved to anything.

It now **directly contradicts a current guideline**: GU93 3.5.2 requires *one person per dining
table* with 2 m between tables, while GU85 8.4 requires the dining hall to *seat one third of
the total workforce at a time*. Both are published today. Serving GU93 items to an FM
contractor would generate corrective actions for conditions no regulator is enforcing —
a contractual and reputational liability, not merely a stale module. Recommended catalogue
status: **published but presumed dormant — verify with DM before sale.** It is a real example
of a §7.12 case the taxonomy does not yet cover: not unusable (it is internally coherent
enough), but *superseded by circumstance*. Consider a sixth `module_kind`, or a
`lifecycle_status` column on `standards` orthogonal to `module_kind`.

**5.4 Text extraction alone loses a quarter of GU93.** Pages 5, 7 and 9 come back **blank**
from `pdfplumber` — they are images. Read visually they are three worker-journey flowcharts,
and page 7 holds **the only decision point in the document** (*"Are there symptoms?"* → No:
allow exit / Yes: contact DHA, isolate, disinfect). GU137's risk matrix, hierarchy-of-controls
reference and five-step diagram are likewise image-only. **Any extraction pipeline for this
family that trusts a blank text layer will silently drop content**, and blank pages are much
easier to miss than a garbled table. Render-and-read must be the default for these documents,
not the fallback. Related: GU137 §4-4's text refers to a hierarchy-of-controls diagram
(*"In the following diagram hazard control methods at the top of the graphic are potentially
more effective…"*) but **the graphic is not on the page** — the levels were deliberately not
extracted rather than filled in from the familiar Elimination/Substitution/Engineering/
Administrative/PPE ladder, which would have been inventing content DM did not print.

**5.5 Document defects were preserved, not corrected.** Verbatim means verbatim, including
where the source is broken. The material ones:

- **GU85 7-1 bullet 7 is truncated mid-sentence**: *"A dishwashing sink with both hot and
  cold"* — no verb, no object. Not completed to "…water": an inspector cannot attest to a
  requirement that was never fully stated.
- **GU84 A1.114 is not a checkpoint at all** — its Requirement cell reads
  *":TG14, TG15, TG16, TG17, TG18, 19, TG20, AND TG21"* (a bare reference list, with "TG"
  missing from "19") **yet carries a risk class of High**, so a naive loader would score it.
- **GU84 prints "Availability of suitable cleaning materials." twice, once Medium and once
  High** — the document contradicts itself on how badly the same failure counts. Set to
  `unknown`; preferring either value would change a grade on a guess.
- **GU93 sections 4 and 7 are near-total duplicates** (eight items each, seven verbatim
  identical), and section 4's first item describes getting *off* a bus under a heading about
  *leaving* the accommodation. Scoring both double-counts the same controls.
- Duplicate rows also appear in GU83 Annex 5 and Annex 7, and GU84 Annex 2 prints
  *"Presence of suitable ventilation mechanism in pump rooms"* both as an unscored group
  header and as a scored Medium item. **All duplicates are flagged with `duplicate_of`:
  de-duplicate before scoring, or one real-world failure counts twice and can push a grade
  down a band.**
- GU84 Annex 3 is titled *"Non drinking water system requirements"* but three of its items are
  explicitly about **drinking** water tanks.
- Typographical errors in GU83 (`inscects`, `Prsence`, `AvaiIability`, `driniking`,
  `belowacceptable`, `nad`, `disseased`) and GU93 (`cleaning and cleaning`, `muzzles`) are
  reproduced exactly.

**5.6 GU85 is a bundle, not a module.** It delegates air conditioning to GU119, water quality
to GU133/GU44/GU17, swimming pools to GU81, the H&S officer to GU131, kitchens to GU46, food
to the Dubai Food Code and the building envelope to the Dubai Building Code. **Sections 14 and
15 contain no requirements of their own — they are pure pointers.** A labour-accommodation
client buying GU85 alone gets a shell that cannot be evaluated. Under §4.5 modular pricing
this is the clearest case in the group for **dependency-aware entitlements**: either sell
GU85 as a bundle, or have the resolver report "not assessable — requires GU119" rather than
silently passing an item it cannot evaluate. That is §7.5's entitlement-as-compliance-hole
risk showing up concretely, and GU85 hands us the test case.

**5.7 GU84 is the stalest document and most at risk of silent re-issue.** Issued December
2020, it is the only one still carrying pre-2023 branding — GU83's own change log records the
Dubai Government / Dubai Municipality logo swap that GU84 has never had — and its contact
addresses still point at `esuggest.dubai.gov.ae` and `ecomplain.dubai.gov.ae`, both replaced
by the 04 Platform in GU83 and GU85. Re-verify before sale.

---

## 6. Recommended schema changes before Phase 4 starts

1. `checklist_items.parent_item_id` + `is_scorable` — GU84's 43 unscored group headers.
2. `checklist_items.spec_limit_id` → §4.2 `spec_limits` — the ~30 measurement items across
   GU83/84/85, whether the limit is in-document (GU85, GU84 noise) or external (GU119, GU44).
3. **Severity namespaced per standard**, not a global enum — `standards.severity_scale` with
   scale-local item values; and extend the enum to carry **Catastrophic** regardless.
4. `checklist_templates.applicability_condition` — GU137's ≥5-employee gate, GU85's
   if-a-pool-exists items, and (once DM clarifies it) GU83's activity-to-annex mapping.
5. `checklist_templates.template_provenance` — *published DM form* vs *derived from published
   requirements* (GU85 §1.5).
6. A **`risk_assessments` / `risk_assessment_entries` pair** for GU137's register — the
   variable-row-count shape the checklist model cannot express. **This is a Phase 4
   prerequisite, and it is new work the scoping document does not currently budget for.**
7. `obligations` needs a **self-declared cadence** kind for GU137's "Date of next review".
8. `standards.lifecycle_status` orthogonal to `module_kind` — for GU93 and anything else
   published but overtaken by events.
