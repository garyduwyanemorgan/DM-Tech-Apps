# Phase 5 — People, competency and permits: extraction notes

Covers the twelve documents extracted into `*_competency.json`. Nine were done in this
pass (GU131, GU42, GU43, GU66, GU99, and the four unnumbered scheme documents); three
(GU35, GU39, GU50) were done earlier and are reviewed here but not rewritten.

Editions and issue dates were taken from `catalogue_editions.json` and, where a numeric
date was day/month ambiguous, from `catalogue_editions_resolved.json`. No version or date
in any of these files comes from a filename, a URL path, or a portal record date.

---

## 1. Arabic

**Nothing was skipped for Arabic.** All twelve documents are `"language": "en"` in
`catalogue.json` and all twelve were extracted in full.

One Arabic dependency was found *inside* an English document and could not be followed:
SP06 delegates mobile-activity requirements to *"Technical guideline (01) for service
vehicles and mobile commercial activities"*, which SP06 itself annotates
**"(Available in Arabic Only)"**. Mobile salon/laundry activities therefore cannot be
fully specified from the English corpus. That is the only Arabic block encountered.

---

## 2. `module_kind` per document, with reasoning

| Document | kind | Why |
|---|---|---|
| **GU131** H&S officer in labour accommodations | `compliance` | Clause 2.8 fixes required HSO headcount against room count (2 above 100 rooms, 1 for 51–100, none at ≤50) and clause 2.2 gives a 3-year certificate validity. Countable, checkable, no interpretation. First Phase 5 doc supporting a verdict. |
| **GU42** Paint spray booths | `compliance` | Face velocity, water circulation rate, stack height and velocity, separation distances, overspray control by application rate — all DM's own numbers, all measurable with an anemometer and a tape measure. |
| **GU43** Industrial organic solvents | `delegating` | **Sets no exposure limit of any kind.** §5-1 points at ACGIH TLVs; storage goes to the DM Dangerous Goods Code of Practice; transport, glove selection, extinguishing media, spill procedure and first aid all go elsewhere. See §4 below. |
| **GU66** Night and shift work | `monitoring` | Full of numbers (12h/8h shifts, 54/108/215 lux, 7–8h sleep, 2 rest nights, 30 min exercise) but **every one sits under a heading that says "Recommended"**, and §4-2 opens "may be exercised as applicable". Supports a risk band and control obligations, not a verdict. Same shape as GU38. |
| **GU99** Safety signs at work | `compliance` | Sign colour/shape per type is prescriptive `shall`; signal word ≥50% greater than hazard text capitals; annual training; 5-year records. Crucially **Annex C reproduces the ISO 7010 symbol library in full**, so the binding content is inside the document — that is what keeps it out of `delegating`. |
| **S1** Lifeguard Scheme (`DM-HSD-S1`) | `compliance` | Either the facility has, on shift, lifeguards holding unexpired certificates of the right specialty for the water depth, or it does not. Cleanest compliance case in the set. |
| **S2** OHS Person in Charge (`DM-HSD-S2`) | `compliance` | §6.1: at least one certified PIC **per work shift, per work location**. Quantified, countable, and it multiplies. |
| **S3** OHS Practitioner (`DM-HSD-S3`) | `compliance` | §5: *all* industries in Dubai shall employ Certified OHS Practitioners. Universal duty on a credential with a 2-year validity. |
| **SP06** NOC to practise H&S activities | `compliance` | Numeric layout requirements checkable against a drawing. **But see §5 — it is not a competency document at all.** |
| GU35 Rope access *(earlier pass)* | `compliance` | Not re-reviewed. |
| GU39 Confined space entry *(earlier pass)* | `process` | Not re-reviewed. |
| GU50 Asbestos *(earlier pass)* | `process` | Not re-reviewed. |

---

## 3. The key question: does §4.4's `certificates` primitive fit people-competencies?

**No. Not as drafted.** It fits *plant* — a crane is examined, a certificate is issued, it
expires — and Phase 3 proved that. People-competencies share only the expiry field. Below
is the evidence, all of it from the documents rather than from first principles. §4.4 is
not wrong; it is a subset, and the missing parts are the parts that determine whether a
client is actually compliant.

### 3.1 `valid_until` is *derived*, not stored

S1 p5: *"Certifications are valid only for the remaining period of a candidate's training
record. For example, if a training record has three months of validity remaining, the
certification will only be issued for that duration."* And: *"If a valid training
record/credential expires, the certification is rendered invalid, and the individual may
not perform lifeguard duties until updated training records are provided."*

