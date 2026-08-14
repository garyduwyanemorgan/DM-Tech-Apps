"""The specification resolver — which limits govern an asset, and the verdict.

DM_COMPLIANCE_SCOPING.md §5 step 2. Pure computation: same inputs → same
outputs, no Streamlit, no IO, no database. Rows are read by the db layer and
handed in; this module only decides. That is the same contract
core/calculations.py states in its own docstring, and it is what makes the parity
proof in tests/test_specs.py possible at all.

TWO FUNCTIONS, AND WHY THEY ARE SEPARATE
----------------------------------------
    resolve_limits(asset, spec_sets) -> SpecSet | None
    judge(result, limits)            -> COMPLIANT | NON_COMPLIANT | NOT_ASSESSED

Resolution can fail. That failure is a first-class answer, not an error and not
a reason to fall back: §7.4 names "applying one scope's limits to another
scope's asset and returning a confident wrong verdict" as the central risk of
the whole generalisation, and the assets.scope comment in migration 019 says
outright that NULL means "cannot be judged yet — never default it". So
resolve_limits returns None for an unclassified asset, for an ambiguous match,
and for anything it cannot decide, and judge(result, None) is NOT_ASSESSED. There
is no default specification set anywhere in this module, deliberately.

WHERE STRICTNESS COMES FROM
---------------------------
min_inclusive / max_inclusive, which migration 022 declares NOT NULL with no
DEFAULT. Never from the `display` string: 022 says display is OUTPUT ONLY and
must not be parsed back to recover an operator. The bound itself is the only
value where inclusivity is observable, and it is precisely where the eight
existing verdict implementations are known to disagree (§5 step-2 note: every
Python site is strict, all three TypeScript engines inclusive, for nine of the
ten lagoon parameters).

HOW A QUALIFIED VALUE IS JUDGED
-------------------------------
Migration 016 forbids coercing '<1' or 'Not Detected' to 0.0 — a below-LOQ
non-detect is regulatorily distinct from a measured zero — so nothing here ever
turns a qualifier into a number and judges it as though it were measured.

Instead a result is modelled as the INTERVAL of values it could truly be, and
compared against the interval the limit permits:

    the possible values lie wholly inside the permitted range  → COMPLIANT
    they lie wholly outside it                                 → NON_COMPLIANT
    they straddle the boundary                                 → NOT_ASSESSED

A plain measurement is the degenerate interval [v, v], so this reduces exactly to
the seeded min/max/inclusive semantics — that is the parity property. And it
gives the qualifier_rule 'bound' behaviour that 022's column comment specifies
without a second code path: '<4' against '< 100' is (-∞, 4), wholly inside, a
genuine PASS; '<4' against '< 1' straddles 1 and yields NOT_ASSESSED rather than
a fabricated FAIL. A value that falls between published bands is never snapped
to the nearer one; straddling is an answer.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping as _MappingABC
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

from core.assets import scope_of_asset

# ── Verdicts ─────────────────────────────────────────────────────────────────
# Underscored, matching ingestion/schema.py ComplianceStatus and the database.
# core/calculations.py::compliance_summary emits the hyphen form 'NON-COMPLIANT',
# bridged by a substring check in frontend status.ts:53; the §5 step-2 note calls
# that bridge fragile. It is not copied here.
COMPLIANT = "COMPLIANT"
NON_COMPLIANT = "NON_COMPLIANT"
NOT_ASSESSED = "NOT_ASSESSED"

VERDICTS: tuple[str, ...] = (COMPLIANT, NON_COMPLIANT, NOT_ASSESSED)

# The three values 022's spec_limits_qualifier_rule_check permits.
RULE_BOUND = "bound"
RULE_DETECT_FAILS = "detect_fails"
RULE_UNASSESSABLE = "unassessable"
QUALIFIER_RULES: tuple[str, ...] = (RULE_BOUND, RULE_DETECT_FAILS, RULE_UNASSESSABLE)

# Qualifiers as ingestion/wimpey.py::_split_value and lab_results.qualifier (016)
# record them. 'ND' carries no magnitude at all; the rest bound one side.
_ND = "ND"
_BELOW = ("<", "≤")
_ABOVE = (">", "≥")


# ── Intervals ────────────────────────────────────────────────────────────────
# Small and private. Both a limit and a result are ranges of possible values, and
# every verdict in this module is one containment test plus one overlap test.

@dataclass(frozen=True)
class _Interval:
    """A range on the real line. None on a side means unbounded there."""
    lo: Optional[float]
    hi: Optional[float]
    lo_inclusive: bool = True
    hi_inclusive: bool = True

    def is_empty(self) -> bool:
        if self.lo is None or self.hi is None:
            return False
        if self.lo > self.hi:
            return True
        return self.lo == self.hi and not (self.lo_inclusive and self.hi_inclusive)


def _lo_at_least(a: _Interval, b: _Interval) -> bool:
    """True when a's lower edge is at or inside b's lower edge."""
    if b.lo is None:
        return True
    if a.lo is None:
        return False
    if a.lo > b.lo:
        return True
    if a.lo < b.lo:
        return False
    # Same number: a is inside unless a admits the point and b does not.
    return b.lo_inclusive or not a.lo_inclusive


def _hi_at_most(a: _Interval, b: _Interval) -> bool:
    if b.hi is None:
        return True
    if a.hi is None:
        return False
    if a.hi < b.hi:
        return True
    if a.hi > b.hi:
        return False
    return b.hi_inclusive or not a.hi_inclusive


def _contains(outer: _Interval, inner: _Interval) -> bool:
    """Every value inner permits is a value outer permits."""
    return _lo_at_least(inner, outer) and _hi_at_most(inner, outer)


def _overlaps(a: _Interval, b: _Interval) -> bool:
    """The two ranges share at least one value."""
    lo, lo_inc = a.lo, a.lo_inclusive
    if b.lo is not None and (lo is None or b.lo > lo):
        lo, lo_inc = b.lo, b.lo_inclusive
    elif b.lo is not None and b.lo == lo:
        lo_inc = lo_inc and b.lo_inclusive

    hi, hi_inc = a.hi, a.hi_inclusive
    if b.hi is not None and (hi is None or b.hi < hi):
        hi, hi_inc = b.hi, b.hi_inclusive
    elif b.hi is not None and b.hi == hi:
        hi_inc = hi_inc and b.hi_inclusive

    return not _Interval(lo, hi, lo_inc, hi_inc).is_empty()


# ── The data 022 holds ───────────────────────────────────────────────────────

class SpecError(ValueError):
    """A specification row that cannot be used. Never raised for 'absent'."""


@dataclass(frozen=True)
class SpecLimit:
    """One row of spec_limits — what compliant means for one parameter.

    min_val/max_val carry ComplianceLimit's semantics: None is unbounded on that
    side. min_inclusive/max_inclusive are the operator, and have no default here
    for the same reason 022 gave them no DEFAULT in SQL — guessing inclusive
    silently passes a value sitting on a '< 50' ceiling, guessing exclusive
    silently fails one sitting on an inclusive bound.
    """
    parameter_key: str
    parameter_label: str
    min_val: Optional[float]
    max_val: Optional[float]
    min_inclusive: bool
    max_inclusive: bool
    display: str = ""
    unit: str = ""
    qualifier_rule: str = RULE_BOUND

    def __post_init__(self) -> None:
        if self.min_val is None and self.max_val is None:
            # spec_limits_bounded_check. A limit bounded on neither side judges
            # nothing and would silently pass every value put to it.
            raise SpecError(
                f"{self.parameter_key}: bounded on neither side. Such a limit "
                "passes every value; it does not belong in a specification set."
            )
        if (self.min_val is not None and self.max_val is not None
                and self.min_val > self.max_val):
            raise SpecError(
                f"{self.parameter_key}: min_val {self.min_val} exceeds max_val "
                f"{self.max_val} — spec_limits_range_check would reject this row."
            )
        if self.qualifier_rule not in QUALIFIER_RULES:
            raise SpecError(
                f"{self.parameter_key}: qualifier_rule {self.qualifier_rule!r} is "
                f"not one of {QUALIFIER_RULES}."
            )

    @property
    def interval(self) -> _Interval:
        """The values this limit permits. Strictness from the booleans only."""
        return _Interval(self.min_val, self.max_val,
                         self.min_inclusive, self.max_inclusive)


@dataclass(frozen=True)
class SpecSet:
    """One row of specification_sets plus its limits, keyed by parameter.

    organization_id None = built-in and shared; non-NULL = that organisation's
    override. applies_to_scope None means the set is not scope-restricted and,
    per 022's column comment, must be selected explicitly — resolve_limits will
    never reach for it on the strength of an asset's scope.
    """
    key: str
    label: str = ""
    applies_to_scope: Optional[str] = None
    organization_id: Optional[str] = None
    standard_id: Optional[str] = None
    limits: Mapping[str, SpecLimit] = field(default_factory=dict)

    def limit_for(self, parameter_key: str) -> Optional[SpecLimit]:
        """The limit for one parameter, or None when this set does not judge it.

        None, not a neighbouring parameter's limit and not a default: a set
        holding six of ten parameters must leave the other four unassessed. See
        verify_complete() in db/seed_standards.py on why a partial set is
        dangerous precisely because it does not fail loudly.
        """
        return self.limits.get((parameter_key or "").strip().lower())


def spec_limit_from_row(row: Mapping[str, Any]) -> SpecLimit:
    """Build a SpecLimit from a spec_limits row as PostgREST renders it.

    min_inclusive/max_inclusive are required. A row missing them is a row whose
    strictness nobody stated, and inventing one here would undo the reason 022
    dropped the DEFAULT.
    """
    for column in ("min_inclusive", "max_inclusive"):
        if row.get(column) is None:
            raise SpecError(
                f"{row.get('parameter_key')!r}: {column} is NULL. 022 declares it "
                "NOT NULL with no default because there is no safe guess; do not "
                "recover it from the display string."
            )
    return SpecLimit(
        parameter_key=(row.get("parameter_key") or "").strip().lower(),
        parameter_label=row.get("parameter_label") or row.get("parameter_key") or "",
        min_val=_as_float(row.get("min_val")),
        max_val=_as_float(row.get("max_val")),
        min_inclusive=bool(row.get("min_inclusive")),
        max_inclusive=bool(row.get("max_inclusive")),
        display=row.get("display") or "",
        unit=row.get("unit") or "",
        qualifier_rule=row.get("qualifier_rule") or RULE_BOUND,
    )


def spec_set_from_rows(set_row: Mapping[str, Any],
                       limit_rows: Iterable[Mapping[str, Any]]) -> SpecSet:
    """Build a SpecSet from a specification_sets row plus its spec_limits rows."""
    limits: dict[str, SpecLimit] = {}
    for row in limit_rows or ():
        lim = spec_limit_from_row(row)
        limits[lim.parameter_key] = lim
    return SpecSet(
        key=set_row.get("key") or "",
        label=set_row.get("label") or "",
        applies_to_scope=set_row.get("applies_to_scope"),
        organization_id=set_row.get("organization_id"),
        standard_id=set_row.get("standard_id"),
        limits=limits,
    )


def _as_float(value: Any) -> Optional[float]:
    """NUMERIC as PostgREST renders it — int, float or string. NULL stays None."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise SpecError(f"{value!r} is not a number") from None
    if math.isnan(out):
        raise SpecError("NaN is not a bound")
    return out


