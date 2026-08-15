# Ambiguous issue dates — verification pass

Input: the 13 `confidence: "medium"` rows of `catalogue_editions.json`.
Output: `catalogue_editions_resolved.json`. Read from the PDFs on 2026-08-15.
`catalogue_editions.json` was **not** modified.

## 1. Result

| | Count |
|---|---|
| Rows examined | 13 |
| **Settled** (`resolution: day_first`, confidence `high`) | **7** |
| **Still unresolved** (confidence stays `medium`) | **6** |
| Rows whose `issued_on` **changed** | **0** |
| Rows whose **year** changed | **0** |

Settled: **GU66, GU46, GU99, GU120, GU38, GU42, GU43.**
Unresolved: **GU148, GU138, GU74, GU73, GU67, GU60.**

Every settled date confirmed the value already recorded. No date moved.

## 2. The headline finding: none of these 13 can move a year

This is worth stating plainly because it bounds the risk that put these rows on
the worklist. All thirteen dates are printed in a `dd/mm/yyyy` **or** `mm/dd/yyyy`
form — a four-digit year in the third position in every case. Swapping the first
two components changes the day and the month and **cannot change the year**. There
is no `yy` form and no `yyyy`-first form among the thirteen (the one document in
the corpus with a `yyyy`-first risk, GU72's `2019.10.08`, was already shown to give
the same answer both ways and is `high`).

`core/standards.py::citation_is_stale` compares `cited >= edition.current_issue.year`
— **years only**. So no reading of any of these thirteen dates can produce the
false "your citation is out of date" warning that §7.1 forbids. That risk is zero
for this set, resolved or not.

What a wrong reading *can* still do, in the same function:

```python
if sampled_at and sampled_at < edition.current_issue:
    return None
```

That is a full-date comparison. If the day/month is transposed, a certificate
sampled between the two candidate dates is silently mis-classified — the warning
is suppressed when it should fire, or fires when the certificate was correct at
the time of sampling. And the warning text itself prints
`edition.current_issue.isoformat()` to the client, so a transposed date is visible
in a message the client may take to their laboratory.

The one unresolved row where that window is materially wide is **GU67**: 9 June
2024 vs 6 September 2024, a three-month gap. The other five unresolved rows have
gaps of a few weeks to three months but none of them is currently in
`KNOWN_EDITIONS`, so nothing consumes them yet.

## 3. How the seven were settled

**GU66 — a history-log row with a component > 12.** The p.2 History Log has two
rows in one Date column: `20/08/2025 | 2.0` and `04/07/2026 | 3.0`. `20` cannot be
a month, so the column is dd/mm and the V3.0 row is 4 July 2026. The strongest
kind of evidence in the list, and it is inside the table that carries the date.

**GU46 — a superseded date with a component > 12, same field block.** Cover:
`Issue Date / 09/05/2024 / Superseded Issue Date / 19/02/2020`. `19` fixes the
block as dd/mm; the issue date is 9 May 2024.

**GU99 — same, in the footer block.** `Issue date: 04.10.2021 / V 2.0 /
Superseded Issue Date: 23.07.2020`, printed identically on 27 pages. `23` fixes
dd.mm; the issue date is 4 October 2021. `catalogue_editions_notes.md` §4 held
this at medium "on principle"; the two values sit on one line of one template
block, which is exactly the "another component > 12 fixes the convention" case, so
it is raised to `high`.

Incidentally, GU99 was listed as an *internal disagreement* row. It has none: its
cover carries no date field at all and every dated line in the file agrees. The
only issue was the day/month reading, and that is now settled.

**GU120 — the real internal disagreement, resolved for 11 March 2024.** See §4.

**GU38, GU42, GU43 — resolved from the file's own embedded timestamps.** All three
print `Issue Date 09/05/2024` with every component ≤ 12, a single History Log row
repeating the same string, and no month name anywhere in the file. Nothing printed
settles them. What settles them is that all three carry
`/CreationDate (D:20240709…)` and `<xmp:CreateDate>2024-07-09T…</xmp:CreateDate>`:
the PDFs were exported on **9 July 2024**. The month-first reading would date the
documents **5 September 2024** — two months *after* the file that contains the date
was created. A document cannot be exported bearing a future issue date, so
month-first is impossible and the date is 9 May 2024.

This is metadata rather than printed text, so it is flagged as such in each row.
It is still evidence internal to the individual file — not a corpus tendency — and
a verifier can check it in one command:

```
python -c "import pymupdf;print(pymupdf.open('GU38.pdf').metadata['creationDate'])"
```

GU46 carries the same timestamp and independently proves day-first from its
printed superseded date, which is a useful cross-check that the argument gives the
right answer where it can be tested.