The expiry is `MIN(own ceiling, underlying credential's expiry)`. A plain date column
holds a value that goes silently wrong when a *different row* lapses. **A lifeguard can be
un-certified today by an event recorded against another record.**

### 3.2 Certificates depend on other certificates

Not decoration — hard prerequisites the scheme enforces:

- S1 lifeguard → accredited lifeguard qualification + DCAS-approved BLS/First Aid/CPR/AED
  + (where DHA requires) a valid Occupational Health Card.
- S1 instructor → all of the above **plus** a valid lifeguard certificate *from the same
  certifying agency* **plus** a BLS/first-aid *trainer* qualification.
- S3 practitioner → one of four degree+diploma+experience combinations, verified and
  screened by the CB before the exam.

§4.4 has no way to draw an edge between two certificate rows. Without it the app can show
a valid lifeguard certificate while the BLS underneath it has lapsed — which the document
says means the person "may not perform lifeguard duties".

### 3.3 Renewal is anchored to the *old expiry*, not to the exam

S1 p14: *"Regardless of the date of the renewal examination within that 2-month period,
the new two-year certification period begins from the date not later than the expiry date
of the candidate's initial certification."*

`issued_on + 24 months` — the obvious implementation — **over-grants up to two months of
validity**. That is a mis-issuance, not a cosmetic bug.

### 3.4 The renewal window is a business rule with money attached

S1: recertification only *within* the two months before expiry; two attempts; then
*"There is no grace period after their certification expires. Candidates whose
certification has lapsed must take a full course."*

One day late converts a renewal exam into a full re-course. GU131 and S2/S3 all likewise
require renewal *before* the end of the final year, so **the actionable date is always
earlier than `valid_until`** and differs per scheme. A single global "expiring soon"
threshold is wrong for all of them.

### 3.5 Status is not a function of dates

A certificate can die before its expiry:

- **S1** — six revocation grounds: expiry without renewal, falsification, substance-abuse
  breach, culpability in an accident, medical non-compliance, ethics breach (list is
  expressly non-exhaustive).
- **S2** — *"In circumstances wherein the OHS Person in Charge changes sector employment
  (e.g., from services to factories) … the issued certification will be invalid."*
  A payroll change invalidates a certificate.
- **GU131 / S2 / S3** — a poor company inspection grade triggers cancellation and
  reassessment of the *individual's* certificate.

`valid_until` alone cannot express any of this. An explicit status is required.

### 3.6 Scope attributes decide whether a valid certificate is the *right* certificate

- **S1** — specialty (shallow water / pool / beach) gated on a 1.5 m depth threshold; a
  Shallow Water lifeguard posted to 2 m water is working outside their certification while
  holding a perfectly valid certificate. Probably the single highest-value check available.
- **S2 / S3** — the certificate face must carry *"Type of sector (Construction, Factories,
  Service)"*, and in S2 sector change invalidates it.
- **S1** — pool dive prerequisite is *"3m, **or to the deepest depth of the facility in
  which they will be lifeguarding**"*, and water-park lifeguards need *"additional
  examinations at the specific facility where they will work"*.

That last one means **a person-certificate can be tied to a site**. §4.4 forbids it: the
CHECK constraint allows exactly one of `asset_id` / `subject_user_id`, and there is no
`site_id` role for a person-certificate's *scope* as distinct from where they work.

### 3.7 The compliance question is coverage, not holding

S2 §6.1: one certified PIC **per work shift, per work location** — and *"must always be
present throughout the conduct of the work activity"*. Three shifts across twelve sites is
36 coverage slots. **This is a roster question that certificate rows cannot answer.** A
client can hold every certificate and still be non-compliant on a night shift.

Compare the required-count rules, which differ per standard and live nowhere in §4.4:
GU131 a room-count table; S2 shifts × locations; S3 *"Certified OHS Practitioners"* plural
with **no ratio at all**; S1 *"appropriate for the size of the facility and number of
bathers"* with no formula.

### 3.8 Smaller mismatches, all real

- **Interim credentials** — S1: proof of passing is valid 3 months pending the card. Miss
  it and you show a false gap; ignore its expiry and you show a false pass.
- **Attached recurring obligations** — S1 4 documented hours of in-service training *per
  month*; S3 two years of CPD evidence that **replaces the renewal exam entirely**;
  GU131 trainer CPD reported by 31 December. These hang off the credential, not the person.
