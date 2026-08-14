# Phase 3 plant certificates — extraction notes

Guidelines covered: GU48, GU67, GU74, GU146, GU41. GU47 skipped (Arabic).
Extracted from the published DM PDFs only. Versions and issue dates are taken from
the cover page and page footers of each document, never from a filename, a URL path
or the portal record date (§7.1, §7.11, §7.12 verification traps).

---

## 1. Documents obtained, and the version/date corrections that came out of them

| Guideline | Code as printed | Version | Issue date (from PDF) | Superseded | Pages |
|---|---|---|---|---|---|
| GU48 | DM-HSD-GU48-ECLA2 | V 5.0 | 2025-01-29 | 2024-05-09 | 6 |
| GU67 | DM-HSD-GU67-MEWP2 | V 2.0 | 2024-09-06 | 2021-01-11 | 23 |
| GU74 | DM-HSD-GU74-MAT2 | V 3.0 | 2025-09-12 | 2021-01-12 | 18 |
| GU146 | **DM-HSD-146-FL2** | V 1.0 | 2025-12-15 | New (first edition) | 14 |
| GU41 | DM-HSD-GU41-GDM2 | V 3.0 | 2024-04-30 | 2020-01-05 | 10 |
| GU47 | DM-HSD-GU47-ECBPV1 | V 5.0 | 2026-01-20 | 2024-04-30 | 10 (Arabic) |

Every one of these six issue dates is a new fact — `catalogue.json` records
`issued_on: null` for all of them. They should be loaded into `standards.issued_on`;
the `portal_document_date` values must stay where they are (§7.11).

**Corrections to `catalogue.json` that follow from reading the documents:**

1. **GU146 has a document code and the catalogue records `null`.** It is
   `DM-HSD-146-FL2`, printed on the cover and in every page footer. Note it omits
   the `GU` prefix every other guideline uses — that is DM's own irregularity, not a
   transcription slip, and it is exactly the kind of thing that silently breaks
   citation matching (compare the GU10/GU101 conflict in §7.11).
2. **GU47 is V 5.0 issued 20/01/2026, superseding 30/04/2024** — recoverable from
   the Arabic cover page without translating the body. The catalogue has
   `version: null`. This also makes GU47 the *newest* document in the Phase 3 set,
   which raises rather than lowers the cost of leaving it untranslated.
3. **Three source URLs sit under upload paths that contradict the edition.**
   GU67's URL is under `/uploads/2021/05/` for a document issued 06/09/2024;
   GU74's is under `/uploads/2021/01/` for a document issued 12/09/2025; GU146's
   filename ends `10.5.26` for a document issued 15/12/2025. The §7.12 rule
   ("never take version from a filename") needs its sibling stated explicitly:
   **never take a date from a URL path or filename either.**
4. GU41's filename says `26-04-2024`; the document says 30/04/2024. Four days out.

**GU47 (boilers and pressure vessels) was not extracted.** The published PDF is
Arabic throughout — 8,002 Arabic characters against 630 Latin, and the Latin
characters are almost entirely the document code, the "OPEN DATA" banner and the
bilingual header labels. There is no English section. This confirms §7.2: GU47 needs
a native-Arabic reviewer before it can be encoded, and it is one of the three
priority certificate SKUs. It is also, per correction 2 above, the most recently
revised document in the group, so a translation done now will not be wasted.

---

## 2. `module_kind` judgement per guideline (§7.12)

All five extracted guidelines are **compliance**. That verdict is uniform but the
reasoning is not, and the differences matter more than the label.

### GU48 — compliance. Cleanly so.
Requirement 1 is a single sentence carrying subject, examiner, accreditation body
and interval: lifting equipment "shall be tested and certified by a third party
accredited by EIAC once every 12 months". Whether a current EIAC certificate exists
is a fact, not a judgement. Nothing in GU48 is advisory; it is six pages of
requirements with no "should".

### GU146 — compliance. Equally clean on the certificate clause, advisory elsewhere.
"Forklifts and their attachments shall be inspected and certified by EIAC-accredited
inspection bodies annually with certificates retained on-site" is the best-drafted
certificate clause in the set — it even names the accreditation scheme in its
references (EIAC-RQ-IB-002). But §§4.1–4.4 (traffic management, segregation, camera
and sensor specification) are design guidance in "should" language with approximate
figures ("≈1–2 m"). **A GU146 report must confine its verdict to the record-based
obligations** — annual EIAC certificate, documented pre-shift inspection, monthly
sensor functional test, annual traffic-plan review — and must not claim compliance
against the technology-design sections. Those advisory figures are tagged
`ADVISORY DESIGN PARAMETER` in the limits array and given `confidence: low` so the
resolver has a hook to exclude them.

