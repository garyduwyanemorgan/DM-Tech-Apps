"""Report types, asset classes, and where specification scope actually lives.

The safety property under test is that **scope belongs to the asset, not to the
report type**. Scope decides which specification set a result may be judged
against, and the two sets overlap heavily in parameter names — pH, turbidity,
ammonia, phosphate, E. coli, total coliforms and COD appear in both. So matching
a parameter name is never sufficient to justify applying a limit: judging a Dubai
Safari Park animal moat against recreational-lagoon limits would produce a
confident, authoritative, wrong verdict.

Scope lived on the report type briefly and that was the wrong level. One asset
carries several report types over time — "Gate Number 2 – GRP Water Tank" has both
microbiology and Legionella certificates — so the report type varies while the
thing being judged does not. Migration 019 moved it to `assets.scope`.

Pure unit tests: no database, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import api_server  # noqa: E402
from core.assets import (  # noqa: E402
    ASSET_CLASSES, ASSET_TYPES, CLASS_EQUIPMENT, CLASS_SAMPLED,
    class_of, find_type, get_asset_type, is_sampled, merge_types, scope_of_asset,
)
from core.report_types import (  # noqa: E402
    BUILTIN_REPORT_TYPES, LEGACY_LAGOON_TYPE, SCOPES, SCOPE_FACILITIES,
    SCOPE_LAGOON, get_builtin, is_known, normalise_name, saves_to_readings,
)
from ingestion.wimpey import FORM_TYPES  # noqa: E402


# --------------------------------------------------------------------------
# Built-in report types
# --------------------------------------------------------------------------

def test_every_builtin_is_fully_described():
    for t in BUILTIN_REPORT_TYPES:
        assert t["key"] and t["label"] and t["builtin"] is True


def test_report_types_carry_no_scope():
    """The regression guard for the whole model change.

    A `scope` key reappearing here means someone has re-attached the
    specification set to the analysis rather than to the asset, which is the
    mistake migration 019 exists to undo.
    """
    for t in BUILTIN_REPORT_TYPES:
        assert "scope" not in t, f"{t['key']} carries a scope; scope belongs to the asset"


def test_builtin_keys_are_unique():
    keys = [t["key"] for t in BUILTIN_REPORT_TYPES]
    assert len(keys) == len(set(keys))


def test_builtin_keys_cover_every_report_type_the_parser_emits():
    """The upload dropdown is matched against the certificate's own form code, so
    the two vocabularies cannot be allowed to drift apart."""
    assert set(FORM_TYPES.values()) <= {t["key"] for t in BUILTIN_REPORT_TYPES}


def test_get_builtin_is_case_and_padding_tolerant():
    assert get_builtin("lagoon")["label"] == "Lagoon Water Quality"
    assert get_builtin("  LAGOON ")["key"] == "lagoon"
    assert get_builtin("nope") is None
    assert get_builtin("") is None


def test_is_known_covers_builtins_and_custom_types():
    custom = [{"name": "Cooling Tower Water"}]
    assert is_known("chemistry")
    assert is_known("cooling tower water", custom)
    assert is_known("Cooling  Tower  Water", custom)   # normalised on both sides
    assert not is_known("nothing like this", custom)


# --------------------------------------------------------------------------
# Asset classes — equipment vs sampled
# --------------------------------------------------------------------------

def test_asset_types_split_cleanly_into_two_classes():
    for t in ASSET_TYPES:
        assert t["asset_class"] in ASSET_CLASSES
    keys = [t["key"] for t in ASSET_TYPES]
    assert len(keys) == len(set(keys))


def test_equipment_is_never_sampled():
    """A laboratory certificate is never about a dosing pump. Equipment is what
    you maintain; sampled assets are what a certificate is about."""
    for key in ("pump", "filter", "dosing", "aerator"):
        assert class_of(key) == CLASS_EQUIPMENT
        assert not is_sampled(key)


def test_sampled_types_are_the_things_a_certificate_can_be_about():
    for key in ("water_body", "water_tank", "fountain", "washroom_outlet", "misting_line"):
        assert class_of(key) == CLASS_SAMPLED
        assert is_sampled(key)


def test_unknown_asset_type_has_no_class():
    assert class_of("teleporter") is None
    assert class_of("") is None
    assert get_asset_type("teleporter") is None


# --------------------------------------------------------------------------
# scope_of_asset — the single place a specification set is chosen
# --------------------------------------------------------------------------

def test_scope_comes_from_a_sampled_asset():
    assert scope_of_asset({"asset_type": "water_tank", "scope": SCOPE_FACILITIES}) == SCOPE_FACILITIES
    assert scope_of_asset({"asset_type": "water_body", "scope": SCOPE_LAGOON}) == SCOPE_LAGOON


def test_equipment_has_no_scope_even_if_a_row_claims_one():
    """Defence in depth behind the database CHECK. A scope on a dosing pump is
    meaningless, and honouring it would apply limits to a thing never sampled."""
    assert scope_of_asset({"asset_type": "dosing", "scope": SCOPE_FACILITIES}) is None


def test_missing_or_invalid_scope_resolves_to_none_not_a_default():
    """None means "cannot judge" and must leave results unassessed. A default here
    would silently apply one scope's limits to the other's asset — the exact
    failure this model exists to prevent."""
    assert scope_of_asset(None) is None
    assert scope_of_asset({}) is None
    assert scope_of_asset({"asset_type": "water_tank"}) is None
    assert scope_of_asset({"asset_type": "water_tank", "scope": "nonsense"}) is None
    assert scope_of_asset({"asset_type": "water_tank", "scope": None}) is None


def test_every_scope_constant_is_a_known_scope():
    assert set(SCOPES) == {SCOPE_LAGOON, SCOPE_FACILITIES}


# --------------------------------------------------------------------------
# Save routing
# --------------------------------------------------------------------------

def test_asset_scope_decides_routing_when_known():
    """`readings` has fourteen fixed columns and one row per site per month, so it
    cannot hold a certificate with an arbitrary parameter list."""
    assert saves_to_readings("chemistry", SCOPE_LAGOON) is True
    assert saves_to_readings("lagoon", SCOPE_FACILITIES) is False


def test_legacy_lagoon_type_routes_to_readings_when_no_asset_is_attached():
    """The lagoon product predates assets, so a hand-entered monthly reading has
    no asset to carry scope. That bridge is keyed on the report type alone."""
    assert saves_to_readings(LEGACY_LAGOON_TYPE, None) is True
    assert saves_to_readings("LAGOON", None) is True


def test_certificates_without_scope_or_lagoon_type_go_to_lab_samples():
    assert saves_to_readings("legionella", None) is False
    assert saves_to_readings("", None) is False
    assert saves_to_readings(None, None) is False


def test_junk_scope_falls_back_to_the_report_type_rather_than_routing_blind():
    assert saves_to_readings("legionella", "nonsense") is False
    assert saves_to_readings("lagoon", "nonsense") is True


# --------------------------------------------------------------------------
# normalise_name
# --------------------------------------------------------------------------

def test_normalise_name_trims_and_collapses_whitespace():
    assert normalise_name("  Cooling   Tower  Water ") == "Cooling Tower Water"
    assert normalise_name("") == ""
    assert normalise_name("   ") == ""


def test_normalise_name_preserves_case():
    assert normalise_name(" GRP Tank ") == "GRP Tank"


# --------------------------------------------------------------------------
# Report type conflict between the selection and the certificate
# --------------------------------------------------------------------------

def _conflict(selected, detected):
    return api_server._type_conflict(selected=selected, detected=detected, organization_id=None)


def test_no_conflict_when_selection_and_certificate_agree():
    assert _conflict("chemistry", "chemistry") is None
    assert _conflict("CHEMISTRY", "chemistry") is None


def test_no_conflict_when_nothing_was_selected():
    assert _conflict("", "legionella") is None


def test_no_conflict_when_the_document_declared_nothing():
    """A scan carries no form code, so there is nothing to disagree with."""
    assert _conflict("chemistry", "scanned") is None
    assert _conflict("chemistry", "") is None


def test_conflict_reports_both_sides_with_labels():
    c = _conflict("chemistry", "legionella")
    assert c["selected"] == "chemistry" and c["detected"] == "legionella"
    assert c["selected_label"] == "Chemical Analysis"
    assert c["detected_label"] == "Legionella"
    assert "Chemical Analysis" in c["message"] and "Legionella" in c["message"]


def test_conflict_no_longer_claims_anything_about_scope():
    """A type mismatch says what the laboratory did, not which limits apply — that
    follows from the asset. Reporting a scope here would be asserting something
    this comparison cannot know."""
    c = _conflict("lagoon", "legionella")
    for key in ("cross_scope", "selected_scope", "detected_scope"):
        assert key not in c


def test_unknown_selected_type_still_reports_a_conflict():
    c = _conflict("Cooling Tower Water", "legionella")
    assert c is not None
    assert c["selected_label"] == "Cooling Tower Water"


# --------------------------------------------------------------------------
# Organisation-defined asset types (migration 020)
# --------------------------------------------------------------------------

_CUSTOM = [
    {"key": "grp_tank", "label": "GRP Tank", "asset_class": CLASS_SAMPLED, "scope": SCOPE_FACILITIES},
    {"key": "water_tank", "label": "HIJACK", "asset_class": CLASS_EQUIPMENT, "scope": None},
    {"key": "junk", "label": "Junk", "asset_class": "nonsense", "scope": None},
]


def test_register_merges_builtins_with_org_types():
    from core.assets import merge_types
    keys = {t["key"] for t in merge_types(_CUSTOM)}
    assert "grp_tank" in keys
    assert len(keys) == len(ASSET_TYPES) + 1      # only the one valid custom row


def test_builtin_types_cannot_be_redefined_by_an_org():
    """Existing assets and the upload flow reference built-in keys, so an
    organisation must not be able to change what `water_tank` means underneath
    records already filed against it."""
    from core.assets import find_type
    assert find_type("water_tank", _CUSTOM)["asset_class"] == CLASS_SAMPLED


def test_a_custom_type_with_an_unusable_class_is_dropped_not_guessed():
    from core.assets import find_type
    assert find_type("junk", _CUSTOM) is None


def test_custom_typed_assets_still_resolve_their_scope():
    """Regression: scope_of_asset() once consulted the built-in taxonomy only, so
    every asset created under an org-defined type silently lost its scope and its
    certificates could never be judged."""
    assert scope_of_asset({
        "asset_type": "grp_tank", "asset_class": CLASS_SAMPLED, "scope": SCOPE_FACILITIES,
    }) == SCOPE_FACILITIES


def test_stored_class_beats_the_type_key_when_they_disagree():
    """The asset's own class is authoritative — it was validated at creation and
    the database CHECK backs it."""
    assert scope_of_asset({
        "asset_type": "water_tank", "asset_class": CLASS_EQUIPMENT, "scope": SCOPE_LAGOON,
    }) is None


def test_pre_019_rows_without_a_class_fall_back_to_the_builtin_taxonomy():
    assert scope_of_asset({"asset_type": "water_tank", "scope": SCOPE_FACILITIES}) == SCOPE_FACILITIES
    assert scope_of_asset({"asset_type": "pump", "scope": SCOPE_FACILITIES}) is None


# --------------------------------------------------------------------------
# Standard editions — stale citation detection
# --------------------------------------------------------------------------

def test_citation_check_is_silent_on_unknown_standards():
    """We only speak when we hold the edition facts. A confident 'your citation
    is out of date' about a document we have never read would send the client to
    argue with their laboratory over nothing."""
    from core.standards import citation_is_stale
    assert citation_is_stale("SOME-OTHER-CODE", "2019") is None
    assert citation_is_stale("", "2019") is None


def test_citation_check_needs_a_readable_year():
    from core.standards import citation_is_stale
    assert citation_is_stale("DM-HSD-GU44-LCWS2", "") is None
    assert citation_is_stale("DM-HSD-GU44-LCWS2", "n/a") is None
    assert citation_is_stale("DM-HSD-GU44-LCWS2", "24") is None


def test_current_or_newer_citation_is_not_flagged():
    from core.standards import citation_is_stale
    assert citation_is_stale("DM-HSD-GU44-LCWS2", "2025") is None
    assert citation_is_stale("DM-HSD-GU44-LCWS2", "2026") is None


def test_a_sample_taken_before_the_reissue_is_not_flagged():
    """The old citation was correct at the time. The certificate is not wrong,
    it is simply old, and flagging it would be noise."""
    from datetime import date
    from core.standards import citation_is_stale
    assert citation_is_stale("DM-HSD-GU44-LCWS2", "2024", date(2025, 1, 5)) is None
    assert citation_is_stale("DM-HSD-GU44-LCWS2", "2024", date(2026, 4, 21)) is not None