- **Issuer is a chain, not a string** — EIAC accreditation → Certification Body →
  certificate, with DCAS approving the BLS portion and DHA approving the clinic. §4.4 has
  flat `issuer` / `issuer_accreditation` text.
- **Attempt counters** — 3 attempts (S2/S3), 2 renewal attempts (S1), with different
  consequences on exhaustion.
- **`outcome` enum doesn't fit** — `pass | pass_with_conditions | fail` is a plant
  vocabulary. No people scheme here issues a conditional pass.
- **Field lists DM actually specifies** — S1 mandates photo, DOB, certification date,
  expiry, *examiner information*, *specialty*, training facility name and location; S2/S3
  mandate designation, *sector*, Emirates ID, serial/control number. Several have no home
  in §4.4.

### 3.9 Recommendation

Keep `certificates` for plant, unchanged — it works and Phase 3 proved it. Add a sibling
for people rather than overloading it. Minimum viable shape:

```
people_credentials
  id, organization_id, subject_user_id → user_profiles
  standard_id → standards.id
  credential_type            lifeguard_pool | ohs_practitioner | ohs_pic | hso | ...
  scope_key                  specialty / sector / depth band — the §3.6 attribute
  scope_site_id              NULL unless the credential is site-tied (S1 water parks)
  issuer_body_id             → certification_bodies (accreditation chain, §3.8)
  certificate_no, issued_on
  valid_until                COMPUTED, never hand-entered      (§3.1)
  renewal_opens_on           expiry − scheme window            (§3.4)
  status                     valid | expired | suspended | revoked | superseded  (§3.5)
  status_reason
  depends_on_credential_id   self-FK, the prerequisite edge    (§3.2)
  attempts_used
  interim_proof_expires_on                                     (§3.8)

coverage_requirements        the §3.7 problem, per standard
  standard_id, basis         per_site | per_shift_per_site | per_room_band | unquantified
  required_count / band table
```

Two rules the resolver must carry: **`valid_until = MIN(own ceiling, every prerequisite's
valid_until)`**, recomputed whenever any prerequisite changes; and **on renewal, the new
period runs from the previous `valid_until`, never from the exam date**.

**Is Phase 5 cheap?** The *expiry* half is cheap and reuses Phase 3 directly. The
derived-validity, prerequisite-graph, status and coverage halves are new work — closer to
Phase 3's cost than to a fortnight bolted onto it. Better to discover that here than after
issuing a report that says a lapsed lifeguard is current.

---

## 4. GU43 and the ACGIH problem — a commercial dependency, not an extraction gap

GU43 was expected to carry exposure limits. It carries **none**: no ppm, no mg/m³, no TWA,
STEL or ceiling for any solvent. §5-1 "Exposure Standards" points at *"Threshold Limit
Values … adopted by ACGIH"* and the reference list cites only the ACGIH publication.

Under §7.12 that makes it `delegating`, the GU10 → ASHRAE 62.1 shape. Consequence:

- A GU43 module **cannot emit a COMPLIANT / NON-COMPLIANT verdict from DM content alone.**
- To sell a verdict-bearing GU43, the product must license the ACGIH TLV list, which is
  copyrighted and sold by ACGIH. That is an external content dependency with a real cost
  and a licensing question — not something more reading closes.
- Until then GU43 is sellable only as an **obligations** module: annual medicals (the one
  firm `shall` with an interval), periodic sampling, MSDS availability, training.
- Its catalogue `evidence_type` of `laboratory` is half right — sampling genuinely happens
  — but there is nothing inside DM's corpus to judge the results against.

Other delegations found this pass, all of them content the product does not have:

| From | To | Blocks |
|---|---|---|
| GU43 | ACGIH TLVs | all solvent exposure verdicts |
| GU43, GU99 | DM Code of Practice for Management of Dangerous Goods | storage segregation, DG labelling |
| GU42 | LEL of the powder in use; unnamed DM Respiratory Protection guideline | powder-coating ventilation, RPE selection |
| GU99 | UAE Fire and Life Safety Code; Dubai Universal Design Code | **all fire/exit signage — expressly out of GU99 scope** |
| GU66 | unnamed "legislation" | emergency drill frequency |
| S1 | HSD public swimming pool guidelines | pool water quality, plant operator |
| SP06 | GU13, GU19, GU75, GU76, GU77, GU107 | everything post-opening |
| SP06 | TG-01 (Arabic only) | mobile activities |

