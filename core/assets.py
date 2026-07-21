"""Asset taxonomy — what a thing *is*, and therefore which rules apply to it.

Two kinds of thing were previously in one flat `asset_type` list, which is why the
model did not hold together:

  equipment   pumps, filters, dosing units, aerators. Things you *maintain* —
              backwash at 1.3 bar, service the dosing pump. Nobody takes a
              laboratory sample from a dosing pump. These carry maintenance
              schedules and checklists.
  sampled     water bodies, water tanks, fountains, washroom outlets, misting
              lines. Things a laboratory certificate is *about*. These carry lab
              samples, specification limits and a compliance history.

`asset_class` separates them. Mixing them meant a maintenance category and a
sampling location competed for the same field.

**Scope lives here, on the asset — not on the report type.** A Legionella count of
900 CFU/L means one thing in a stored domestic tank and something else in an open
animal moat; it is the asset that decides which specification set applies. The
same asset also carries several report types over time (Gate Number 2 – GRP Water
Tank has both microbiology and Legionella certificates), so the report type cannot
be the thing that holds scope — it varies while the asset does not.

    asset instance  "Gate Number 2 – GRP Water Tank"
      └─ asset_type "water_tank"  (class: sampled)
           └─ scope "facilities"  → which limits may be applied

A sampled asset with no scope resolves to None, never a default: an unclassified
asset must not inherit limits by accident.
"""
from __future__ import annotations

from typing import Optional, TypedDict

from core.report_types import SCOPE_FACILITIES, SCOPE_LAGOON, SCOPES  # noqa: F401

CLASS_EQUIPMENT = "equipment"
CLASS_SAMPLED = "sampled"
ASSET_CLASSES: tuple[str, ...] = (CLASS_EQUIPMENT, CLASS_SAMPLED)


class AssetTypeDef(TypedDict):
    key: str
    label: str
    asset_class: str


# Equipment — maintained, never sampled. These are the pre-existing values.
EQUIPMENT_TYPES: list[AssetTypeDef] = [
    {"key": "pump",    "label": "Pump",        "asset_class": CLASS_EQUIPMENT},
    {"key": "filter",  "label": "Filter",      "asset_class": CLASS_EQUIPMENT},
    {"key": "dosing",  "label": "Dosing unit", "asset_class": CLASS_EQUIPMENT},
    {"key": "aerator", "label": "Aerator",     "asset_class": CLASS_EQUIPMENT},
]

# Sampled — a laboratory certificate is about one of these. Grounded in the
# Dubai Safari Park register (water bodies WB*, wet moats WM*) and SOP 3's public
# health assets (fountains, washroom monitoring points, misting systems).
SAMPLED_TYPES: list[AssetTypeDef] = [
    {"key": "water_body",      "label": "Water body / lagoon",  "asset_class": CLASS_SAMPLED},
    {"key": "water_tank",      "label": "Water tank",           "asset_class": CLASS_SAMPLED},
    {"key": "fountain",        "label": "Fountain",             "asset_class": CLASS_SAMPLED},
    {"key": "washroom_outlet", "label": "Washroom outlet",      "asset_class": CLASS_SAMPLED},
    {"key": "misting_line",    "label": "Misting line",         "asset_class": CLASS_SAMPLED},
]

ASSET_TYPES: list[AssetTypeDef] = EQUIPMENT_TYPES + SAMPLED_TYPES
_BY_KEY = {t["key"]: t for t in ASSET_TYPES}


def get_asset_type(key: str) -> Optional[AssetTypeDef]:
    return _BY_KEY.get((key or "").strip().lower())


def class_of(asset_type: str) -> Optional[str]:
    """Which class a type belongs to. None for an unrecognised type."""
    t = get_asset_type(asset_type)
    return t["asset_class"] if t else None


def is_sampled(asset_type: str) -> bool:
    """True when a laboratory certificate can legitimately be about this type."""
    return class_of(asset_type) == CLASS_SAMPLED


def scope_of_asset(asset: Optional[dict]) -> Optional[str]:
    """The specification scope an asset is judged under.

    None when the asset is missing, is equipment, or carries no valid scope. The
    caller must treat None as "cannot judge" and leave results unassessed — a
    default here would silently apply one scope's limits to the other's asset.
    """
    if not asset:
        return None
    # Trust the asset's own stored class. It was validated at creation and the
    # database CHECK forbids a scope on anything but a sampled row. Re-deriving it
    # from the type key would consult built-ins only, so every asset created under
    # an organisation-defined type (migration 020) would silently lose its scope.
    asset_class = asset.get("asset_class")
    if asset_class:
        if asset_class != CLASS_SAMPLED:
            return None
    elif not is_sampled(asset.get("asset_type") or ""):
        # Pre-019 rows have no class; fall back to the built-in taxonomy.
        return None
    scope = asset.get("scope")
    return scope if scope in SCOPES else None


def merge_types(custom: Optional[list[dict]] = None) -> list[AssetTypeDef]:
    """Built-in types plus an organisation's own (migration 020).

    Built-ins win on a key collision: they are referenced by existing assets and
    by the upload flow, so an organisation cannot redefine `water_tank` out from
    under records already filed against it.
    """
    merged: list[AssetTypeDef] = list(ASSET_TYPES)
    seen = {t["key"] for t in merged}
    for row in custom or []:
        key = (row.get("key") or "").strip().lower()
        if not key or key in seen:
            continue
        cls = row.get("asset_class")
        if cls not in ASSET_CLASSES:
            continue                      # unusable row; never guess a class
        merged.append({
            "key": key,
            "label": row.get("label") or key,
            "asset_class": cls,
            "scope": row.get("scope"),     # type: ignore[typeddict-unknown-key]
        })
        seen.add(key)
    return merged


def find_type(key: str, custom: Optional[list[dict]] = None) -> Optional[dict]:
    """Resolve a type across built-ins and an organisation's own."""
    wanted = (key or "").strip().lower()
    for t in merge_types(custom):
        if t["key"] == wanted:
            return dict(t)
    return None


def default_scope_for_type(key: str, custom: Optional[list[dict]] = None) -> Optional[str]:
    """The scope a new asset of this type should inherit.

    Built-in sampled types carry no scope of their own — the two lagoon/facilities
    sets both contain water bodies — so the caller must supply one. Custom types
    declare it, which is what makes them useful.
    """
    t = find_type(key, custom)
    if not t or t.get("asset_class") != CLASS_SAMPLED:
        return None
    scope = t.get("scope")
    return scope if scope in SCOPES else None
