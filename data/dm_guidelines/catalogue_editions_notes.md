# DM guideline editions — issue dates read from inside the PDFs

Source: the 81 rows of `catalogue.json`. Output: `catalogue_editions.json` (80 entries).
Retrieved and read: 2026-08-15. Feeds `standards.issued_on` / `version` / `code` per
`DM_COMPLIANCE_SCOPING.md` §7.11 and `db/load_guidelines.py` rules 3 and 4.

Nothing here comes from a filename, a URL path, a portal `Date` field, or a
guideline number. Every value was read from the document itself — the cover page
or the document-control header/footer that DM repeats on every page — and each row
carries the printed line it came from in `source_quote`.

## 1. Resolution

| | Count |
|---|---|
| Catalogue rows | 81 |
| Editions resolved (`issued_on` + `version` + `code`) | **80** |
| Unresolved | 1 (GU78) |
| Confidence `high` | 67 |
| Confidence `medium` | 13 |
| Confidence `low` | 0 |
| Rows carrying `superseded_issued_on` | 48 |

All 80 obtainable documents yielded an issue date. There were no blank cover pages
and no document needed rendering to an image: every PDF in the corpus carries a
text layer, including the thirteen Arabic-only ones, whose covers extract as
scrambled but readable RTL fragments.

**The one failure: GU78** (Health protection against Ionizing Radiation). Its
document page 301-redirects to the DM home page and the catalogue has no
`source_url`. There is no file to open. It stays unresolvable here and needs
chasing with DM, as §7.11 already says.

## 2. Why 13 rows are `medium` and not `high`

Two distinct reasons, both recorded in each row's `notes`.

**Ambiguous numeric dates (11 rows).** Part of the corpus prints the issue date
numerically (`09/05/2024`) rather than in words (`4th May 2024`). The DM template
is day-first — proved repeatedly by dates whose first component exceeds 12
(`30/04/2024`, `22/07/2025`, `29/01/2025`, `23.07.2020`), by documents that print
both forms (GU120: `29/09/2022` = "29th Sep. 2022"; GU2's log rows `30/04/2024`
and `24/05/2024`), and decisively by GU85's history log, whose `3-1-2025` and
`30-09-2025` rows match its worded header dates "3rd Jan. 2025" and
"30 September 2025". But where **both** components of a particular date are ≤12,
that document alone cannot exclude a US-style reading, so the row is `medium`:

GU148, GU138, GU74, GU73, GU67, GU66, GU46, GU43, GU42, GU38, GU60.

If a human is verifying modules for sale (§7.1, decision 5), these eleven are the
dates to eyeball first. A month/day transposition here is exactly the error that
would fire a false `citation_is_stale`.

**Internal disagreement (2 rows).** GU120 and GU99 — see §4.

## 3. Codes recovered, and codes that contradict the catalogue

**Nine of the ten null codes are now filled** from the printed cover (the tenth is
GU78, which has no document):

| No | Printed code | Note |
|---|---|---|
| 148 | `DM-HSD-148-SS2` | no `GU` in the code |
| 146 | `DM-HSD-146-FL2` | no `GU` |
| 145 | `DM-HSD-145-WC` | no `GU`, no trailing digit |
| 143 | `DM-HSD-143-BTS` | no `GU` |
| 142 | `DM-HSD-GU142-MRC2` | |
| 141 | `DM-HSD-GU141-IAQI2` | |
| 118 | `DM-HSD-GU118-SSP2` | resolves the `SSP1V_4` filename ambiguity: it is `SSP2` |
| 15 | `DM-HSD-GU15-EIC2` | cover form; the page header prints the shorter `DM-HSD-GU15-EIC` |
| 13 | `DM-HSD-GU13-FCC2` | the listing's `HSD-GU13` was a filename artefact |

**Printed code contradicts `catalogue.json` — four cases, all catalogue-side
errors that would break citation matching:**

| No | Catalogue | Printed in the PDF |
|---|---|---|
| 124 | `DM-HSD-GU124-CMG` | `DM-HSD-GU124-LCM` |
| 29 | `DM-HSD-GU29-TGHS21` | `DM-HSD-GU29-TGHS1` |
| 93 | `DM-HSD-GU93-LAP` | `DM-HSD-GU93-LAP_E` |
| 19 | `DM-HSD-GU19-CSCM2` | `DM-HSD-GU19-CSMC2` (letters transposed) |

**GU10 / GU101 — confirmed from inside the document, not resolved.** The cover
*and* the page-2 header both print `DM-HSD-GU101-VSC2`. The number 10 appears
nowhere in the file. So the PDF is internally consistent and it is the *portal
listing* that says "(10)". This does not settle which is the typo — there is still
no GU101 row — but it removes the possibility that the code was merely a filename
mangling. §7.11's instruction to resolve it with DM stands, and the evidence to
put in front of DM is now: "your own document says GU101 throughout."

**GU86 contradicts itself — the worst find of the batch.** Its cover reads
`DM-HSD-GU86-BIOP2` / "General Requirements for Professional Use of Business to
Business 'B2B' Biocidal Products". Every inner page's document-control header
reads `Doc Ref: DM-HSD-GU29-TGHS2` and "Document title: Technical Guidelines for
Health Supplement" — GU29's identity, left in place when DM copied the file. The
cover code is what is recorded. Two consequences: a citation-matcher scanning the
body of GU86 will see GU29's code, and GU29's own current code is `-TGHS1`, so
`-TGHS2` in GU86 matches nothing real.

