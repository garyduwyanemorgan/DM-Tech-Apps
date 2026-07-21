"""Known editions of the standards laboratories cite, so we can spot a stale one.

A certificate names the guideline its verdicts were judged against. That citation
can go stale: Dubai Municipality reissues a guideline, the laboratory's LIMS
template keeps printing the old edition, and certificates continue to cite a
superseded document. The limits usually survive a reissue unchanged — so the
numbers stay right while the citation does not — but it is exactly the sort of
thing a regulator queries, and the client is the one who has to answer.

Real example this was built from: every Wimpey certificate in the sample set,
including ones sampled in April and June 2026, cites
``DM-HSD-GU44-LCWS2; 2024``. The published guideline is V6, issued 19 August
2025, superseding the edition of 17 December 2024. So certificates issued nearly
a year after the reissue still name the old edition.

Facts here were read directly from the published PDF at dm.gov.ae, not inferred.
Only add an entry when you have the document in front of you: a wrong "your
citation is out of date" warning is worse than none, because it sends the client
to argue with their laboratory over nothing.
"""
from __future__ import annotations

from datetime import date
from typing import NamedTuple, Optional


class StandardEdition(NamedTuple):
    code: str
    title: str
    current_version: str
    current_issue: date          # when the edition in force was issued
    superseded_issue: date       # the edition it replaced
    source_url: str


# Keyed by the document code exactly as laboratories print it.
KNOWN_EDITIONS: dict[str, StandardEdition] = {
    "DM-HSD-GU44-LCWS2": StandardEdition(
        code="DM-HSD-GU44-LCWS2",
        title="Technical Guidelines for Legionella Control in Water System",
        current_version="V.6",
        current_issue=date(2025, 8, 19),
        superseded_issue=date(2024, 12, 17),
        source_url=(
            "https://dmpmedia.dm.gov.ae/uploads/2022/10/"
            "DM-HSD-GU44-LCWS2_Technical-Guidelines-for-Legionella-Control-in-"
            "Water-System_V6-002.pdf"
        ),
    ),
}


def get_edition(code: str) -> Optional[StandardEdition]:
    return KNOWN_EDITIONS.get((code or "").strip().upper())


def citation_is_stale(code: str, cited_year: str,
                      sampled_at: Optional[date] = None) -> Optional[str]:
    """Return a warning when a certificate cites a superseded edition, else None.

    Deliberately conservative — silence unless all three hold:

      * we actually hold the edition facts for this code
      * the cited year is a readable four-digit year
      * that year is earlier than the year the edition in force was issued

    A citation matching or postdating the current edition is fine, and an
    unparseable or absent year yields nothing rather than a guess. When the
    sampling date is known and predates the reissue, the old citation was correct
    at the time and is not flagged — the certificate is not wrong, it is simply
    old.
    """
    edition = get_edition(code)
    if not edition:
        return None

    year = (cited_year or "").strip()
    if not (len(year) == 4 and year.isdigit()):
        return None
    cited = int(year)

    if cited >= edition.current_issue.year:
        return None
    if sampled_at and sampled_at < edition.current_issue:
        return None

    when = f" (sampled {sampled_at.isoformat()})" if sampled_at else ""
    return (
        f"[source] certificate cites {edition.code} edition {cited}, but "
        f"{edition.current_version} was issued {edition.current_issue.isoformat()}, "
        f"superseding the edition of {edition.superseded_issue.isoformat()}{when}. "
        "The limits may be unchanged, but the citation is out of date — worth "
        "raising with the laboratory before this reaches the regulator."
    )
