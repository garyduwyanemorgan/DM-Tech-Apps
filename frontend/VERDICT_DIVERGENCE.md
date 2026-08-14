# Verdict divergence: the TypeScript UI versus the Python engine

**Status: investigation only. Nothing in this document has been changed.**
Aligning the TypeScript engines with Python would flip historical verdicts on
readings that have already been rendered, exported and in some cases sent to a
client. That is a decision for the product owner, not for a refactor. This
document exists so the decision can be made from facts rather than from a
parity-test failure discovered halfway through the `core/specs.py` consolidation
(§5 step 2 of `DM_COMPLIANCE_SCOPING.md`).

Scope: the three TypeScript verdict engines, measured against
`core/calculations.py:check_compliance`, which is the canonical implementation.
The eighth site, `ingestion/gates.py`, **has been fixed** — it now applies the
`<`/`≤` glyph printed on the laboratory's own certificate instead of discarding
it — so everything below is a front-end divergence.

The bounding fact first: **no limit VALUE differs anywhere.** All sites use
6.0/9.0, 4.0, 50, 75, 50, 5.0, 5.0, 10, 200, 1000, and
`frontend/src/constants.ts:10-21` is character-for-character identical to
`core/constants.py`. Every divergence below is an operator, a band, a formula or
a coverage gap.

---

## 1. Strictness — inclusive in TypeScript, strict in Python

Nine of the ten parameters. Only pH agrees, because it is inclusive on both
sides.

| Site | Code | Verdict at exactly the limit |
|---|---|---|
| `core/calculations.py:32` | `compliant = value < lim.max_val` | **breach** |
| `core/calculations.py:28` | `compliant = value > lim.min_val` (DO) | **breach** |
| `core/alert_engine.py:88-110` | `if r.tss >= 50: …` etc. | **breach** (agrees with Python) |
| `frontend/src/components/Dashboard.tsx:24-25` | `if (limit.max !== null && value > limit.max) return false` | **pass** |
| `frontend/src/components/ComplianceReport.tsx:290-291` | `const maxOk = limit.max === null \|\| val <= limit.max` | **pass** |
| `frontend/src/components/Chemistry.tsx:245-246` | `if (lim.max != null && val > lim.max) breach = true` | **pass** |

Concretely, a reading of TSS = 50.0, COD = 50.0, turbidity = 75.0,
ammonia = 5.0, phosphate = 5.0, oil & grease = 10, E. coli = 200,
total coliforms = 1000, or DO = 4.0 renders **green on screen and red in the
PDF** — same reading, same limit table, opposite verdict. Laboratories report on
exactly these round numbers routinely; this is live, not theoretical.

`ui/monitoring.py:47-65` is a fourth Python opinion but coincidentally agrees at
the bound: it highlights `v >= lim` (upper) and `v <= lim` (lower) as a breach.

**Flip if aligned to Python:** every stored reading with a value exactly equal to
one of the nine limits changes from WITHIN/pass to EXCEEDS/breach in
`Dashboard`, `ComplianceReport` and `Chemistry`, and the site traffic light for
that month goes green → red. No other value moves.

---

## 2. The pH margin formula differs structurally

- **Python — `core/calculations.py:23-25`:** two-sided, normalised by the range.
  ```python
  compliant  = lim.min_val <= value <= lim.max_val
  range_size = lim.max_val - lim.min_val                     # 3.0
  margin_pct = min(value - lim.min_val, lim.max_val - value) / range_size * 100
  ```
- **TypeScript — `Dashboard.tsx:29-35` and `ComplianceReport.tsx:294-301`:** both
  test `limit.max` **first**, so pH never reaches the lower-bound branch and the
  margin becomes `(9.0 − v) / 9.0`, ignoring the floor of 6.0 entirely.

pH 6.1 — one tenth above the floor, i.e. nearly out of specification:

| | margin | risk band |
|---|---|---|
| Python | `min(0.1, 2.9) / 3.0` = **3.3 %** | **HIGH** |
| UI | `(9.0 − 6.1) / 9.0` = **32 %** | **LOW** |

The pass/fail verdict for pH is the same on both sides; it is the **risk band and
the operator's early warning** that invert. A lagoon drifting acidic reads as its
safest at exactly the moment it is closest to breach.

This will surface during the `core/specs.py` consolidation as a parity failure
that looks like a bug in the new resolver and is not.

**Flip if aligned to Python:** no pass/fail change; every pH risk label and every
pH margin cell in the dashboard and the report changes, most dramatically at the
acidic end.

---

## 3. Four risk-band schemes

| Site | Bands | Applied to |
|---|---|---|
| `core/calculations.py:35-40` | `>30` LOW, `>10` MODERATE, else HIGH | PDF and API |
| `Dashboard.tsx:37-49` | `<20` WATCH, `<50` MODERATE, else LOW (`riskLabel`/`riskStyle`) | dashboard table |
| `ComplianceReport.tsx:310-322` | `<0` red, `<25` amber, else green (`marginColor`/`marginBg`) | report heat cells |
| `ui/monitoring.py:57-65` | `0.8 ×` / `1.2 ×` of the raw limit — not a margin percentage at all | Streamlit table |