---

## 5. Two documents are in the wrong phase

**SP06 is not a competency document.** "Health and safety activities" is a *commercial
licence category* — salons, oriental baths, spas, gyms, laundries — and the NOC is a
**premises permit granted against a furniture-layout drawing**. Across 12 pages there is
no role, qualification, training, certificate, examination, issuing body or validity for
any person. `competencies` is empty by evidence.

It is also the wrong *commercial shape*: five event triggers (new branch, layout change,
added activity, relocation, mobile activity), **no expiry, no renewal, no periodic
re-inspection**. Nothing for an obligations engine to schedule. It is a pre-opening
checklist and the front door to the Phase 6 bundle (GU13/19/75/76/77/107) it delegates to.
**Sequence it with Phase 6, not Phase 5.**

**GU42 has no people content either.** No competent person, no trained operator, no
examiner, no training, no certification, no validity — and, contrary to the catalogue's
guess of *"likely LEV thorough examination"*, **no thorough examination requirement at
all**. It belongs with the quantitative engineering modules. Its `evidence_type` of
`unknown` should become a measured engineering inspection, not a third-party certificate.

---

## 6. Validity vs interval — checked specifically, per the Phase 3 lesson

Phase 3 found all five certificate guidelines stated an interval and **no** validity.
Phase 5 is the opposite, and the distinction was tested document by document:

| Document | Validity | Interval(s) |
|---|---|---|
| **GU131** | **36 months** (HSO), explicit | recert before end of year 3; trainer report 31 Dec |
| **S1** | **24 months** ceiling, derived downward | 4 h/month in-service; quarterly CB/ATP reports; 30-day exam window; 3-month interim proof |
| **S2** | **24 months** | daily pre-operational inspection **(only daily obligation in Phase 5)**; 31 Dec trainer report |
| **S3** | **24 months** | CPD across the 2-year period (unquantified) |
| GU43 | none | **12-month medical** (firm `shall`) |
| GU66 | none | 6-month health assessment — *and even that is hedged* "(recommended: …)" |
| GU99 | none | **annual training**; 5-year record retention |
| GU42, SP06 | none | none |
| GU35, GU39, GU50 | none recorded | — |

Trainer/examiner/invigilator roles carry **no validity anywhere** in this corpus. They are
maintained by annual reporting and by suspension-on-non-compliance, not by expiry. Recorded
`null` throughout by evidence.

---

## 7. Honest nulls

Of 104 obligations across the nine files written this pass, **86 have both cadences null**.
This is the real category §5 of the brief describes, and the causes are distinguishable:

- **No frequency published at all** — GU43 sampling "at regular intervals"; GU99 acoustic
  and illuminated sign checks "at regular intervals" *with* an unquantified instruction to
  increase frequency for riskier sites; GU42 "container should be emptied regularly".
- **Delegated cadence** — GU42 maintenance deferred to the manufacturer's manual; GU66
  drills "as per legislation"; S1 facility records "as set by local technical guidelines".
- **Genuinely aperiodic** — standing states (staffing, PPE, labelling) and event-driven
  duties (spills, sector change, revocation).
- **Fixed-date annual** — GU131 and S2 trainer reports due *by 31 December*.
  `cadence_months` left null deliberately: a 12-month rolling interval drifts off a fixed
  deadline.

---

## 8. Document defects found — none guessed at

- **S2 Annex D arithmetic** — *"a minimum total of twenty (20) hours … consists of:
  Twenty-three (23) hours … and One (1) hour for examination"*. 23+1 = 24, and §8.3.4
  independently says 24. **24 encoded**, on two corroborations against one bare assertion.
  Annex-D-only reading would have shipped a check four hours short.
- **S2 unresolvable cross-reference** — "modules 4 to 8" / "Module 6 to 8" against an
  **unnumbered eleven-item list**. The GU83 pattern from §7.14. Not relied on.
- **GU131 clause 1.1 vs the 2.8 table** — 1.1 requires an HSO always, the table exempts
  ≤50 rooms; 1.1 cross-refers to "clause 2.9", **which does not exist** (numbering stops at
  2.8). Recorded at `medium` with the resolver told not to auto-apply 1.1.
- **GU42 "not less than 30 to 75 linear m/min"** — a minimum cannot be a range. Only the
  30 encoded as a floor; the 75 deliberately **not** encoded as a ceiling.
- **GU42 water circulation** — "150 litres/1000 m³ of exhaust air" is dimensionally
  incomplete (per minute? per hour?). Flagged, not inferred.