### GU67 — compliance, but narrowly, and the mandatory core is one sentence.
Twenty-three pages, of which about twenty are risk-assessment and safe-system-of-work
guidance yielding no verdict. Two clauses are hard: the six-monthly EIAC third-party
inspection (4-16), and EIAC inspection and certification of any modification (4-13).
The 15 m / 9 m overhead-line clearances are stated as a mandatory minimum ("must
always be kept") and are genuine numeric limits, though GU67 itself defers to DEWA
where DEWA is stricter — a partial delegation that a resolver must not silently
resolve on its own.

### GU74 — compliance, but the evidence is a checklist, not a certificate.
**GU74 does not fit Phase 3.** It requires no accredited third-party periodic
examination at all — no EIAC, no named body. Its recurring obligation is an in-house
inspection "at regular intervals not exceeding seven days". The only third-party
artefact is a one-off BS EN 1004 product conformity certification held by the tower
as supplied, which never expires and is never re-issued. What makes a verdict
possible is a set of dimensional limits (950 mm guardrail, 470 mm maximum opening,
150 mm toe board, 600 mm platform width) verified by looking at the tower.
This is the §4.6 checklist primitive wearing a certificate module's badge.

### GU41 — compliance, and it is in the wrong phase.
GU41 sets real, measurable requirements — 6 mm work rest gap, 6 mm disc-knife guard
gap, 45 cm self-acting machine clearance, mandatory interlocks and fixed guards — so
a verdict is defensible. But it names no accreditation body, requires no third party,
issues no certificate and states no validity period. Its sole periodic examination is
a 12-monthly balance check of centrifugal machine cages by "a competent person",
competence undefined. Twelve of its thirteen asset types carry no examination at all;
they carry guard-design specifications. **GU41 is a Phase 4 checklist guideline with
one certificate-shaped row attached.**

GU41 also contains a delegating clause that no module can resolve: §4-2 says
"Details on guard for different machines may be obtained from the Health and Safety
Departmental". For any machine type not among the ten enumerated in §4-3, the
binding specification lives in a phone call to DM, not in a published standard. That
is a worse form of §7.12 *delegating* than GU10 → ASHRAE 62.1, because at least
ASHRAE 62.1 can be bought.

---

## 3. The question that determines whether Phase 3 is one build or five

**One primitive serves GU48, GU67 and GU146 — the three the scoping document already
calls the priority set, minus GU47 and plus GU146. GU74 and GU41 do not fit it and
should not be built as certificate SKUs.**

### What the three share, precisely

| | GU48 | GU67 | GU146 |
|---|---|---|---|
| Recurring third-party examination | yes | yes | yes |
| Interval stated as a number of months | 12 | 6 | 12 |
| Examiner accreditation named | EIAC | EIAC | EIAC |
| Certificate explicitly required | yes | "inspected and certified" (modifications) | yes, retained on-site |
| Certificate validity period stated | **no** | **no** | **no** |
| Event-triggered re-examination | after repair | after modification | after repair, before return to service |
| Person-certification clause in the same document | yes (operators, riggers, signalmen) | yes (operators, 2-yearly training) | yes (operators, third-party certified) |

The row that matters most is the empty one. **Not one of the five documents states a
certificate validity period.** They all state an examination interval and stop. So
`certificates.valid_until` (§4.4) cannot be derived from the standard — it can only
come from the certificate document the client uploads, or be computed as
`issued_on + interval` under an explicit, recorded assumption. `certificate_validity_months`
is `null` in every row of all five files for exactly this reason, and the difference
between "interval" and "validity" is not academic here: it is the whole basis of the
overdue calculation. **This needs a product decision before the primitive is built,
and the decision must be visible in the report**, not buried in a resolver default.

### What the primitive needs that §4.4 does not yet have

1. **An `examinations` layer between `standards` and `certificates`.** A guideline
   imposes several distinct examinations on the same asset at different intervals by
   different examiners — GU146 alone has an annual EIAC certification, a per-shift
   in-house check, and a monthly sensor test. One `standard_id` on a certificate row
   cannot express which examination the certificate discharges.
2. **Event-triggered obligations as first-class rows.** Every one of the five
   documents has them, and they are 14 of the 29 examination rows extracted. "After
   substantial repair", "after modification", "after any event likely to have
   affected strength or stability", "before first use", "before return to service".
   These have no due date until the event occurs, so they cannot live in the same
   due/overdue query as a periodic obligation without a null-safe branch.
3. **Cadence in days as well as months.** GU74's seven-day inspection is the only
   sub-monthly cadence, and converting it to 0.23 months would be a fabrication.
   `cadence_days` is populated and `cadence_months` left null in that row.
4. **A shared examiner/accreditation registry.** EIAC accreditation appears in three
   of the five documents, and GU146 cites the specific scheme (EIAC-RQ-IB-002 for
   lifting equipment inspection bodies). This is the same shape as the §4.7
   `laboratories` accreditation gate, and should reuse it rather than duplicate it —
   a body accredited for lifting equipment is not thereby accredited for anything else.
5. **A `subject_kind` discriminator, needed sooner than Phase 5.** Every one of the
   five documents certifies *people* alongside plant, in the same clause list: GU48
   requirements 10–12 (operators, riggers, signalmen, KHDA-approved training
   institutes), GU67's two-yearly ISO 18878 operator training, GU74's periodical
   medical surveillance and DHA Occupational Health Card, GU146's third-party
   certified operators. §4.4 already anticipates this with the `subject_user_id` /
   `asset_id` CHECK constraint, and that constraint is right — but it means the
   Phase 5 people work is not cleanly separable from Phase 3. Selling a GU48 module
   that ignores requirements 10–12 sells two thirds of the guideline. The
   person-scoped rows are marked `PERSON, not plant` in the `applies_to` field of
   each file so they can be filtered either way.

### Recommendation

- **Build one primitive against GU48, GU67 and GU146.** Three SKUs, one shape, three
  intervals (12 / 6 / 12 months), one accreditation body. GU67's six-monthly cadence
  is the useful test that the interval is data and not a hardcoded year.
- **Move GU74 and GU41 to Phase 4** and build them on the checklist primitive. They
  are cheap once that exists and expensive now: GU74 has eleven dimensional limits and
  a 7-day cadence but no certificate; GU41 has thirteen asset types, three limits and
  one examination. Building certificate SKUs for them would mean shipping a module
  whose central artefact the source document never requires — which is the §7.12
  misrepresentation risk arriving from a third direction.
- **GU47 stays blocked on translation** and is worth translating first among the
  Arabic set: it is the remaining priority-three SKU, it is a boilers-and-pressure-vessels
  module every FM contractor carries, and it was revised in January 2026 so the
  translation will hold.
- **Once the primitive exists, GU62 (acetylene generators) and GU53 (LPG cylinders)
  are the next cheapest additions** — §7.11 already identified them, both are English,
  both are in the catalogue with `evidence_type: certificate`, and neither was read
  for this extraction.

---

## 4. Ambiguities and things left deliberately unresolved

- **GU74 cites three different designations for its governing product standard.**
  Scope (p5) says "BS EN 1004"; the document history log (p2) records an update "of
  Standard BS EN1004 to BS EN1004-1"; the references section (p13) cites
  "BS EN 1004-2". A conformity check cannot be automated until DM says which part
  applies. Recorded as printed, all three.
- **GU74's wind figures are advisory, not DM limits.** 27 km/h ("recommended by many
  manufacturers") and 64 km/h ("if there is a possibility of the wind reaching speeds
  approaching or more than"). Both are captured with `confidence: low` and an
  `ADVISORY, NOT A DM LIMIT` label so they cannot be mistaken for a stop-work
  threshold. This is the GU38 failure mode (§6) in miniature.
- **GU146's blue/red light distances are tunable design guidance,** given with `≈`
  and explicitly to be adjusted to aisle width, floor reflectance and speed during
  commissioning. Captured, labelled advisory, `confidence: low`.
- **"Frequently" appears four times in GU146 and once in GU74 where an interval
  should be.** Camera calibration "frequently", barrier and floor-marking inspection
  "frequently", pedestrian-vehicle refresher training "(frequently)", temporary-route
  review "frequently". Each is recorded with both cadence fields null and a
  `cadence_note` saying the document is silent. None was assigned a number.
- **GU48 and GU146 both impose a 12-month EIAC test on forklifts.** GU48 requirement 1
  names forklifts explicitly; GU146 is the dedicated forklift guideline. If both are
  sold as modules, one forklift must not generate two overdue obligations for the
  same examination. This needs a de-duplication rule at the obligation level, and it
  is the first concrete case of two guidelines claiming the same asset.
- **GU67's 15 m / 9 m clearances defer to DEWA where DEWA is stricter** ("The stricter
  requirement shall be followed"). The module can assert the GU67 figure as a floor
  but cannot assert compliance without knowing the DEWA requirement for the site.
- **GU41 §4-2 delegates guard details for unenumerated machines to the Health and
  Safety Department by enquiry.** Unresolvable in software; flagged in the file.
- **GU48 requirement 4 conflates issuing a certificate with completing repairs**
  ("shall issue a certificate of safety after due examination and test, and only after
  any repairs have been carried out"). Read as a condition on certificate issue, and
  recorded separately as a `trigger_event` row at `confidence: medium`, because it is
  genuinely unclear whether a fresh examination is required post-repair or the
  original one is simply held open.
