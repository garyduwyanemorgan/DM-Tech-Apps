# DM water guidelines — extraction notes (Phase 2 laboratory group)

Guidelines covered: GU81, GU80, GU34, GU120, GU145, GU142, GU133.
Retrieved 2026-08-14 from <https://www.dm.gov.ae/municipality-business/technical-guidelines-list/>.
Output: `gu<N>_limits.json` per guideline, shaped for `standards` / `specification_sets` /
`spec_limits` / `obligations` (DM_COMPLIANCE_SCOPING.md §4.1–4.3, migration 022).

**Everything below is UNVERIFIED.** Every limit carries `source_page` and
`source_quote`; nothing here may be sold until a human has opened the cited page
and confirmed it (§7.1 narrow-verified-catalogue decision, and the rule already
written into `core/standards.py`).

---

## 1. What was obtained

| GU | Code | Version | Issued | Limits found | Lab-evidenced? |
|---|---|---|---|---|---|
| 81 | DM-HSD-GU81-PSPS2 | V 3.0 | 2024-04-30 | 11 sets, 34 limits | yes (microbiological) |
| 80 | DM-HSD-GU80-PRSPS2 | V 1.0 | 2020-01-14 | 2 sets, 12 limits | yes (microbiological) |
| 34 | DM-HSD-GU34-ASPP2 | V 4.0 | 2024-05-04 | **none — process document** | no |
| 120 | DM-HSD-GU120-WF2 | V 2.0 | 2024-03-11 | 1 limit (depth, dimensional) | no — defers to GU44 |
| 145 | DM-HSD-145-WC | V 1.0 | 2026-02-13 | **none** — 3 obligations only | yes, but no criteria given |
| 142 | DM-HSD-GU142-MRC2 | V1 | 2025-05-12 | 2 sets, 5 limits | yes (air + surface spores) |
| 133 | DM-HSD-GU133-EWS2 | V.1 | 2025-03-25 | 1 process-control limit | yes, but no criteria given |

All seven PDFs were obtained. **Nothing was unobtainable.**

### GU34 — the question asked: process, not limits

**Confirmed process.** GU34 is issued by the *Registration & Permits Section*, not
the Safety or Environmental Health sections, and is titled "Technical Guidelines for
Approval of Swimming Pool Plans". Its section 5 "Technical Requirements" covers
stairs and ladders, showers, diving boards, lighting, depth marking, deck area,
filtering, disinfecting equipment, children's pools and Jacuzzis — all design and
plan-approval criteria. It contains **no water quality parameter, no acceptable
range, and no sampling requirement**; the only occurrence of the word "sampling" in
the whole document is "sampling taps" as a required fitting on a filter device.

`gu34_limits.json` was still written, with empty `specification_sets` and
`obligations`, because the edition facts (code, V 4.0, 2024-05-04, supersedes
2022-03-11) are wanted for the `standards` registry even though no
specification set hangs off them. **GU34 is not a Phase 2 quantitative SKU.**
If it is sold at all it belongs with the Phase 4/6 checklist primitive.

---

## 2. The single most important caveat: bare ranges carry no operator

Almost every DM pool limit is printed as a bare range — `7.2 - 7.6`,
`60 - 200 mg/l`, `1 to 2 mg/liter`, `100 to 500 ppm` — with **no `<`, `>`, `≤` or
`≥` glyph anywhere**. Read strictly, inclusivity is undetermined for all of them.

Encoding them all as `min_inclusive: null` would have made every pool limit
unseedable (022 declares both columns `NOT NULL`), which is a worse outcome than
stating the reading and flagging it. So the convention applied is:

> **A bare range is encoded inclusive of both endpoints, at `confidence: "medium"`,
> with the absence of an operator glyph stated explicitly in `source_quote`.**

The textual support is GU81 §4-16, which requires the value be "continuously
controlled and monitored **within the ranges** as specified in Table 5", and the
GU80/GU81 column heading "Acceptable Range". A value sitting exactly on an
endpoint of a range described as acceptable is most naturally acceptable.

**This convention needs a human ratification decision, once, for the whole pool
family.** It is not a per-limit judgement call and should not be re-litigated
parameter by parameter. Where a real operator glyph *is* printed it was used and
the confidence is `high` — see GU142 (`<16%`, `<60%` — exclusive) and GU120
("must not exceed 50 cm" — inclusive).

This matches the reading already used by the sibling GU38 extraction
(`gu38_limits.json` reads "35 to 39 ºC" as inclusive), so the two are consistent.