## 4. GU120 and GU99 — the two "internal disagreement" rows

**GU120: believe 11th March 2024 (unchanged). The cover is wrong by one day.**

First, this was never a day/month problem. The cover prints
`Issue Date / 12/03/2024 / Superseded Issue Date / 29/09/2022`; `29` cannot be a
month, so the cover block is dd/mm, and the footer spells the same superseded date
as `29th Sep. 2022`. The cover therefore reads **12 March** 2024, not 3 December.

So the conflict is a plain one-day typo, 11th vs 12th March 2024:

- p.2 History Log, the row for the current version:
  `2.0 / 11th March 2024 / Bhayagshree Nagvenkar / Omar Gouda / Shifting to a new
  corporate template & content's grammar revision`
- document-control footer, all 7 pages:
  `Issue Date: 11th March 2024 / Version # (2.0) / Superseded Issue Date: 29th Sep. 2022`
- cover, once: `Issue Date / 12/03/2024`

**11th March 2024** is believed, on three grounds: it is written in words, so it
carries no format risk at all; it is the date DM entered in the History Log row for
the edition in force, which is the field of record for that edition; and it appears
eight times against the cover's one. The PDF was created 13 March 2024, consistent
with either. Month and year are certain, and no downstream check is sensitive at
one-day granularity, so this row is safe to ship. DM should still be asked to
correct the cover.

**GU99: no disagreement exists — settled, see §3.**

## 5. The six that stayed unresolved, and why

Each was opened in full and searched for every date-shaped string, every English
and Arabic month name, every ordinal, and every alternative rendering in headers,
footers, history logs, annexes and references. In each case the document genuinely
does not contain a disambiguator.

| No | Printed | Candidates | Why it cannot be settled |
|---|---|---|---|
| **GU148** | `03/06/2026` | 3 Jun / 6 Mar 2026 | Only date in the whole 26-page file. `Superseded Issue Date: New`; single history row repeats the same string; no month name anywhere. |
| **GU138** | `03/02/2025` | 3 Feb / 2 Mar 2025 | Same shape. `Superseded Issue Date: NEW`; one history row; no month name anywhere. |
| **GU74** | `12/09/2025` | 12 Sep / 9 Dec 2025 | Superseded `12/01/2021` is itself ambiguous; one history row; no month name. Both readings are chronologically consistent. |
| **GU73** | `06/04/2026` | 6 Apr / 4 Jun 2026 | Superseded `12/01/2021` ambiguous; one history row; no month name. |
| **GU67** | `06/09/2024` | 6 Sep / 9 Jun 2024 | Superseded `11/01/2021` ambiguous; one history row; no month name. |
| **GU60** | `08.01.2020` | 8 Jan / 1 Aug 2020 | Superseded is `April 2010` — a bare month with no day, so it fixes nothing. No History Log in this document, and the cover carries no date field. |

Timestamps did not rescue any of them. GU148, GU138, GU74, GU73 and GU67 were all
re-exported well after both of their candidate dates (GU74/GU73/GU67 in a single
bulk re-publication on 2026-06-09), and GU60's 2021 export postdates both. Nothing
excludes either reading.

Two temptations were declined, deliberately:

- **GU73's filename** ends `_V1.1-06-04-2026`. A filename is not evidence
  (`catalogue_editions_notes.md` §6 and `db/load_guidelines.py` rule 1), and it
  repeats the same ambiguous string in any case.
- **GU60's template.** GU60 uses the older dotted layout shared with GU99, and
  GU99's footer proves *that* template is dd.mm.yyyy. That is a different document.
  Per the standing rule, a convention proved elsewhere in the corpus is not proof
  about this file, and this is precisely the reasoning that produces a confident
  wrong date. GU60 stays unresolved.

The six keep the day-first value already recorded in `catalogue_editions.json` —
which is the sensible working assumption for a DM document — but they are recorded
as **unverified**, remain `medium`, and stay on the verification worklist. They can
only be closed by DM confirming the dates, and the question to put to DM is narrow:
for each of these six, is the printed date day-first? Nothing else about the rows is
in doubt.

## 6. What to do with this file

`catalogue_editions_resolved.json` is a side-car, not a replacement. Nothing was
written back to `catalogue_editions.json`, whose consumers are unaffected. Each row
carries `code`, `guideline_no`, `issued_on`, `previously`, `resolution`, `evidence`
(verbatim), `source_page`, `confidence`, plus two additions: `year_changed` (false
on all 13, for a machine-checkable assertion of §2) and `notes`.

If the seven settled rows are promoted, `catalogue_editions.json` drops from 13
medium rows to 6, and no value in it changes.