# ── Resolution ───────────────────────────────────────────────────────────────

def resolve_limits(asset: Optional[Mapping[str, Any]],
                   spec_sets: Sequence[SpecSet] = ()) -> Optional[SpecSet]:
    """The specification set governing an asset, or None.

    `spec_sets` is the candidate library, already read from the database by the
    caller — this module does no IO. An empty library therefore resolves to None,
    which is the correct answer and not a special case.

    None is returned, never a default set, when:

      * the asset is missing, is equipment, or carries no valid scope
        (core/assets.py::scope_of_asset). Migration 019: NULL scope is a real
        answer meaning "cannot be judged yet", and defaulting it "applies one
        scope's limits to the other scope's asset and returns a confident wrong
        verdict";
      * no candidate set matches;
      * more than one matches at the same precedence. Picking one arbitrarily is
        the same failure wearing a plausible face.

    The result must reach the user as a visible outcome — "cannot be judged —
    asset unclassified" — and never as a silent pass (§7.4).
    """
    scope = scope_of_asset(asset)
    if scope is None:
        return None

    org_id = (asset or {}).get("organization_id")
    wanted_key = ((asset or {}).get("spec_set_key") or "").strip() or None

    candidates = []
    for spec in spec_sets or ():
        # A set restricted to another organisation is not ours to apply. A
        # built-in (organization_id NULL) is available to everyone.
        if spec.organization_id is not None and spec.organization_id != org_id:
            continue
        # applies_to_scope NULL is not a wildcard — 022 says such a set must be
        # selected explicitly, so only a named key may reach one.
        if spec.applies_to_scope != scope:
            continue
        if wanted_key is not None and spec.key != wanted_key:
            continue
        candidates.append(spec)

    if not candidates:
        return None

    # An organisation's own override beats the built-in it narrows. Anything
    # still tied after that is ambiguous, and ambiguity resolves to None.
    overrides = [s for s in candidates if s.organization_id is not None]
    chosen = overrides or candidates
    if len(chosen) != 1:
        return None
    return chosen[0]


