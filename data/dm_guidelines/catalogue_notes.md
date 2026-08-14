# DM technical guidelines catalogue — extraction notes

Source: <https://www.dm.gov.ae/municipality-business/technical-guidelines-list/>
Retrieved: 2026-08-14. Output: `catalogue.json` (81 entries).

Feeds `guideline_modules` / `standards` per DM_COMPLIANCE_SCOPING.md §4.1 and §4.5.

## 1. Count retrieved vs count claimed

**The page states no total.** It renders one HTML `<table>` under the heading
"Health and Safety Technical Guidelines / Below are the Health and Safety Technical
Guidelines", with a single `Documents` column, no pagination, no filters and no
"showing N of M" counter. There is therefore nothing to reconcile a retrieved count
against other than the markup itself.

| Measure | Count |
|---|---|
| `<tr>` rows in the table (excluding header) | 81 |
| `<a href>` document links | 81 |
| Rows with no link (would be unreachable) | 0 |
| Entries written to `catalogue.json` | **81** |
| Of which carry a guideline number `(nn)` in the title | 77 |
| Of which are unnumbered scheme/requirement documents | 4 |

So the retrieval is complete against what the page publishes: 81 of 81.

> A first-pass WebFetch summary of this page reported "48 technical guidelines".
> That figure is wrong — it is the summarising model truncating a long list, not a
> statement by Dubai Municipality. Do not use it. The raw HTML has 81 rows.

Resolution rates across the 81 entries:

| Field | Populated | Null |
|---|---|---|
| `source_url` (direct PDF) | 80 | 1 |
| `code` | 71 | 10 |
| `version` | 68 | 13 |
| `issued_on` | 0 | 81 |
| `language` | 81 | 0 |

## 2. `issued_on` is null for every entry — by design

No guideline page publishes an issue date. Each document page shows a `Date` field,
but that is the CMS record date (upload/last modification): GU44 shows `27/07/2026`
while its in-force edition is V.6, which the scoping document records as issued
2025-08-19. The two are unrelated.

Rather than discard the value, it is carried in a separate `portal_document_date`
field (ISO) and repeated in `notes`. **Do not load `portal_document_date` into
`standards.issued_on`.** Real issue dates have to come from the PDF cover pages,
which is the extraction agents' job, not the catalogue's.

## 3. Guideline with no retrievable document

| No | Title | Problem |
|---|---|---|
| 78 | Health protection against Ionizing Radiation | `https://www.dm.gov.ae/documents/hsd-gu78-2020/` returns **301 → `https://dm.gov.ae/`**. The document page no longer exists; the list page still links it. No PDF, no code, no version. |

GU78 is a Phase 2 module in §6, so this needs chasing — via the DM site search, or
by asking DM directly. It is the only dead link in the table.

## 4. Guidelines with no document code visible

The code is only ever visible in the published PDF's filename; it is never printed
as a separate metadata field. Ten entries therefore have `code: null`. Per the brief,
none of these were guessed.

**Filename simply carries no code (6):** GU148 Safe Storage, GU146 Safe Forklifts
Operations, GU145 Water Coolers and Dispensers, GU143 Safe Back to School, GU142 Mold
Remediation and Control, GU141 EIAQI. All six are recent uploads (2025-10 onward)
whose filenames are plain English titles. The code may well be printed on the PDF
cover page — GU142 and GU141 are already being opened by the extraction agents, so
their codes should be back-filled from that work rather than re-derived here.

**Ambiguous or malformed (3):**

| No | Filename fragment | Why null |
|---|---|---|
| 118 | `...-Dubai-DM-HSD-GU118-SSP1V_4` | Cannot tell whether the code is `DM-HSD-GU118-SSP1` at version 4, or `DM-HSD-GU118-SSP1V`. Every other file separates the version as `_V<n>`; this one does not. |
| 15 | `13-GU15-EIC2_Technical-Guidelines-...` | No `DM-HSD-` prefix, and an unexplained leading `13-`. |
| 13 | `...-for-Fitness-Centers-Men-and-Women-HSD-GU13` | `HSD-GU13` only: no `DM-` prefix and no subject abbreviation. |

**Dead page (1):** GU78, above.

## 5. Code formats that break the `DM-HSD-GU<n>-<abbrev>` pattern

Five deviations, all real and all recorded exactly as printed:

1. **GU10 — number/code conflict.** Listed as "Technical Guidelines (10) for
   Ventilation in School Classes", but the PDF is
   `DM-HSD-GU101-VSC2_TECHNICAL-GUIDELINES-FOR-VENTILATION-IN-SCHOOL-CLASSES_-V1`.
   `guideline_no` is taken from the list page (10) and `code` from the file
   (`DM-HSD-GU101-VSC2`). One of the two is a DM typo, and there is no GU101 row in
   the table to disambiguate. **This one matters** — GU10 is a Phase 2 module and a
   laboratory/instrument citation would be matched against whichever string is real.
   Resolve from the PDF cover page before shipping the module.
2. **`DM-HSD-S1`, `DM-HSD-S2`, `DM-HSD-S3`** — the Lifeguard Scheme and the two OHS
   certification schemes use an `S<n>` series with no guideline number and no subject
   abbreviation. `guideline_no` is null for these.
3. **`DM-HSD-SP06-NOPHSA2`** — "Technical Requirements for No Objection for
   Practicing Health and Safety Activities" uses an `SP<n>` series. Also unnumbered.
4. Underscore vs hyphen after `DM-HSD` is inconsistent across files
   (`DM-HSD-GU44-...` vs `DM-HSD_GU97_...` vs `DM-HSD-GU62_AG2_...`). Codes in
   `catalogue.json` are **normalised to hyphens** so they compare cleanly. If lab
   citations are matched against these strings, normalise separators on both sides.
5. Abbreviation reuse: `PPEHP2` is used for both GU98 (Hand Protection) and GU65/GU60
   (Head / Hearing Protection). The abbreviation alone is not a key — always match on
   the full code.

## 6. Language

13 documents are Arabic. Two confidence levels, distinguished in `notes`:

**Explicitly stated "Arabic only" on the page or in the list title (7):**
GU145, GU143, GU135, GU130, GU125, GU124, GU118.

**Inferred from an Arabic-script document title/filename, with no explicit statement (6):**
GU115, GU97, GU90, GU72, GU47, GU29. These are flagged in `notes`; the English title
on the list page makes them look bilingual, but the only published file is Arabic. If
`language: "both"` matters commercially, these six need a human to confirm — no entry
in the catalogue is set to `"both"` because the site never publishes a document twice.

**§7.2 of the scoping document is out of date.** It names GU17, GU124, GU125, GU129,
GU130 as the known Arabic-only set. Verified against the live site:

- GU124, GU125, GU130 — confirmed Arabic.
- **GU17 — now English.** `DM-HSD-GU17-DW2_Technical-Guidelines-for-Quality-of-Unbottled-Drinking-Water_V1`.
- **GU129 — now English.** `DM-HSD-GU129-HH_Technical-Guidelines-for-Health-and-Safety-Requirements-in-Holiday-Homes_V1`.
- Ten Arabic documents §7.2 does not mention: GU145, GU143, GU135, GU118, GU115,
  GU97, GU90, GU72, GU47, GU29. Four of those ten are explicit on the page
  (GU145, GU143, GU135, GU118); the other six are the inferred cases above.

That is good news for Phase 2 — GU17 was called out as an Arabic-only obstacle and
is not one any more. **But GU47 (Boilers and Pressure Vessels) is Arabic**, and it is
one of the three priority Phase 3 certificate modules. Budget translation for it.

## 7. Coverage against scoping §6

Every guideline named in §6 exists on the list page. Nothing in the build order is
missing from the source.

Phase distribution of the 81 catalogue entries:

| Phase | Entries |
|---|---|
| 1 | 1 |
| 2 | 13 |
| 3 | 6 |
| 4 | 2 |
| 5 | 19 |
| 6 | 21 |
| null (not in §6) | 19 |

The 19 not named in §6, i.e. candidate SKUs the build order has not yet placed:

GU148 (Safe Storage), GU143 (Safe Back to School), GU138 (Helium Gas Cylinder Safety),
GU132 (Food Contact Materials), GU122 (Tobacco/Smoking Supplies Permits), GU117
(Fragrance Products), GU116 (Cosmetic & Personal Care Products), GU115 (Handmade
Consumer Products), GU107 (Consumer Products Storage), GU100 (Consumer Products
Import/Re-export), GU86 (B2B Biocidal Products), GU82 (Biocides), GU73 (Safe Use of
Ladders), GU70 (Smoking Areas Permits), GU62 (Acetylene Generators), GU53 (LPG
Cylinders), GU30 (Detergents), GU29 (Health Supplements), GU18 (Consumer Products
E-Commerce).

