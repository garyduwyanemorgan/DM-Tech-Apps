# Instrument-measured guidelines — extraction notes

Covers the Phase 2 instrument group per `DM_COMPLIANCE_SCOPING.md` §6: **GU38**
(heat stress), **GU141** and **GU119** (indoor air quality), **GU10** (classroom
ventilation).

> **Everything in the four JSON files is UNVERIFIED.** Every limit carries
> `source_page` and `source_quote` so a human can check it against the published
> PDF cheaply. Nothing here has been checked by a second person, and nothing here
> should be sold under the §7.1 narrow-verified-catalogue rule until it has been.

---

## 1. Documents obtained

All four were obtained from `dm.gov.ae`. None had to be reconstructed from
secondary sources.

| Guideline | Document code as printed | Version | Issue date | Pages | PDF |
|---|---|---|---|---|---|
| GU38 | `DM-HSD-GU38-MHSW2` | V 3.0 | 09/05/2024 | 16 | [link](https://dmpmedia.dm.gov.ae/uploads/2024/07/DM-HSD-GU38-MHSW2_Technical-Guidelines-for-Management-of-Heat-Stress-at-Work_V3.pdf) |
| GU141 | `DM-HSD-GU141-IAQI2` | V1 | 14 Feb 2025 | 22 | [link](https://dmpmedia.dm.gov.ae/uploads/2025/10/Environmental-Indoor-Air-Quality-Index-V_1-004.pdf) |
| GU119 | `DM-HSD-GU119-IAQ` | V 4 | 11 Dec 2024 | 63 | [link](https://dmpmedia.dm.gov.ae/uploads/2025/01/DM-HSD-GU119-IAQ_Technical-Guidelines-for-Indoor-Air-Quality-for-Healthy-Life_V2.pdf) |
| GU10 | `DM-HSD-GU101-VSC2` | V 1.0 | 10 Dec 2020 | 4 | [link](https://dmpmedia.dm.gov.ae/uploads/2021/08/DM-HSD-GU101-VSC2_TECHNICAL-GUIDELINES-FOR-VENTILATION-IN-SCHOOL-CLASSES_-V1.pdf) |

Nothing was refused or unavailable. Method: the guideline list page links to a
per-document landing page (`dm.gov.ae/documents/hsd-gu38/` etc.), which in turn
links the PDF on `dmpmedia.dm.gov.ae`. Text and table geometry were extracted
with `pdfplumber`; where a table's column-to-value mapping mattered, word
x-coordinates were read directly rather than trusting the linearised text (see
§6).

### Provenance traps found while fetching

- **The GU119 URL lies about the version.** The file is named
  `..._V2.pdf` and sits under `/uploads/2025/01/`, but the document inside is
  **V 4, issued 11 December 2024**, superseding 10 July 2024. The `version`
  field in the JSON is taken from the document, not the filename. Do not seed
  `standards.version` from a URL for any guideline.
- **GU141's URL is under `/uploads/2025/10/`** but the document is V1 issued
  14 February 2025. Same lesson.
- **GU10's printed document code is `DM-HSD-GU101-VSC2`, not `GU10`.** The DM
  guidelines list titles it "Technical Guidelines (10) for Ventilation in School
  Classes" and the landing page is `hsd-gu10`, but every page footer of the PDF
  says `GU101`. `standards.code` is stored as printed (`DM-HSD-GU101-VSC2`) per
  the migration 022 comment — "as laboratories print it, do not normalise" — and
  `guideline_no` is set to 10 from the DM list. **Someone needs to confirm there
  is no separate GU101.** If there is, this row's `guideline_no` is wrong.
- **GU38's issue date `09/05/2024` is written numerically** and could be 9 May
  or 5 September. Recorded as **2024-05-09** (DD/MM, matching DM's usual
  convention and the superseded date 08/10/2019 which corroborates as 8 October
  2019 from the V2 record). GU141, GU119 and GU10 all spell their months out, so
  only GU38 carries this risk. Worth confirming before it drives
  `citation_is_stale`.

---

## 2. The headline finding: **GU38 is not a WBGT guideline**

The brief, and §6 of the scoping document, describe GU38 as "Heat stress at work
(WBGT)" and anticipate "a TABLE of thresholds varying by work intensity and
work/rest ratio".

**GU38 V3.0 contains no WBGT thresholds and no work/rest ratio table.** The
string "WBGT" does not appear in the document. What it actually contains:

- A four-row **Heat Index** table (page 7) mapping temperature bands to a *risk
  level* and a *control approach* — "basic heat safety and planning", "implement
  planned controls and create awareness", and so on.
- An Annex A **heat index chart** (temperature × relative humidity → apparent
  temperature) with a six-band legend running from "No discomfort" to "Death
  danger: imminent heat stroke".
- Two core body temperature ceilings for workers on work/rest cycles.
- Narrative controls (acclimatisation, shade, hydration, PPE, screening).

The only mention of wet bulb is instrumental, not a threshold: *"Employers shall
ensure that they have sufficient instruments such as dry and wet bulb globe
thermometers or are using properly calibrated instruments to measure temperature
and relative humidity"* (page 8). The instrument is named; no WBGT limit is
attached to it.

Two consequences:

1. **The parameter to model is `heat_index` (°C), not `wbgt`.** The
   `spec_limits.parameter_key` example `'wbgt'` in migration 022's column comment
   is aspirational, not sourced. Seeding a `wbgt` key would produce a parameter
   no DM document defines.
2. **The work/rest scheduling rule is delegated, not stated.** GU38 says
   *"the Ministry of Human Resources and Emiratization has issued regulations
   restricting the working hours schedule during summer in UAE. All employees
   shall adhere to this regulation"* (page 9). The actual stop-work rule — the
   midday break — lives in a **MoHRE** instrument that GU38 does not reproduce
   and does not cite by number. See §5 on external dependencies.

---

## 3. Compliance limits vs action levels, per guideline

This was asked explicitly and it is the commercially load-bearing distinction: a
breached **compliance limit** is a reportable non-compliance; a crossed **action
band** is a management trigger. Getting these confused in a report would claim a
regulatory breach that does not exist.

### GU38 — **no hard compliance limit on the environment. None.**

Stated plainly, because it changes how the module can be sold:

- The page 7 table is **action bands only**. Every row's third column is headed
  "Control Approach" and every cell describes management effort, not
  permissibility. Even the top band, 46 ºC and above, says "Enhanced controls as
  planned with enhanced awareness control" — *not* stop work. All twelve
  specification sets are therefore named `gu38_heat_index_action_band_*` and
  `gu38_annex_a_legend_*`.
- **The nearest thing to a stop-work rule is in a chart legend and it
  contradicts the main table.** Annex A's legend says "From 46 to 53˚C — Danger:
  stop all physical activities". The main normative table calls the same 46+
  region merely "Very high" with "enhanced controls". A legend on an
  informative annex chart is weak ground on which to declare a client
  non-compliant, and it disagrees with the body of the document. Recorded as its
  own set, labelled a legend, and **not** promoted to a compliance limit.
- **The only genuine numeric ceilings in GU38 are physiological**: core body
  temperature ≤ 38.5 ºC and ≤ 38 ºC (page 9). These are hard, inclusive, and
  unambiguous as numbers — but they are measured on a person, clinically, not by
  a site instrument, and no DM certificate or FM contractor deliverable reports
  them. They are not a sellable monitoring parameter.

**So: a GU38 module cannot claim to judge compliance.** It can claim to classify
a site's heat risk band, drive the control approach the band requires, and track
the daily checklist and the pre-employment medical screening obligation. That is
a real product — arguably a better one, since the band changes hourly and the
checklist is genuinely daily — but a report that renders "COMPLIANT / NON-COMPLIANT"
against a heat index reading would be asserting something GU38 does not say.
This needs to be settled before the module is priced and before any report
template is written.

### GU141 — **no compliance limit either; it is an index, not a threshold set.**

GU141 defines the EIAQI: eight pollutants plus temperature and humidity, each
mapped through breakpoint bands to a 0-500 sub-index, then combined two ways
(dominant-pollutant for real time, weighted summation for 8h/24h reporting).

The document requires compliance without defining it: *"Owners and Managements
bodies must ensure that EIAQI threshold values are met, and non-compliance is
addressed through enforcement measures according to Dubai Municipality IAQ
regulation"* (page 15). **It never says which EIAQI band constitutes "met".**
Is Moderate acceptable? Is Unhealthy for Sensitive Groups a breach? The document
is silent, and its own worked example ends at EIAQI 105 (Unhealthy for Sensitive
Groups) with the neutral gloss "IAQ needs improvement" rather than a verdict.

Every GU141 set is therefore labelled a **classification band**, and the pass
line is left undefined rather than guessed. **This is a question to put to DM
before the module ships**, because a plausible-looking answer ("Good and
Moderate pass") would be invention.

### GU119 — **this is the one with real compliance limits.**

GU119 is the document that actually says what must not be exceeded:

- *"The maximum limit for indoor air contaminants included in Table (1) must not
  be exceeded"* (new buildings, page 31).
- *"the maximum limit for indoor air contaminants included in Common Air
  Pollutant Table (2) must not be exceeded"* (existing buildings, page 32).
- *"the Carbon Monoxide (CO) concentration in the enclosed parking area is
  maintained **below** fifty (50) parts per million"* (page 28).

and it separately gives one clean **action level**: the parking CO alarm at
*"reaches or exceeds seventy-five (75) ppm in, at least, five percent (5%) of the
monitored locations"* (page 29). Compliance limit 50, alarm 75, kept in separate
sets (`gu119_parking_ventilation` vs `gu119_parking_co_alarm_action_level`).
Note the inclusivity flips between them — "below 50" is exclusive, "reaches or
exceeds 75" is inclusive — which is exactly the kind of pair the
`min_inclusive`/`max_inclusive` columns exist for.

Table 3 (thermal comfort) sits in between and is **not** a compliance limit: its
column is headed "Recommended Range" and the obligation is that the HVAC system
be *capable* of providing it for 95% of the year — a design capability, not a
measured pass/fail. Flagged as such in the set's `applies_to`.

**GU119 is the commercially strongest of the four**, and it is the one the
scoping document ranks second. On this evidence it should lead the instrument
group.

### GU10 — mandatory space rule, advisory everything else.

One `shall` (≥1 m² per student), the rest `should` (≤25 / ≤30 students, ≥295 /
≥345 CFM). And the actual ventilation requirement is delegated to ASHRAE 62.1
(§5 below). Thin.

---

## 4. Inclusivity: what the documents actually printed

Per the brief, inclusivity was taken only from notation, never from convention.

| Notation found | Read as | Where |
|---|---|---|
| `must not be exceeded`, `Max-acceptable` | **inclusive** max | GU119 Tables 1, 2, 4 |
| `below fifty (50) ppm` | **exclusive** max | GU119 parking CO |
| `reaches or exceeds 75 ppm` | **inclusive** min (alarm band) | GU119 parking alarm |
| `less than or equal to 38.5 ºC` | **inclusive** max | GU38 core body temp |
| `Up to 34 ºC`, `46 ºC and above` | **inclusive** | GU38 page 7 table |
| `From 35 to 39˚C`, `0-12`, `22 – 25.5` | **inclusive** both ends | GU38 Annex A, GU141 Tables 2 & 3 |
| `Over 54˚C`, `>250`, `<20` | **exclusive** | GU38 Annex A, GU141 Tables 2 & 3 |
| `not less than`, `at least`, `a minimum of` | **inclusive** min | GU10, GU119 §9-5, §9-6 |
| `should not exceed`, `not exceeding` | **inclusive** max | GU10 class sizes |

**One limit has `min_inclusive: null` on an attribution rather than an
operator**, and it is worth spelling out because it is the sharpest example of
the rule the brief set. GU38 page 9 reads:

> "...to maintain the core body temperature within the acceptable limits that is,
> **less than or equal to 38.5 ºC for acclimatized and less than or equal to 38 ºC
> for acclimatized workers.**"

Both categories are printed as "acclimatized". The operator is unambiguous
(inclusive, twice) and both numbers are certain. What is *not* stated is which
population the 38 ºC ceiling governs. Every external source and common sense say
the second should read "un-acclimatized" — which is precisely why it is not
recorded that way. It is stored as
`core_body_temperature_second_worker_category` with `confidence: "low"` and the
ambiguity written into `source_quote`. **A human should resolve this against DM,
not against intuition**, because a limit table that quietly says "un-acclimatized"
where the regulator's document says "acclimatized" is indefensible if it is ever
challenged.

### Band gaps — real, and they will produce NOT_ASSESSED

Several band tables do not tile the number line. These are not extraction
errors; the documents are printed this way:

- **GU38 page 7**: "Up to 34" then "35 to 39". A heat index of **34.5 falls in no
  band.**
- **GU38 Annex A legend**: "From 46 to 53" then "Over 54". **54.0 exactly falls
  in no band.**
- **GU141 Table 2**: every pollutant. PM₂.₅ "0-12" then "12.1-35" — **12.05 is
  unclassified**; same shape for all eight pollutants.
- **GU141 CO₂ starts at 400**, not 0. A reading of **380 ppm — entirely plausible
  indoors near an open window — falls in no band at all.**

`resolve_limits` must return `None`/NOT_ASSESSED for these rather than snapping
to the nearest band. Per §7.4 of the scoping document, that outcome has to stay
visible; silently rounding 12.05 into "Good" is the confident-wrong-verdict
failure mode.

---

## 5. Dependencies on external standards we would also need

| Guideline | External standard | What depends on it | Severity |
|---|---|---|---|
| **GU10** | **ASHRAE 62.1** | *The entire binding requirement.* "The outdoor airflow required in the breathing zone (classrooms) ... shall be not less than the value determined in accordance with ASHRAE Standards 62.1." The 295/345 CFM figures are described as being *from* ASHRAE and are qualified as "changeable according to the area size". | **Blocking** |
| GU141 | ISO/IEC 17025 | Sensor calibration and certification. Affects whether evidence is admissible, not what the limit is. | Gate, not limit |
| GU141 | ASHRAE 62.1-2022, ASHRAE 55-2020, ISO 16000, US EPA AQI, GB/T 18883-2002, CIBSE Guide A, EU 2008/50/EC, WHO | Listed as references for how the index was *derived*. The breakpoints are printed in full in GU141 itself, so none is needed to judge a reading. | None |
| GU119 | ISO/IEC 17025 | Instrument calibration standard. | Gate, not limit |
| GU119 | EIAC accreditation | Testing must be by "a Company or laboratory accredited under EIAC Accreditation Scheme". | Gate — see below |
| GU119 | US EPA TO compendium | Analytical methods for the individual-VOC route. | Method, not limit |
| GU119 | DM Legionella guideline (GU44) | Cooling tower cleaning is delegated to it. Already in our catalogue. | Cross-module |
| GU38 | MoHRE summer working hours regulation | The stop-work / midday break rule. Not reproduced, not cited by number. | **Blocking for any stop-work claim** |
| GU38 | Federal Law No. 8, Ministerial Order 32/1982, DM Local Order 61/1991 | Legal basis. No numbers. | None |

**GU10 cannot be honestly sold as a self-contained module.** Its one substantive
requirement points at a standard we would have to license, and the two CFM
figures it does print are explicitly area-dependent, so they are not a threshold
a resolver can apply to an arbitrary classroom. What is left that we can judge
alone — 1 m² per student, ≤25/≤30 students — is a floor-plan and register check,
not an instrument reading, and does not belong in the instrument group at all.

**The EIAC point matters for §4.7.** GU119 requires testing by an **EIAC**-accredited
company or laboratory, and calibration by a facility "accredited by DM". The
scoping document's `laboratories` registry assumes DM accreditation
(`authority = 'DM'`). For the IAQ modules the accrediting body is EIAC, and the
provider is often a testing *company* rather than a laboratory. The
`laboratories` table and its `authority` column will need to accommodate that —
which is an argument for the column existing, not against it, but it should be
settled before the accreditation gate ships.

---

## 6. Extraction hazards found in the documents themselves

Recorded because a human verifier should look at these first, and because
several would silently corrupt a seeded limit table.

**GU141 — the weights table contradicts the worked example.**
Table No.4 (page 12, normative) gives Formaldehyde 0.07, NO₂ 0.07, O₃ 0.04.
The worked example (page 20) uses Formaldehyde **0.06**, NO₂ **0.08**, O₃
**0.06**. Table 4's weights sum to exactly 1.00; the example's sum to 1.02.
The table is almost certainly right and the example wrong — but the example is
what a consultant will copy. Neither is encoded in the JSON, because weights are
a calculation input, not a limit. **Whoever implements the EIAQI calculation must
use Table No.4 and must know the example is inconsistent with it.**

**GU141 — a third, incompatible scoring scheme appears in Figure No.1** (page 14),
mapping IAQI/TCI bands to integer weightages 5, 4, 3, 2, 1, −4 and summing to a
"Total Weightage" scale of 10 / 9-8 / 7-6 / 5-3 / 2-1 / <1 labelled Good →
Worst Extreme. This cannot be reconciled with the §7.8 weighted summation that
produces the value 105 on page 20. **GU141 contains two mutually exclusive ways
to compute a final EIAQI and does not say which governs.** This alone makes
GU141 unfit to ship as a verdict-producing module without clarification from DM.

**GU119 Table 2 — ozone short-term is unreadable.** The cell prints as
`0.1 2 ppm` (two separate tokens at distinct x-positions, 0.1 at x≈356 and 2 at
x≈371). It is most likely `0.12 ppm`. **It is not recorded in the JSON at all** —
inventing 0.12 would be exactly the confident-wrong-number the brief forbids.
Every other ozone value in that row is present. Needs a human eye on page 33.

**GU119 Table 2 — total fungal counts prints `500 U/m3`**, not `CFU/m3` as in
Table 1. Recorded verbatim with the unit as printed and a note.

**GU119 Table 4 — Styrene is `100 ppm`** where every other individual VOC is in
µg/m³ in the tens-to-thousands. 100 ppm styrene is ~425,000 µg/m³, an
occupational-exposure figure sitting in a list of indoor-air-quality objectives.
Recorded verbatim at `confidence: "low"` with the anomaly stated. Do not
"correct" it without DM confirming.

**GU119 Table 4 — the PAH row's two units disagree by ~10 orders of magnitude**:
`0.012ng/m3 (1.2 × 10–4 ppm)`. The ng/m³ figure is encoded; the ppm figure is
preserved in `display` but not relied on.

**GU119 Tables 1 and 2 — bacterial and fungal counts have no averaging time**,
and their values are horizontally centred between the long-term and short-term
columns (x≈307 where those columns sit at x≈205 and x≈340). Which column they
belong to is genuinely not determinable from the layout. Recorded at
`confidence: "medium"` in the long-term set with the ambiguity noted.

**GU119 — PM10's short-term limit (100 µg/m³) is stricter than its long-term
limit (150 µg/m³)** in both tables. Unusual but printed clearly and consistently
in both; recorded as-is.

**GU119 Table 2 CO₂ short-term is a differential**: "700 ppm above outdoor air
levels". Judging it needs a simultaneous outdoor reference reading. No other
limit in any of these four documents does. `core/specs.py` has no concept of a
reference measurement, and this limit cannot be judged without one — it will
need either a second parameter on the evidence or an explicit NOT_ASSESSED.

**GU141 Table No.3 bands are disjoint intervals.** "20-21.9 **or** 26-28" cannot
be expressed as one `min_val`/`max_val` pair without silently including the
comfortable range in the discomfort band. Every thermal band is therefore split
into `*_lower_interval` and `*_upper_interval` limits. **`spec_limits` as
designed in migration 022 cannot represent a two-sided exclusion natively** — a
parameter whose acceptable region is a hole rather than an interval. Worth
knowing before another guideline needs it.

**Header column order was verified by coordinate, not by text order.** The
linearised text of GU141 Table No.2 and GU119 Tables 1-2 interleaves the
multi-line headers, and naive reading puts Carbon Monoxide in the wrong column.
Word x-positions were used to confirm the mapping
(PM₂.₅ → PM₁₀ → CO₂ → CO → VOCs → HCHO → NO₂ → O₃ for GU141). This is the single
most likely place for a silent transcription error, and it is worth re-checking
visually before seeding.

---

## 7. Are these "a numeric limit judged by a resolver"?

The §6 acceptance criterion is that each Phase 2 module should be *seed data plus
a limit table, with no Python change*.

| Guideline | Verdict |
|---|---|
| **GU119** | **Yes — and it is the only unqualified yes.** Table 1, 2 and 4 are max-value limits with an explicit "must not be exceeded". The parking CO pair is a textbook compliance-limit-plus-action-level. Two things need resolver support that does not exist today: the CO₂-above-outdoor differential, and the alternative-route rule at §9-8-9 (a TVOC failure is redeemed by passing all ten individual VOCs) — that is conditional logic across parameters, not a per-parameter bound. Expect a small, principled resolver extension, not a special case. |
| **GU38** | **No, and not for a fixable reason.** It has no environmental compliance limit at all (§3). Its value is a *classification* module — band the site, drive the control approach, track the daily checklist and pre-employment screening. The classification itself is a clean `resolve_limits`-shaped lookup and the seed data is genuinely just a table. But the thing being resolved is a risk band, not a verdict, and the product must not render it as one. Nearest analogue in the existing codebase is the risk-band logic in `calculations.py`, not `check_compliance`. |
| **GU141** | **No — it is a calculation engine, not a limit table.** Sub-index interpolation between breakpoints, a dominant-pollutant max for real time, a weighted summation for 8h/24h, and two mutually incompatible published methods for the final score (§6). The breakpoints are seed data; the index is code. Also, no compliance line is defined anywhere in the document, so even a perfect implementation cannot produce a verdict. **Would violate the no-Python-change criterion.** Recommend it is deferred behind GU119 rather than shipped alongside it, and that the method contradiction is raised with DM. |
| **GU10** | **No, and it is not really an instrument module.** Its binding requirement is delegated to ASHRAE 62.1 (§5). What remains — 1 m² per student, ≤25/≤30 students — is a register/floor-plan check judged by counting, closer to a Phase 4 checklist item than to a measured parameter. Four pages, one `shall`, no tables. Thin as a standalone SKU; more natural as a rider on GU119 for the education sector. |

**Suggested resequencing within the instrument group:** GU119 first and alone.
GU38 second, sold as classification and obligation tracking with the compliance
claim explicitly dropped. GU141 and GU10 deferred pending, respectively, a DM
clarification on the EIAQI method and pass line, and a decision on ASHRAE 62.1.

---

## 8. Other things noticed, not acted on

- **GU141 explicitly cites GU119** as a reference ("Technical Guidelines (119)
  for Indoor Air Quality for Healthy life"), and their limits do not agree — CO₂
  "Good" tops out at 600 ppm in GU141 while GU119's 8-hour compliance limit is
  800 ppm; PM₂.₅ "Good" is ≤12 µg/m³ in GU141 against a 35 µg/m³ 24-hour limit in
  GU119. These are not contradictions (a comfort band is not a legal ceiling) but
  a client monitored under both will see two different colours for one reading.
  Decision 6's "both verdicts, disagreement is a finding" posture handles this,
  but the UI copy needs to explain it or it will read as a bug.
- **GU119 Table No: 5** (page 35) sets the minimum number of sampling points by
  building area (1 per 500 m² under 3,000 m², rising to fixed counts, then 1 per
  1,200 m² above 30,000 m²). Not encoded as a limit — it governs survey design,
  not a result — but it is a genuine numeric requirement and would let the
  product check whether a submitted IAQ report has enough sampling points to be
  valid. That is a differentiated feature and cheap; worth a look once GU119
  ships.
- **GU119 appendix best-practice items** ("Keep relative humidity below 60%",
  "60cfm per occupant" for smoking lounges, page 41-ish) are advisory appendix
  content, not requirements, and are deliberately not encoded.
- **The `data/dm_guidelines/` directory contains other files** (`gu34`, `gu80`,
  `gu81`, `gu120`, `gu133`) from parallel work. `gu34_limits.json` currently
  parses but has a `specification_sets` structure that does not match the shape
  used here — it is not part of this task and has not been touched, but it will
  break a shared seeder.