# ── Reading a result ─────────────────────────────────────────────────────────

def _result_fields(result: Any) -> tuple[Optional[str], Optional[float],
                                         Optional[str], Optional[float]]:
    """(parameter_key, value_num, qualifier, loq) from whatever was handed in.

    Accepts a LabResult-shaped object, a dict/row, or a bare number for the
    convenience of call sites that already hold one. A verbatim string is read
    with the same split ingestion/wimpey.py uses, so '<1' arrives as (1.0, '<')
    and 'Not Detected' as (None, 'ND') — never as 0.0, which migration 016
    forbids.
    """
    if result is None:
        return None, None, None, None
    if isinstance(result, bool):                       # not a measurement
        return None, None, None, None
    if isinstance(result, (int, float)):
        return None, _as_float(result), None, None
    if isinstance(result, str):
        num, qual = _split_value(result)
        return None, num, qual, None

    def get(name: str) -> Any:
        if isinstance(result, _MappingABC):
            return result.get(name)
        return getattr(result, name, None)

    key = get("parameter_key") or get("parameter") or None
    qualifier = get("qualifier")
    value = get("value_num")
    loq = get("loq")

    if value is None and qualifier is None:
        raw = get("value_raw")
        if isinstance(raw, str) and raw.strip():
            value, qualifier = _split_value(raw)

    return (
        (str(key).strip().lower() if key else None),
        (None if value is None else _as_float(value)),
        (str(qualifier).strip() if qualifier else None),
        (None if loq is None else _as_float(loq)),
    )