Four different answers to "is this close to the edge?". Note the label sets do
not even match (LOW/MODERATE/HIGH versus LOW/MODERATE/WATCH/EXCEED), so
converging on one scheme also means choosing a vocabulary.

**Flip if aligned:** no pass/fail change; a margin of, say, 22 % moves between
MODERATE and WATCH and amber and green depending on which scheme wins. Cosmetic
in the data, not cosmetic to an operator triaging a portfolio.

---

## 4. Coverage gaps that look like agreement

- `Chemistry.tsx:69-78` (`TABLE_PARAMS`) judges **eight** parameters, silently
  omitting **E. coli** and **total coliforms** — the two microbiological
  parameters, and the ones a health regulator reads first.
- `ui/monitoring.py:41-46` judges **six**, omitting pH, oil & grease and both
  microbiological parameters.

A parameter that is never judged agrees with everything. Neither screen states
that it is showing a subset, so a clean Chemistry table is easily read as a clean
sample.

**Flip if the gaps are closed:** readings breaching only on E. coli or coliforms
begin showing EXCEEDS in Chemistry where the table is currently silent. Purely
additive — no existing row changes verdict.

---

## 5. The verdict string is split, and the bridge is fragile

- `core/calculations.py:71` emits `"NON-COMPLIANT"` (hyphen).
- The lab path and the database use `NON_COMPLIANT` (underscore) —
  `ingestion/gates.py:roll_up_status` → `ComplianceStatus.NON_COMPLIANT`,
  surfaced by `api_server.py:1942`.
- `frontend/src/lib/status.ts:52-53` papers over the split with a substring test:
  ```ts
  const nonCompliant =
    (reading.compliance ?? '').toUpperCase().includes('NON') ||
    (reading.failing_params?.length ?? 0) > 0
  ```

It works today, and it is fragile in a specific direction: **any future status
containing the substring `NON` renders red as a breach** — `NONE`,
`NON_APPLICABLE`, `NOT_ASSESSED` would be safe but `NON_ASSESSABLE` would not.
Given that the gate's own vocabulary already includes `NOT_ASSESSED` and
`INCOMPLETE`, a status that trips this is a plausible near-term addition, not a
hypothetical.

`INCOMPLETE` is worth checking separately: it contains no `NON` and no
`failing_params`, so a certificate that could not be assessed currently renders
**green**. That is the §7.4 failure mode — a confident wrong answer — and it is
independent of the strictness question.

**Flip if aligned:** none for existing data, provided the chosen canonical string
is applied to both producers at once.

---

## Recommended remediation order

Sequenced so each step is provable before the next one can hide a regression.

1. **Unify the verdict string, and give `INCOMPLETE` its own light.** No verdict
   flips, no historical data changes, and it removes the trap that would silently
   miscolour any status added during the rest of this work. Replace the substring
   test in `status.ts:53` with an explicit set membership. Do this first because
   it is the only item with zero blast radius.
2. **Close the coverage gaps** (`Chemistry.tsx:69-78`, `ui/monitoring.py:41-46`).
   Additive: it can only reveal breaches, never conceal one. Doing it before the
   strictness decision means the strictness change is measured over the full ten
   parameters rather than eight.
3. **Land `core/specs.py` and prove parity against `check_compliance`** over a
   value grid for all ten parameters *at exactly the bound*, per §5 step 2. Do
   not touch the TypeScript yet — this step establishes the reference answer that
   the following two steps are measured against. Expect the pH margin difference
   (§2) to appear here as a parity failure; it is a divergence to be decided, not
   a resolver bug.
4. **Decide strictness explicitly, then apply it in one commit across all three
   TypeScript engines.** This is the user's call, not an agent's, and it should be
   recorded as a numbered decision in `DM_COMPLIANCE_SCOPING.md` §8 alongside
   decision 6. Two defensible options:
   - *Strict everywhere* (matches Python, the PDF and now `ingestion/gates.py`):
     historically green readings at exactly the limit turn red on screen. Quantify
     the affected rows against production data before committing, and decide
     whether previously issued reports need reissuing or a note.
   - *Inclusive everywhere*: no screen changes, but the PDF and the API soften,
     and a value exactly at a DM ceiling would be reported as compliant. Harder
     to defend to a regulator and inconsistent with the certificate semantics
     the gate now applies, so it is the weaker option.

   Whichever is chosen, change **all** sites in a single commit. A partial
   alignment is worse than the current state, because today's divergence is at
   least uniform per surface.
5. **Unify the pH margin formula and the risk bands last.** They change no
   verdict, so they can safely follow, and after step 3 there is a resolver to
   host the single implementation instead of a fifth copy.

Throughout, honour the standing guardrails in §5: an asset with no scope resolves
to `None` and stays `NOT_ASSESSED`, never a default; `raw_extraction` and
`value_raw` stay verbatim.
