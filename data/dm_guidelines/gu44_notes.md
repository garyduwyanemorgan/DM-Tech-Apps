# GU44 — extraction notes

**Provenance warning.** These notes were written from `gu44_limits.json` and the
output of `scripts/validate_extractions.py`, **not** from the published PDF. The
agent that read the document hit a session limit after writing the JSON but
before writing its narrative notes, so its own commentary was lost. Everything
below is derived from the artefact it left. Where the artefact cannot answer a
question, this file says so rather than filling the gap.

Document: `DM-HSD-GU44-LCWS2`, V.6, issued 2025-08-19, English.
Extracted: **7 specification sets, 32 limits, 22 obligations.**

---

## 1. The one thing to re-check before anything else

The agent's last message before it was cut off reported **a conflict between a
table it labelled "Table (3)" and §14-4 of the document**, and said the table was
column-collapsed in text extraction so it needed visual confirmation. It was
instructed to record both readings rather than pick one — but the notes carrying
that detail were lost, and the JSON does not obviously flag which limit is
affected.

**Someone must re-open GU44 and find that conflict.** It is the single highest
-priority verification item here: an internal contradiction in the source
document means the affected parameter cannot be sold as a compliance module until
DM adjudicates it (§7.12). Candidates are the `confidence: low` rows —
`aerobic_bacterial_count`, `total_bacterial_count` (fountain/spa),
`copper_ion_ionization`, `silver_ion_ionization`,
`cooling_tower_emergency_free_chlorine_stage2`,
`tank_disinfection_maintained_chlorine`.

## 2. Settled: the lagoon limits do not come from GU44

Checked programmatically. **None** of the ten parameters in `core/constants.py`
`COMPLIANCE_LIMITS` — pH, DO, TSS, turbidity, COD, ammonia, phosphate, oil &
grease, E. coli, total coliforms — appears anywhere in the GU44 extraction. GU44
covers *Legionella*, bacterial counts, water temperatures and disinfectant
residuals.

This confirms the position taken in `db/seed_standards.py`: seeding
`lagoon_dm_water` with `standard_id` NULL was correct, and attributing those ten
limits to GU44 would have put a false citation on every lagoon report. **The
source document for the lagoon limits remains unidentified.**

## 3. Corroboration for the accreditation gate (§4.7)

Obligation 19 quotes §21-1 step 9: *"Collect a water sample from the tank and
send it to an **accredited laboratory** for analysis…"*. The requirement that
evidence come from an accredited laboratory is written into the guideline itself,
not merely inferred from DM's accreditation scheme. That supports building the
`laboratories` registry and the accreditation gate in Phase 1.

## 4. What cannot be seeded yet — 29 blocking findings

Run `python -m scripts.validate_extractions --file data/dm_guidelines/gu44_limits.json`
for the current list.

**27 are ambiguous inclusivity.** A bound was extracted but the document's
notation did not clearly say whether the bound itself passes, so `min_inclusive`
/ `max_inclusive` were left null rather than guessed. Migration 022 makes those
columns NOT NULL with no default precisely so this stops at the gate. **This is
the design working, not a defect** — but it is also the verification worklist,
and it is long: most of the disinfectant-residual and disinfection-process limits
are ranges written as "1 to 2 mg/l" or similar, where inclusivity is genuinely
unstated.

Practical note for whoever verifies: these cluster by set, and a single reading of
the residuals table and the disinfection-process section will likely resolve
twenty of them at once.

**2 are structural and need a decision, not just a reading:**

| Limit | Problem |
|---|---|
| `gu44_fountain_spa_water_system.legionella` | Bounded on neither side, and no `display`. Violates `spec_limits_bounded_check`. Most likely GU44 sets **no** *Legionella* limit for fountains and spas — in which case the row should be deleted, not fixed. Deleting is the honest outcome; an unbounded limit would silently pass every value. |
| `gu44_hot_warm_cold_water_temperature.small_water_heater_temperature` | Same. Probably a narrative requirement rather than a numeric limit. |

## 5. Advisory items

- **Unit spellings are inconsistent** — `MG/L` against `mg/l`, `cfu/l` against
  `cfu/ml`. A resolver matching a lab result by `parameter_key` will compare
  against whichever spelling it finds first, so these must be normalised before
  seeding. Note `cfu/l` vs `cfu/ml` is a genuine thousand-fold difference, not a
  spelling variant — check each against the document rather than normalising
  mechanically.
- **`legionella_growth_temperature_zone` (20–50 °C, marked `unassessable`)** is
  descriptive — it names the range in which *Legionella* proliferates. It is not
  a compliance limit and probably should not be a `spec_limits` row at all.
- Six rows carry `confidence: low`; see §1.

## 6. Obligations — the richest part of this extraction

22 obligations: 16 inspection, 4 sampling, 2 examination. This is more than any
other guideline extracted so far and makes GU44 a strong Phase 1 proof for the
obligations registry, which was the point of choosing it.

**One exposed a data-model gap.** Obligation 19 is triggered by an *event* —
sampling after a tank cleaning or disinfection — not by a schedule. §4.3's
`obligations` table models only `cadence_months` / `cadence_days` and cannot
express it. See the note added to §4.3 of the scoping document.