def _split_value(raw: str) -> tuple[Optional[float], Optional[str]]:
    """Split a printed result into (magnitude, qualifier). Never returns 0.0
    for a non-detect — 'Not Detected' has no magnitude and inventing one would
    be a claim the laboratory never made (016, ingestion/wimpey.py:178-193)."""
    text = (raw or "").strip()
    if not text:
        return None, None
    if re.match(r"(?i)^(not\s*detected|nd|absent|nil)\b", text):
        return None, _ND
    m = re.match(r"^([<>≤≥])\s*(-?\d+(?:\.\d+)?)$", text)
    if m:
        return float(m.group(2)), m.group(1)
    m = re.match(r"^(-?\d+(?:\.\d+)?)$", text)
    if m:
        return float(m.group(1)), None
    return None, None


# ── The verdict ──────────────────────────────────────────────────────────────

def judge(result: Any, limits: Optional[SpecSet | SpecLimit],
          parameter_key: Optional[str] = None) -> str:
    """COMPLIANT / NON_COMPLIANT / NOT_ASSESSED for one result against a limit.

    `limits` may be the SpecSet resolve_limits returned — in which case the
    parameter is taken from the result, or from `parameter_key` when the result
    is a bare number — or a single SpecLimit.

    NOT_ASSESSED whenever the answer is not provable: no limits resolved, the set
    does not judge this parameter, the result carries no readable value, or the
    values the result could truly represent straddle the boundary. None of those
    is a pass, and none of them is a fail.
    """
    if limits is None:
        return NOT_ASSESSED

    key, value, qualifier, loq = _result_fields(result)

    if isinstance(limits, SpecSet):
        wanted = (parameter_key or key or "").strip().lower()
        if not wanted:
            return NOT_ASSESSED
        limit = limits.limit_for(wanted)
        if limit is None:
            return NOT_ASSESSED
    else:
        limit = limits

    if qualifier:
        return _judge_qualified(limit, value, qualifier, loq)

    if value is None:
        # Nothing readable was reported. Silence is not compliance.
        return NOT_ASSESSED

    return _verdict(limit, _Interval(value, value, True, True))