---

## 3. Ambiguities that were NOT resolved, by guideline

### GU81 — free chlorine minima are conditional, and the document contradicts itself

Table 5 prints the free chlorine floor as a *range of minima*: `Min. 1 - 2 mg/l`
(≤26 °C), `Min. 2 - 3 mg/l` (26–30 °C), `Min. 2 - 4 mg/l` (>30 °C). Footnote 3
explains the two-valuedness — the floor depends on whether cyanuric acid is used:

> "If cyanuric acid is used, minimum free chlorine is 2 mg/l at ≤26 °C and 4 mg/l
> at > 26 °C. For unstabilized pool water (without cyanuric acid), minimum free
> chlorine is 1 mg/l at ≤26 °C and 2 mg/l at > 26 °C."

Two problems:

1. Footnote 3 knows only **two** temperature bands (≤26, >26) while the table has
   **three** (≤26, 26–30, >30). For the 26–30 °C band the footnote yields
   {2, 4} mg/l but the table cell says `Min. 2 - 3 mg/l`. **The 3 mg/l figure
   appears nowhere else in the document.** This is a genuine internal
   inconsistency and needs a ruling from DM.
2. The stabilizer condition is not a property of the sample, it is a property of
   how the pool is dosed — so it cannot be resolved from a laboratory certificate
   alone. Correct modelling is probably to split each chlorine set into
   stabilized / unstabilized variants and let the client declare which applies.

**What was done instead, pending that ruling:** `min_val` is set to the *lowest*
value the document permits anywhere in that band (1, 2, 2), `confidence: "low"`,
and both the table cell and footnote 3 are quoted in full in `source_quote`. This
under-detects a stabilized pool but **cannot manufacture a false FAIL**, which is
the safer error for a regulator-facing report per §7.4. Do not sell these three
sets before resolving them.

### GU81 — the bromine cells for swimming pools state no direction at all

For swimming/wading/waterslide pools the bromine cells read exactly `2 mg/l` and
`4 mg/l` — **no operator, and no `Min.` prefix**, unlike every chlorine cell in
the same table and unlike the hydrotherapy and spa bromine cells, which do read
`Min. 4 mg/l` and `Min. 8 mg/l`. Whether 2 mg/l is a floor, a target or a ceiling
is simply not stated for those two rows.

`min_inclusive` is left **null** on both, which will block seeding until a human
resolves it. That is the intended behaviour of 022's `NOT NULL` with no default.

### GU81 — the `≤` glyph is missing from the PDF's text layer

The temperature band cells extract as a blank followed by `26OC`, paired in the
same table against `> 26OC`. `≤` is the only consistent reading, and it is used
in `applies_to` — but it was **inferred from context, not read**. The same
glyph-dropping means the Table 6 cell `1000 cfu/ml` may actually print as
`≤ 1000 cfu/ml` (which gives the same inclusive answer, so nothing turns on it).
No numeric `display` string in GU81 depends on a dropped glyph.

Note also that GU81's Table 5 is **split across pages 30 and 31** and the column
headers repeat per row-group. `pdftotext -layout` scrambles it badly and produced
a plausible-but-wrong reading on the first pass; `pdftotext -table` recovers it
correctly. Anyone re-verifying should use `-table`, or read the printed page.

### GU80 vs GU81 — do not carry values across

Private and public pool limits **differ**, and several differences are easy to
miss because the parameters share names:

| Parameter | GU80 (private) | GU81 (public) |
|---|---|---|
| pH | 7.4 to 7.6 | 7.2 – 7.6 (chlorine) / 7.2 – 7.8 (bromine) |
| Total alkalinity | 70 to 100 **ppm** | 60 – 200 **mg/l** |
| Cyanuric acid | 20 to 60 mg/liter | 30 – 50 mg/l |
| Free chlorine | 1 to 2 mg/liter (closed range) | `Min.` floor, varies by temp/stabilizer |

GU80 states one flat table for all private pools with no split by pool type,
disinfectant or temperature; GU81 splits nine ways. The units genuinely differ
(ppm vs mg/l) and were preserved verbatim rather than normalised.

### GU142 — two different clearance criteria for the same measurement

Section 9 (p19) says material moisture "should not exceed 16-18%" — inclusive,
and *itself a range*, with the document saying it "may vary based on material
type" without saying which material takes which value. Appendix 3 (p26) says
"Moisture content **<16%** for wood and drywall" — explicitly exclusive and
stricter. Both are in force on their face.