Two clusters stand out. The **consumer-product family** (132, 117, 116, 115, 107, 100,
86, 82, 30, 29, 18) is a laboratory-evidenced group that would reuse the Phase 2
resolver with no new primitive — but it sells to traders and importers, not to FM
contractors, so it is a different market rather than an extension of the current one.
The **plant items** GU62 (Acetylene Generators) and GU53 (LPG Cylinders) are the same
shape as Phase 3: periodic third-party examination with an expiry, sold to the same
buyer. They look like the cheapest additions to the certificate primitive once it
exists.

## 8. `evidence_type` — how it was assigned

Classified from the published title and page text only; no PDFs were opened for this.
Distribution: checklist 35, laboratory 19, certificate 12, competency 7, instrument 5,
unknown 3.

Judgement calls worth reviewing, all noted per-row:

- **Permits** (GU122, GU121, GU70) and **plan approval** (GU34) are typed
  `certificate` because they are a dated document with an expiry, which is the §4.4
  primitive — but they are issued by DM itself, not by a third-party examining body.
  If `certificates` grows an issuer-type column, these are the rows that need it.
- **PPE** (GU98, GU97, GU65, GU61, GU60, GU59) is typed `checklist`. §6 says PPE
  should ride on `core/inventory.py` as an issuance-and-inspection register rather
  than get its own module, so this type is a placeholder, not a design decision.
- `unknown` (3): GU138 Helium Gas Cylinder Safety, GU100 Consumer Products Import and
  Re-export, GU42 Paint Spray Booths. GU42 is probably LEV thorough examination —
  i.e. `certificate` — but the title does not say so and it was not guessed.

## 9. Site structure — for whoever automates the refresh

- **The list is server-rendered.** No JS, no XHR, no API. `curl` the page and parse
  the single `<table>`; that is the whole job. Do not reach for a headless browser.
- **The WordPress REST API is closed.** `/wp-json/wp/v2/pages/7611` (this page's ID,
  present in the HTML `<head>`) returns `401 rest_not_logged_in`. Scraping is the only
  route.
- **Two hops per document.** The table links a `/documents/<slug>/` page; the PDF URL
  lives only on that page. 81 fetches. The site tolerated sequential requests at
  ~0.3 s with no rate limiting or bot challenge.
- **Slugs are not derivable.** Three different conventions coexist —
  `hsd-gu44/`, `hsd-gu98-2020/`, `technical-guidelines-148-for-safe-storage/`, plus
  one-off oddities like `copy-of-hsd-gu13-2020-...-arabic-only/` and
  `dm-hsd-gu132-fcm2_technical-guidelines-for-food-contact-materials/`. **Never
  construct a document URL from a guideline number.** Always re-read the table.
  `page_url` is stored per entry for exactly this reason.
- **Host is inconsistent.** 17 of the 81 links use bare `https://dm.gov.ae/...`, the
  rest `https://www.dm.gov.ae/...`. Both resolve. Normalise before diffing runs.
- **PDFs are on a separate host**, `https://dmpmedia.dm.gov.ae/uploads/<yyyy>/<mm>/<filename>.pdf`.
  The `<yyyy>/<mm>` path is the upload date and **does not track the version** — GU44
  V.6 sits under `/2022/10/`, GU115 V.1.0 under `/2026/01/` while its page date reads
  2024-10-26. Do not read meaning into that path.
- **Arabic filenames are un-encoded UTF-8 in the href.** Percent-encode before
  requesting, and store as UTF-8.
- Useful stable markers for a parser: the heading string
  `Below are the Health and Safety Technical Guidelines`, and on each document page
  the literal sequence `|Size| … |Type|PDF|Date|dd/mm/yyyy|Download|Preview|<filename>|`,
  which is where filename, size and record date are read from.
- **A refresh should diff on `file_label`, not on the title.** The version lives in the
  filename, so a new edition changes the filename while the list-page title usually
  stays identical. Titles also carry typos that may be silently corrected
  ("Safet Requirements" in GU145 as published).

## 10. Fields in `catalogue.json` beyond the requested schema

Two were added because dropping them would lose the evidence behind the extraction:

- `page_url` — the `/documents/` page, since PDF URLs move and slugs are not derivable.
- `file_label` — the exact filename string as printed on the page. Every `code` and
  `version` in this file was read from it, so it is the audit trail: any disputed code
  can be re-checked without re-fetching. It is also the right diff key on refresh.
- `portal_document_date` — see §2. Deliberately not `issued_on`.
