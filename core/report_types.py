"""Report types — what analysis a certificate records.

A report type says what was *done* (a chemical analysis, a Legionella count). It
does **not** say which limits apply. That is the asset's job — see core/assets.py.

Scope briefly lived here and it was the wrong level. One asset carries several
report types over time (Gate Number 2 – GRP Water Tank has both microbiology and
Legionella certificates), so the report type varies while the thing being judged
does not. And a Legionella count of 900 CFU/L means one thing in a stored domestic
tank and another in an open animal moat — the asset decides, not the analysis.

The two scopes are defined here because they are shared vocabulary, but a scope is
resolved from `assets.scope`. They overlap heavily in parameter names — pH,
turbidity, ammonia, phosphate, E. coli, total coliforms and COD appear in both:

  lagoon      man-made / closed lagoons. Limits in core/constants.py
              (COMPLIANCE_LIMITS). Saved to `readings`, which feeds the alert
              engine, dashboards and monthly reporting.
  facilities  facilities-management assets — domestic water tanks, washroom
              lines, fountains/misting, animal water bodies. Governed by Dubai
              Municipality technical guidelines (GU44) and, for chemistry, by
              client-specific DM-derived limits. Saved to `lab_samples`.

Because the names overlap, matching a parameter is never sufficient to justify
applying a limit: judging a Safari Park animal moat against recreational-lagoon
limits would produce a confident, authoritative, wrong verdict. Scope is resolved
first; a limit is only ever drawn from that scope's set; unknown scope means the
result stays unassessed.

Built-in types live here in code. Organisations may add their own (migration 017);
either way a type carries no fields — they come from whatever the certificate
reports, so the document stays the source of truth.
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict

Scope = Literal["lagoon", "facilities"]

SCOPE_LAGOON: Scope = "lagoon"
SCOPE_FACILITIES: Scope = "facilities"
SCOPES: tuple[Scope, ...] = (SCOPE_LAGOON, SCOPE_FACILITIES)


class ReportType(TypedDict):
    key: str
    label: str
    builtin: bool


# Keys match `LabSample.report_type` emitted by ingestion/wimpey.py, so a parsed
# certificate can be matched against the type the user selected.
BUILTIN_REPORT_TYPES: list[ReportType] = [
    {"key": "lagoon", "label": "Lagoon Water Quality", "builtin": True},
    {"key": "chemistry", "label": "Chemical Analysis", "builtin": True},
    {"key": "microbiology", "label": "Microbiological Analysis", "builtin": True},
    {"key": "legionella", "label": "Legionella", "builtin": True},
]

# The legacy monthly-readings path, identified by report type rather than by asset.
# This is a bridge, not a counter-example to "scope lives on the asset": the lagoon
# product predates assets entirely and writes the fixed `readings` table, which the
# alert engine, dashboards and monthly reporting all read. Once lagoon certificates
# are attached to sampled assets carrying scope='lagoon', this constant goes away.
LEGACY_LAGOON_TYPE = "lagoon"

_BUILTIN_BY_KEY = {t["key"]: t for t in BUILTIN_REPORT_TYPES}


def get_builtin(key: str) -> Optional[ReportType]:
    return _BUILTIN_BY_KEY.get((key or "").strip().lower())


def is_known(key: str, custom: Optional[list[dict]] = None) -> bool:
    """True when this report type exists, built-in or organisation-defined."""
    if get_builtin(key):
        return True
    wanted = normalise_name(key).lower()
    return any(normalise_name(t.get("name") or "").lower() == wanted for t in custom or [])


def saves_to_readings(report_type: Optional[str], scope: Optional[str] = None) -> bool:
    """True when this data belongs in the fixed monthly `readings` table.

    `readings` has fourteen fixed columns and one row per site per month, so it
    cannot hold a certificate with an arbitrary parameter list; everything else
    goes to `lab_samples`/`lab_results`.

    Routing prefers the asset's scope when one is known, because the asset is what
    actually determines which specification applies. It falls back to the legacy
    lagoon report type only because that product predates assets — a lagoon reading
    entered by hand has no asset attached yet.
    """
    if scope in SCOPES:
        return scope == SCOPE_LAGOON
    return (report_type or "").strip().lower() == LEGACY_LAGOON_TYPE


def normalise_name(name: str) -> str:
    """Custom type names are compared case-insensitively and trimmed."""
    return " ".join((name or "").split()).strip()