They are encoded as two separate sets (`..._laboratory_clearance` and
`..._visual_clearance`) with the conflict stated in both `source_quote`s. The
section 9 figure takes `max_val: 18` (the higher, so it cannot cause a false
FAIL) at `confidence: "low"`.

Also in GU142: "ideally between 30-50%" relative humidity is prefaced by
*ideally* and was **not** encoded as a bound. "Bi-annual inspection schedule"
(p20) is recorded as `cadence_months: 6` but "bi-annual" is undefined in the
document and can mean 24 months; flagged in the obligation's `source_quote`.

### GU142 — the airborne spore limit is RELATIVE, not absolute

"indoor levels should not exceed 50% of outdoor levels" cannot be judged from an
indoor result alone — it needs a paired outdoor control sample from the same
sampling event. `core/specs.py` must return NOT_ASSESSED when only the indoor
figure is present, never a pass. This is a resolver capability the current
`ComplianceLimit` model does not have and it should be sized before GU142 is sold.

### GU133 — website issue date disagrees with the document

dm.gov.ae shows an issue date of 09/06/2026 for GU133; the PDF's own cover page
and every page footer say **25th March 2025, Version 1, Superseded: New**. The
document was used. Same pattern on GU145: the site says 15/07/2026, the PDF says
13/02/2026. Treat the site's date as a publication/upload date, not an issue date.

### GU145 — Arabic only, and the extraction is bidi-mangled

GU145 is published in Arabic only (§7.2 territory: needs a native-Arabic
reviewer, sequence last). Text extracts with `pdftotext -enc UTF-8` but words are
reversed and split by the bidi algorithm, so **operator glyphs cannot be trusted
in direction**. Specifically:

- Sabeel-fridge cooling temperature extracts as `(≥ 5°م تقريبًا)`. Physically it
  must be `≤ 5 °C`, and the sentence ends in `تقريبًا` ("approximately") anyway.
  **Not encoded** — a guessed operator on a reversed glyph is exactly the failure
  mode the brief forbids.
- Concrete base thickness "not less than 10 cm" and rear/side ventilation
  clearance "not less than 10–15 cm" are unambiguous but are installation
  dimensions, not lab-evidenced parameters. **Not encoded**; recorded here.

What GU145 *does* give, unambiguously, is the cadence — see §4.

---

## 4. Sampling obligations recovered (§4.3 — the commercially valuable half)

| GU | Cadence | What | Evidence |
|---|---|---|---|
| 81 | daily, before use | pH, chlorine, temperature (logbook) | in-house |
| 81 | every 15 days | calcium hardness, alkalinity, saturation index, cyanuric acid | in-house |
| 81 | **every 2 months** | microbiological (Table 6) | **laboratory** |
| 80 | daily, before use | pH, chlorine, temperature (logbook) | in-house |
| 80 | every 15 days | calcium hardness, alkalinity, saturation index, cyanuric acid | in-house |
| 80 | **every 2 months** | microbiological (Table 2) | **laboratory** |
| 145 | **every 6 months** | freedom from pathogenic bacteria | **EIAC-accredited lab** |
| 145 | every 6 months (at least) | cleaning and disinfection of the cooler | contractor |
| 145 | every 6 months or per manufacturer, whichever sooner | filter replacement | contractor |
| 142 | event-triggered | post-remediation air + surface clearance | **ISO/IEC 17025, EIAC-accredited lab** |
| 142 | bi-annual (ambiguous) | visual inspection of high-risk areas | in-house |
| 133 | event-triggered | post-disinfection tank and network samples | **accredited lab** |
| 120 | — | "regularly" / "periodic", no number given | — |
| 34 | — | none | — |

**GU145 is the sleeper commercial finding.** It carries no limits we can encode
at all, but it carries a hard six-month laboratory cadence against an asset class
(public drinking water coolers) that exists in large numbers on every FM site. Per
§4.3 the product's core claim is knowing a test was due and never arrived — GU145
supports that claim fully while supporting no verdict claim whatsoever. It should
probably be scoped as an obligations-only module.

Note the §4.7 relevance: GU133, GU142 and GU145 all name **the Emirates
International Accreditation Centre (EIAC)** as the accrediting body, and GU142
additionally requires ISO/IEC 17025. That is the concrete accreditation vocabulary
the `laboratories` table needs, and it is consistent across three documents.

---

## 5. Guidelines that defer their limits to an external standard

This was asked for specifically. Four of the seven defer, and two defer entirely:

- **GU120 (water features) — defers completely.** It contains no water quality
  parameter at all. It says: "Perform periodic cleaning and disinfection of water
  features and water treatment **according to the Technical Guidelines of the
  Control of Legionella Bacteria in Water Systems issued by Dubai Municipality
  (DM-HSD-GU44-LCWS2)**" and "Water sample testing should be conducted according
  to DM technical guidelines" (p6). **A GU120 module is therefore a GU44 module
  wearing a different asset type.** Good news commercially — GU44 is already being
  encoded in Phase 1 — but it means GU120 has no independent limit content and
  should not be priced as though it does.
- **GU133 (emergency water systems) — defers completely.** Appendix 4 (p17) is a
  *test panel matrix*: it says which parameters must be tested for non-drinking
  water, non-bottled drinking water and swimming pool water, and gives **no
  acceptable value for any of them**. Its references point to **GU17 (Quality of
  Un-bottled Drinking Water, DM-HSD-GU17-DW1 — Arabic only, §7.2)**, **GU44**, and
  **WHO Guidelines for Drinking-water Quality, 4th edition + 1st addendum**. To
  sell GU133 as a verdict-producing module we would need GU17 encoded first.
- **GU145 (water coolers) — defers to Gulf standards.** It requires conformity to
  **UAE.S GSO 1811** (the cooler itself) and **UAE.S GSO 2071** (water filters).
  These are GSO/ESMA standards, not DM publications — they are **paid standards**,
  not free downloads, which is a real acquisition cost if we ever want the
  underlying criteria. Its own water quality criterion is the untestable-as-written
  "free from pathogenic bacteria".
- **GU142 (mould) — defers on method, not on limits.** Its two numeric criteria are
  its own, but sampling methodology defers to **ASTM D7338-14** and **ISO
  16000-21**, and prevention references **ASHRAE 160** and **ASHRAE 62.1**. Method
  standards do not block encoding the limits; they would matter for a laboratory
  scope-of-accreditation check (§4.7).

GU81, GU80 and GU34 are self-contained.

---

## 6. The lagoon limits in `core/constants.py` — NEGATIVE RESULT

**I could not find the published source of the ten `COMPLIANCE_LIMITS` values,
and I am not proposing an attribution. `specification_sets.standard_id` should
stay NULL for the seeded lagoon set.**

022 already anticipates this: `standard_id` is "Nullable because client-specific
sets exist that derive from no single published document." That nullable is the
correct home for the lagoon set until provenance is established.

### What was searched

1. **The full DM HSD technical guidelines catalogue (81 documents).** Filtering
   every title for water/lagoon/lake/pond/reuse/irrigation/recreation/effluent/
   bathing yields exactly eight documents: GU145, GU141, GU135, GU133, GU120,
   GU90, GU44 and GU17. **None of them is a surface-water, water-reuse,
   irrigation-water or recreational-water-body standard.** The HSD catalogue is an
   occupational health and safety catalogue; ambient water body quality is not in
   its remit. The source, whatever it is, is **not** in the list this project is
   working from.
2. **The pool guidelines specifically.** GU81 and GU80 share not one parameter
   with the lagoon set. Pools are judged on disinfectant residual, pH, alkalinity,
   hardness, cyanuric acid and five microbiological parameters. The lagoon set is
   pH, DO, TSS, turbidity, COD, ammonia, phosphate, oil & grease, E. coli and
   total coliforms — an ambient/effluent profile, not a disinfected-pool profile.
   pH is the only overlap and the ranges differ (6.0–9.0 vs 7.2–7.8).
   **Attributing the lagoon set to GU81 or GU80 would be plainly wrong.**
3. **DM water-reuse and irrigation limits.** Checked and **ruled out on the
   numbers**: DM's irrigation-reuse limits run COD 150 mg/l (unrestricted) /
   200 mg/l (restricted) and TSS 15 / 30 mg/l. The lagoon set is COD 50 and
   TSS 50. These are different regimes, not different editions of one regime.
4. **The repo's own provenance chain.** `core/constants.py:3` says "All values
   sourced from `Dubai_Lagoon_Algae_Management_System.md`." **That file does not
   exist** — not in `DM-Tech-Apps`, not in the frozen `DECCA-Lagoons-App`, and not
   in git history in either repo. The citation names an internal design document,
   not a DM publication, and the document itself is lost.
5. **The laboratory certificates.** The only regulatory citation anywhere in
   `Lab Reports Example/` is `DM-HSD-GU44-LCWS2`. No certificate in the sample set
   names a standard for the lagoon parameters — the lagoon comparison appears to be
   ours, made against a "Dubai Municipality limits" column, not the laboratory's.