- **S1 three anchor dates** for the same 2-year clock (issue / final accreditation approval
  / training-record remainder). Ceiling certain, anchor not.
- **S1 "Lagoons & other water features Lifeguards"** is in scope with **no prerequisites,
  no specialty exam and no depth rule**. Matters directly here — lagoon operators are in
  the client base. Do **not** infer that the pool specialty covers a lagoon.
- **S2 trainer "at least one (1) or two (2) years' training experience"** — two numbers, no
  rule for choosing. Flagged, **not** encoded as a limit.
- **GU99 degree glyphs lost in the text layer** — "450" for 45°, "600" for 60°. A bare
  number passed through would have been plausible-looking nonsense.
- **Sibling inconsistencies, same issue date** — S2 says failing grades "D or F", S3 says
  "D or E" (GU131 also D or F). S2 sets invigilator qualifications, S3 sets none. S3 says
  "soft copy", S2 says "copy". **Do not normalise these; record as printed per scheme.**
- **S2/S3 approval "valid for a specified period"** — and the period is never specified.
  Three occurrences.

---

## 9. §7.14 confirmed again — render-and-read earned its place twice

- **SP06 p12** — the permitted-services matrix is 5×7 of tick/cross glyphs. **The text
  layer returns headers and not one cell value.** Read from the render, it shows that an
  oriental bath may do *only* the bath, a massage centre *only* massage, and a spa club
  *only* jacuzzi/sauna/steam — the sharpest rules in the document. Text-only extraction
  would have shipped it empty.
- **GU99 pp11/27/28** — degree symbols dropped; the Annex D three-column table verified by
  position, not text order.
- **GU131 p8** — the HSO-per-room table's text layer returns rows in a misleading sequence;
  column mapping confirmed visually.

---

## 10. Corrections owed to `catalogue.json`

| Guideline | Field | Catalogue | Document |
|---|---|---|---|
| GU66 | `version` | `null` | **V 3.0** |
| GU42 | `evidence_type` | `unknown` ("likely LEV thorough examination") | measured engineering inspection — **no examination requirement exists** |
| GU43 | `evidence_type` | `laboratory` | sampling is real, but **no limits to judge against** — mark `delegating` |
| SP06 | `phase` | 5 | **6** — premises permit, not a competency scheme |
| GU42 | `phase` | 5 | quantitative/engineering — no people content |

---

## 11. Consistency defect in the three earlier files

`gu35`, `gu39` and `gu50` use **free-text `obligation_type` values** — `ppe_provision`,
`rescue_plan`, `gas_detector_calibration`, `bag_labelling` and 17 others — against the
closed vocabulary the nine files in this pass use (`sampling, examination, inspection,
self_inspection, health_screening, cleaning, deep_cleaning, disinfection, pest_control,
waste_removal, maintenance, competency, permit_renewal, reporting, review, risk_assessment,
process, isolation_and_notification`).

All nine new files validate clean against that list. **The three earlier files should be
normalised before load**, mapping the specific wording down into `applies_to` as the new
files do. Left unfixed, `obligation_type` cannot be used as an enum or grouped on.

Where the closed vocabulary had no exact term, the closest was used and said so in the
`cadence_note` — most often `reporting` for retain-and-produce-on-demand duties (GU131 §1.3,
S3 §5, S2 §6.1, GU99 maintenance records) and `process` for signage, labelling and
document-availability duties. **The vocabulary's real gap is a `record_retention` /
`produce_on_demand` type**; it recurs in eight of the nine documents.

---

## 12. What could not be obtained

- No register of approved Certification Bodies, training companies, trainers, examiners or
  DHA/DCAS-approved clinics in **any** scheme document. Verification is by holding a copy
  of the certificate, nothing more.
- No fee schedules — repeatedly "as defined by Dubai Municipality".
- No renewal-window length in GU131, S2 or S3 (only S1 states one: two months).
- No statement of what happens between expiry and renewal in GU131, S2 or S3. Only S1 says
  it explicitly, and says there is no grace period. **Do not generalise S1's answer.**
- No lifeguard headcount formula (S1), no OHS Practitioner ratio (S3), no lead-work
  precautions despite GU42 requiring "special precautions", no fitness-equipment spacing
  figure (SP06).
- GU131 clause 2.9, S2's module numbering, and S1's lagoon specialty — three references to
  content that does not exist in the documents. **Only DM can close these.**
