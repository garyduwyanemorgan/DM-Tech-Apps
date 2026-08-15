"""The escalation reason a user reads, pinned string by string.

core/alert_engine.py used to carry its own inline copy of all ten limits — the
second of the eight verdict implementations DM_COMPLIANCE_SCOPING.md §5
catalogues. It now judges through core/specs.py.

The verdicts were never in doubt: the copy agreed with core/calculations.py on
every value and every operator. What a differential run over 632 readings DID
catch was the wording drifting — pH gained "pH Units" and E. coli became
"CFU/100mL", because SpecLimit carries the limit's real unit while the old
messages used shorter ones.

That is the failure mode of a consolidation: the logic is right and the output
changes underneath somebody. These tests exist so the next person to touch it
finds out immediately.
"""
from __future__ import annotations

import inspect

import pytest

from core.alert_engine import _check_compliance_breach
from core.models import WaterReading

_FIELDS = {p.name for p in inspect.signature(WaterReading).parameters.values()}


def reading(**over):
    base = dict(timestamp=None, ph=7.5, do=8.0, tss=10, turbidity=10, cod=10,
                ammonia=1.0, phosphate=1.0, oil_grease=1, ecoli=10,
                total_coliforms=10, chla=1, phycocyanin=1, salinity=45,
                water_temp=25)
    base.update(over)
    return WaterReading(**{k: v for k, v in base.items() if k in _FIELDS})


@pytest.mark.parametrize("field,value,expected", [
    ("ph", 5.9, "pH 5.9"),
    ("ph", 9.1, "pH 9.1"),
    ("do", 4.0, "DO 4.0 mg/L"),
    ("tss", 50, "TSS 50 mg/L"),
    ("turbidity", 75, "Turbidity 75 NTU"),
    ("cod", 50, "COD 50 mg/L"),
    ("ammonia", 5.0, "Ammonia 5.0 mg/L"),
    ("phosphate", 5.0, "Phosphate 5.0 mg/L"),
    ("oil_grease", 10, "O&G 10 mg/L"),
    ("ecoli", 200, "E. coli 200 CFU"),
    ("total_coliforms", 1000, "Coliforms 1000 CFU"),
])
def test_breach_message_is_unchanged(field, value, expected):
    assert _check_compliance_breach(reading(**{field: value})) == expected


@pytest.mark.parametrize("field,value", [
    ("ph", 6.0), ("ph", 9.0),        # inclusive both ends
    ("do", 4.1), ("tss", 49), ("turbidity", 74), ("cod", 49),
    ("ammonia", 4.9), ("phosphate", 4.9), ("oil_grease", 9),
    ("ecoli", 199), ("total_coliforms", 999),
])
def test_compliant_values_report_no_breach(field, value):
    assert _check_compliance_breach(reading(**{field: value})) is None


def test_precedence_is_preserved():
    """It returns the FIRST breach, and which one reaches the user matters.

    COMPLIANCE_LIMITS is ordered and the loop follows it, which reproduces the
    inline copy's if-chain exactly. A dict that stopped being ordered, or a
    resolver that iterated its own limits instead, would change the escalation
    reason without changing any verdict.
    """
    everything = reading(ph=5.0, do=1.0, tss=999, turbidity=999, cod=999,
                         ammonia=99, phosphate=99, oil_grease=99,
                         ecoli=9999, total_coliforms=99999)
    assert _check_compliance_breach(everything) == "pH 5.0"
    # With pH back in range, DO is next in the chain.
    assert _check_compliance_breach(
        reading(do=1.0, tss=999, ecoli=9999)) == "DO 1.0 mg/L"
    # And with both fine, TSS.
    assert _check_compliance_breach(reading(tss=999, ecoli=9999)) == "TSS 999 mg/L"


def test_a_clean_reading_has_no_breach():
    assert _check_compliance_breach(reading()) is None