### What this means

The provenance chain terminates at a missing internal markdown file. There is no
evidence in either repo, in the DM HSD catalogue, or in the laboratory
certificates that these ten values were ever read off a published DM document —
and they may well be a consultant's operating envelope for the Safari Park
lagoons rather than a regulatory standard at all. The `display` strings
(`> 4.0`, `< 50`, `< 200`) are also all strict-inequality, which is a *Python
author's* formatting habit, not how DM prints limits — every DM document examined
here uses bare ranges and "shall not exceed".

### Recommended next step

Ask Al Ghurair / the Safari Park operator for the document their lagoon
obligation is written against, and ask the laboratory which specification it
prints on the lagoon certificates. One email resolves this properly. Two places
worth checking that are outside the HSD catalogue and outside my reach here:

- Dubai Municipality **Environment Department / Sewerage and Recycled Water
  Projects Circulars** (linked from the same site, a different catalogue).
- The **project's own consent or EIA condition** for the Safari Park water
  bodies — site-specific consent limits would explain both the parameter mix and
  the absence of any matching published guideline.

Until then: leave `standard_id` NULL, label the set as client-specific, and do
**not** print a guideline citation on lagoon reports. §7.1 is explicit that a
wrong citation is a liability, and a false attribution here would appear on every
lagoon report the product has ever produced.

---

## 7. Tooling note for whoever verifies this

`pdftotext` in this environment is **xpdf 4.06, not poppler** — it has no `-bbox`
and there is no `pdftoppm`, so PDF pages could not be rendered to images for
visual confirmation. Column alignment was recovered with `pdftotext -table`, which
handled every table here correctly, but **no table was confirmed visually**.
GU81 Table 5 is the one that most warrants a human eye on the printed page: it is
split across two pages, has nine row-groups with repeating headers, and its
`-layout` rendering is actively misleading.

### Transcription safeguards applied

- **No `version` was taken from a filename or a URL.** Every version string comes
  from the PDF's own cover page or page footer. This matters here: GU142's URL
  says `V_1-002` while the document says `V1`, and GU133's URL says `V_1-002`
  while the document says `Version #: 1`. The site's *issue dates* are also wrong
  for GU133 and GU145 (see §3) — the document was used in both cases.
- **Units were read from inside the same cell as the number**, not from a column
  header matched by text order. Every DM pool table prints the unit alongside the
  value (`60 - 200 mg/l`, `1 to 2 mg/liter`, `0 mpn/100 ml`), so no number in this
  group depended on a column-position inference. The one place this could have
  gone wrong — GU81 Table 5, where a nine-row-group table spans a page break — was
  cross-checked against footnotes 2, 3, 4 and 7, which independently name the
  parameter, the value and the unit; all agreed.
- **Ambiguous cells were omitted, not guessed.** Left out on purpose: the GU145
  cooling temperature (`≥ 5°م` under bidi reversal, and hedged with "approximately"
  in any case), the GU142 "ideally between 30-50%" humidity aspiration, and the
  narrower gaseous-chlorine / BCDMH alkalinity ranges in GU81 footnotes 2 and 4,
  which depend on a disinfectant chemistry the certificate does not report.
  Where a value could not be omitted without losing a real safety floor — the
  GU81 free chlorine minima — it is encoded at the lowest permitted value with
  `confidence: "low"` and the conflict quoted in full, rather than silently picked.

### Schema conformance

All seven files validate against the shared shape used by the instrument-group
extractions (`gu38`, `gu119`, `gu141`, `gu10`): `standard` / `specification_sets`
/ `obligations`, with `limits` carrying the full twelve keys and every obligation
carrying `obligation_type`, `cadence_months`, `cadence_days`, `cadence_note`,
`applies_to`, `source_quote`. No file introduces a key of its own.

`gu34_limits.json` and `gu145_limits.json` have an empty `specification_sets`
array. That is the finding, not a gap: GU34 is a plan-approval process document
with no limits at all, and GU145 states a laboratory obligation with no acceptance
criteria attached to it. Both still carry their edition facts for the `standards`
registry, and GU145 carries three real cadences.

`cadence_note` is populated on all fourteen obligations, and says explicitly where
the document gives a number, where it gives an ambiguous one (GU142 "bi-annual"),
and where it is silent and the obligation is event-triggered rather than periodic
(all three GU133 obligations, and GU142 clearance sampling). No cadence was
synthesised for an event-triggered obligation.