**Cosmetic code deviations recorded as printed:** stray space after `DM-HSD-` in
GU116 (`DM-HSD- GU116-CPCP2`), GU136 and GU13 (page header only); zero-padded
number in GU2 (`DM-HSD-GU02-SEPA2`). Normalise separators and spaces on both sides
before comparing, as `catalogue_notes.md` §5 already warns.

## 4. Documents whose cover disagrees with their own revision history

**GU120 — a real date conflict.** Cover prints `Issue Date 12/03/2024`. The history
log row for V2.0, and the footer of all seven pages, print `11th March 2024`.
Recorded as **2024-03-11**, per the rule that the current edition's history entry
governs; confidence `medium` and the cover's value is in `notes`. Whoever verifies
GU120 should decide explicitly, because one of the two dates is a typo by DM and
the difference is a day either side of a boundary nobody will notice until a
citation is judged stale.

**GU83 — version conflict, date agrees.** Cover and footers say `V 4.1`; its own
history log tops out at 3 (already flagged in §7.14). The issue date `9th June
2025` is consistent everywhere, so `issued_on` is safe; the version is not, and
GU83 should not be sold on its printed version string without asking DM.

**GU99 — day/month unprovable within the document.** Issue `04.10.2021`, superseded
`23.07.2020`. The superseded date proves the document uses dd.mm, but the issue
date's own components are both ≤12, so it is `medium` on principle.

**GU118 — a rendering glitch, not a conflict.** The cover's version field extracts
as `V 4 0.` (the glyphs are almost certainly `V 4.0`); the page header prints
`Version #: 4`, which is what is recorded.

**GU77 checks out** despite an initially odd parse: cover `V5` / 26th March 2026,
and the history log runs V3 (12 Mar 2023) → V4 (9 Jan 2025) → V5 (26 Mar 2026).

## 5. Version numbers the catalogue got wrong

Formatting differences (`V.3` vs `V 3.0`) are not listed — versions here are
verbatim as printed, so normalise before diffing. Three are **substantive**:

| No | Catalogue | Printed | Cause |
|---|---|---|---|
| 119 | V.2 | **V 4** | URL ends `_V2`; the document is V 4 (rule 1, exactly as warned) |
| 73 | V.1.1 | **V 2.0** | filename lagged a new edition |
| 50 | V.5 | **V 4.0** | filename claims a version the document does not |

Twelve versions that were null are now filled: GU148, GU145, GU143, GU135, GU118,
GU98, GU97, GU72, GU66, GU47, GU15, GU13.

## 6. Confirmation that the portal `Date` is worthless as an issue date

The rule in §7.11 holds everywhere it can be tested. Twenty-five documents have a
portal record date in a different **year** from their real issue date, and the
error runs in both directions:

- GU93: portal 2026-06-23, issued **2021-01-01** — five years out.
- GU133: portal 2026-06-09, issued **2025-03-25**; PDF stored under `/2024/08/`.
- GU44: portal 2026-07-27, issued **2025-08-19** — the case §7.11 cites, confirmed.
- **GU115: portal 2024-10-26, issued 2025-10-02** — the portal date is a year
  *earlier* than the document's own issue date. So `portal_document_date` is not
  even reliably an upper bound. Nothing can be inferred from it, in either
  direction.

Upload paths are equally meaningless: GU67's 2024 edition sits under `/2021/05/`,
GU132's 2024 edition under `/2026/01/`, GU115's 2025 edition under `/2026/01/`.
GU146's filename ends `10.5.26` while the document issued **2025-12-15**.

## 7. Arabic documents

Thirteen documents are Arabic-only; all thirteen yielded a date. Their covers use
`تاريخ الإصدار` (issue date), `رقم الإصدار` (version), `تاريخ الإصدار السابق`
(superseded), and `جديد` ("new") where there is no predecessor. Text extraction
scrambles the glyph order, so `source_quote` for these rows is a joined window of
the cover's date region rather than a clean sentence; the reading is given in
`notes`.

Two worth calling out:

- **GU47** (Boilers and Pressure Vessels — a priority Phase 3 certificate module)
  is `V 5.0`, issued **2026-01-20**, superseding 2024-04-30. It is the newest
  edition in the certificate group and the catalogue had no version for it at all.
- **GU72** prints `2019.10.08`. Both readings — as printed (yyyy.mm.dd) and
  reversed by RTL rendering (08.10.2019) — give **8 October 2019**, so the
  ambiguity is harmless here. It is `high`.

## 8. Fields written

Per row: `guideline_no`, `code`, `version`, `issued_on`, `source_page`,
`source_quote`, `confidence`, `notes`, plus two additions —
`superseded_issued_on` (ISO, present on 48 rows, for 022's column of that name;
omitted where the document prints "New"/"NEW", a bare "-", or a month with no day
as GU84, GU62 and GU60 do) and `listing_title` (the portal title, carried so the
four unnumbered scheme documents, whose `guideline_no` is null, can be matched
back to their catalogue row by code).

No title was found that differs materially from its listing, so no `title` field
is written. The only title discrepancy in the corpus is GU86's inner header
carrying GU29's title, described in §3.

`catalogue.json` was not modified.