def _verdict(limit: SpecLimit, possible: _Interval) -> str:
    """Compare the values a result could be against the values a limit permits."""
    permitted = limit.interval
    if _contains(permitted, possible):
        return COMPLIANT
    if not _overlaps(permitted, possible):
        return NON_COMPLIANT
    # Neither proved. The value falls across a published boundary, and snapping
    # it to the nearer side would invent a verdict the evidence does not carry.
    return NOT_ASSESSED


def _judge_qualified(limit: SpecLimit, value: Optional[float],
                     qualifier: str, loq: Optional[float]) -> str:
    """Judge a non-numeric laboratory result per the limit's qualifier_rule.

    The three rules are 022's, verbatim in intent:

    unassessable — never judge a qualified value on this parameter. The honest
        choice where the guideline does not say.
    detect_fails — presence alone is the breach, so a non-detection passes and
        any quantified value fails. '<X' is treated as a non-detection, matching
        ingestion/gates.py:126 where qualifier '<' and 'ND' both satisfy a
        printed 'Zero'/'Absent' requirement; 022 requires this module to stay
        consistent with that gate.
    bound — judge by the range the qualifier actually bounds. '<X' means the
        true value lies below X, so it passes only when the whole of that range
        passes; where the range straddles the limit it proves nothing and the
        answer is NOT_ASSESSED, not a fabricated FAIL.
    """
    if limit.qualifier_rule == RULE_UNASSESSABLE:
        return NOT_ASSESSED

    if limit.qualifier_rule == RULE_DETECT_FAILS:
        if qualifier == _ND or qualifier in _BELOW:
            return COMPLIANT
        if qualifier in _ABOVE or value is not None:
            return NON_COMPLIANT
        return NOT_ASSESSED

    # RULE_BOUND
    if qualifier == _ND:
        # No magnitude was reported. When the certificate states a limit of
        # quantitation, that is a real upper bound on the true value and can be
        # judged; otherwise fall back on the one thing a non-detection does
        # establish — that nothing was found — which satisfies a ceiling but
        # says nothing at all about a floor.
        if loq is not None:
            return _verdict(limit, _Interval(None, loq, True, False))
        if limit.min_val is None:
            return COMPLIANT
        return NOT_ASSESSED

    if value is None:
        return NOT_ASSESSED

    if qualifier in _BELOW:
        # '<X' → (-∞, X); '≤X' → (-∞, X].
        return _verdict(limit, _Interval(None, value, True, qualifier == "≤"))
    if qualifier in _ABOVE:
        return _verdict(limit, _Interval(value, None, qualifier == "≥", True))

    # An unrecognised qualifier is not a licence to ignore it and judge the bare
    # number: whatever it meant, it modified the value.
    return NOT_ASSESSED
