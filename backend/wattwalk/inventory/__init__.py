"""Inventory: dedupe, coverage and corrections (plan 8.6 to 8.8, Appendix A.4). Owner: Person 2.

One physical object is one asset (decision D5). Asset id = "a_" + lowest observation id in its group.
"""
from __future__ import annotations

import math
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable

from ..contracts import ASSET_LABELS, Asset, Attr, Coverage, CorrectionRequest, ModelGeometry, Observation, RoomCoverage, Vec3
from ..vision.prompts import ATTR_ORDER, INT_ATTRS, KEY_ATTR, VOCAB

# Same-object distance thresholds in metres (8.6.1).
THRESHOLD_M: dict[str, float] = {
    "refrigerator": 1.5,
    "range_gas": 1.0, "range_electric": 1.0, "washer": 1.0, "dryer": 1.0, "water_heater": 1.0, "dishwasher": 1.0,
    "window_ac": 0.8, "mini_split": 0.8,
    "window": 0.6, "thermostat": 0.6, "ceiling_fan": 0.6,
    "ceiling_light": 0.5, "lamp": 0.5,
    "supply_vent": 0.4,
}
ONE_PER_ROOM = {"refrigerator", "range_gas", "range_electric", "dishwasher", "washer", "dryer", "water_heater"}

# Next-step table (8.6.4), in priority order. A None attribute means "always, for this label".
NEXT_STEP: list[tuple[tuple[str, ...], str | None, str]] = [
    (("window",), "panes", "Confirm glazing (single or double pane) from a close photo or on site"),
    (("window",), "shading", "Check whether the window has blinds or curtains"),
    (("ceiling_light", "lamp"), "bulb_type", "Photo of a bulb, or answer the bulb-type question"),
    (("thermostat",), "thermostat_type", "Photo of the thermostat face"),
    (("refrigerator",), "age_years", "Photo of the refrigerator nameplate (model number)"),
    (("window_ac", "mini_split"), None, "Photo of the AC unit label to confirm efficiency (EER)"),
]

EXPECTED_CHECKLIST = ["thermostat", "water_heater"]  # fixed in the MVP (7.8)
CORRIDOR_WORDS = ("hall", "corridor", "entry", "foyer")  # rooms where finding nothing is expected


# ---------- helpers ----------

def id_key(obs_id: str) -> tuple[int, str]:
    """Sort key for o001-style ids that stays correct past o999."""
    m = re.search(r"(\d+)$", obs_id)
    return (int(m.group(1)) if m else -1, obs_id)


def asset_id_key(asset_id: str) -> tuple[int, str]:
    return id_key(asset_id.removeprefix("a_"))


def round3(values: Iterable[float]) -> float:
    """Mean rounded half-up to 3 decimals, computed in decimal to avoid binary rounding surprises."""
    vals = [Decimal(repr(v)) for v in values]
    mean = sum(vals) / len(vals)
    return float(mean.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def _dist(a: Vec3, b: Vec3) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def next_step_for(label: str, attrs: dict[str, Attr]) -> str:
    for labels, attr, text in NEXT_STEP:
        if label not in labels:
            continue
        if attr is None or (attr in attrs and attrs[attr].value is None):
            return text
    return ""


# ---------- dedupe (8.6) ----------

def same_object(a: Observation, b: Observation) -> bool:
    if a.id == b.id or a.label != b.label:
        return False
    if (a.pano_id, a.face) == (b.pano_id, b.face):
        return False  # two detections in one face are different objects
    threshold = THRESHOLD_M.get(a.label, 0.5)
    both_anchored = a.anchor is not None and b.anchor is not None
    if a.room_id is not None and b.room_id is not None:
        if a.room_id != b.room_id:
            return False
    elif a.room_id is None and b.room_id is None:
        if not (both_anchored and _dist(a.anchor, b.anchor) < threshold):
            return False
    else:
        return False
    if a.label in ONE_PER_ROOM and a.room_id is not None:
        return True
    return both_anchored and _dist(a.anchor, b.anchor) < threshold


def _groups(observations: list[Observation]) -> list[list[Observation]]:
    parent = list(range(len(observations)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(observations)):
        for j in range(i + 1, len(observations)):
            if same_object(observations[i], observations[j]):
                parent[find(i)] = find(j)
    groups: dict[int, list[Observation]] = {}
    for i, o in enumerate(observations):
        groups.setdefault(find(i), []).append(o)
    return [sorted(g, key=lambda o: id_key(o.id)) for g in groups.values()]


def _attr_keys(label: str, members: list[Observation]) -> list[str]:
    seen: list[str] = []
    for key in ATTR_ORDER.get(label, []):
        if any(key in m.attrs for m in members):
            seen.append(key)
    for m in members:
        for key in m.attrs:
            if key not in seen:
                seen.append(key)
    return seen


def _preference(m: Observation, attr: Attr) -> tuple[int, tuple[int, str]]:
    # provided_by_user first, then the large model's reading, then the lowest observation id
    rank = 0 if attr.source == "provided_by_user" else (1 if m.escalated else 2)
    return rank, id_key(m.id)


def merge_group(group: list[Observation]) -> Asset:
    """Merge one same-object group into an asset."""
    members = sorted(group, key=lambda o: id_key(o.id))
    label = members[0].label
    attrs: dict[str, Attr] = {}
    disagreement = False
    for key in _attr_keys(label, members):
        reporting = [m for m in members if key in m.attrs]
        evidence = [m.id for m in reporting]
        known = [(m, m.attrs[key]) for m in reporting if m.attrs[key].value is not None]
        if known:
            m, chosen = min(known, key=lambda pair: _preference(*pair))
            note = chosen.note
            distinct: list[Any] = []
            for _, a in known:
                if a.value not in distinct:
                    distinct.append(a.value)
            if len(distinct) > 1:
                disagreement = True
                text = "observations disagree: " + " vs ".join(str(v) for v in distinct)
                note = f"{note}; {text}" if note else text
            attrs[key] = Attr(value=chosen.value, source=chosen.source, note=note, evidence_obs_ids=evidence)
        else:
            first = reporting[0].attrs[key]
            attrs[key] = Attr(value=None, source="needs_verification", note=first.note, evidence_obs_ids=evidence)
    anchors = [m.anchor for m in members if m.anchor is not None]
    anchor = (Vec3(x=round3(a.x for a in anchors), y=round3(a.y for a in anchors), z=round3(a.z for a in anchors))
              if anchors else None)
    asset = Asset(id="a_" + members[0].id, label=label, scope="unit", room_id=members[0].room_id,
                  observation_ids=[m.id for m in members], attrs=attrs, anchor=anchor,
                  next_step=next_step_for(label, attrs), disagreement=disagreement)
    return asset


def build_inventory(observations: list[Observation]) -> list[Asset]:
    assets = [merge_group(g) for g in _groups(list(observations))]
    return sorted(assets, key=lambda a: asset_id_key(a.id))


# ---------- coverage (8.7) ----------

def _words(s: str) -> str:
    return s.replace("_", " ")


def _unresolved_notes(room_assets: list[Asset], observations: dict[str, Observation]) -> list[str]:
    """Notes for key attributes still unknown after escalating to the large model."""
    notes = []
    for a in room_assets:
        key = KEY_ATTR.get(a.label)
        if key is None or key not in a.attrs or a.attrs[key].value is not None:
            continue
        if not any(observations[o].escalated for o in a.observation_ids if o in observations):
            continue
        asked = "question" in a.attrs[key].note
        steps = "high-res crop, large model and user question" if asked else "high-res crop and large model"
        notes.append(f"{_words(a.label).capitalize()} {_words(key)} unresolved after {steps}")
    return notes


def compute_coverage(geometry: ModelGeometry, observations: list[Observation], inventory: list[Asset],
                     reviewed: dict[str, list[str]], faces_rejected: int, partial_rooms: dict[str, str]) -> Coverage:
    """reviewed: room id -> panos inspected; partial_rooms: room id -> reason (used as the room's first note)."""
    obs_by_id = {o.id: o for o in observations}
    rooms: list[RoomCoverage] = []
    for room in geometry.rooms:
        panos = list(reviewed.get(room.id, []))
        room_assets = [a for a in inventory if a.room_id == room.id]
        notes: list[str] = []
        if room.id in partial_rooms:
            status = "partial"
            notes.append(partial_rooms[room.id])
        elif panos:
            status = "reviewed"
        else:
            status = "not_visited"
            notes.append("no panorama inside this room" if not room.pano_ids else "no panorama of this room was inspected")
        if room.area_m2 >= 20.0 and len(panos) >= 2:
            notes.append(f"Room area {room.area_m2:.1f} m2 >= 20 m2, so two panoramas were inspected")
        notes.extend(_unresolved_notes(room_assets, obs_by_id))
        corridor = any(w in room.label.lower() for w in CORRIDOR_WORDS)
        if status == "reviewed" and not room_assets and not corridor:
            notes.append("No energy-relevant assets found")
        rooms.append(RoomCoverage(room_id=room.id, room_label=room.label, status=status,
                                  panos_reviewed=panos, notes=notes))

    reviewed_panos = {p for ps in reviewed.values() for p in ps}
    present = {a.label for a in inventory}
    known = sum(1 for a in inventory for v in a.attrs.values() if v.value is not None)
    unknown = sum(1 for a in inventory for v in a.attrs.values() if v.value is None)
    return Coverage(
        panos_total=len(geometry.panos), panos_reviewed=len(reviewed_panos),
        rooms_total=len(geometry.rooms), rooms_reviewed=sum(1 for r in rooms if r.status != "not_visited"),
        assets_unique=len(inventory), observations_total=len(observations),
        attrs_known=known, attrs_unknown=unknown, faces_rejected=faces_rejected,
        not_visible=[label for label in EXPECTED_CHECKLIST if label not in present],
        rooms=rooms)


# ---------- corrections (8.8, 7.12.10) ----------

class UnknownAssetError(LookupError):
    """The correction names an asset that does not exist (API answers 404)."""


def _validate_value(label: str, field: str, value: Any) -> Any:
    if field not in VOCAB.get(label, {}):
        raise ValueError(f"field {field!r} is not valid for label {label!r}")
    allowed = VOCAB[label][field]
    if isinstance(allowed, list):
        v = str(value).strip().lower()
        if v not in allowed:
            raise ValueError(f"value {value!r} not allowed for {field}; allowed: {allowed}")
        return v
    if isinstance(value, bool):
        raise ValueError(f"value for {field} must be a number")
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"value for {field} must be a number") from None
    lo, hi = allowed
    if not lo <= num <= hi:
        raise ValueError(f"value for {field} must be between {lo} and {hi}")
    if field in INT_ATTRS:
        if num != int(num):
            raise ValueError(f"value for {field} must be an integer")
        return int(num)
    return num


def _user_attr(value: Any, note: str = "user correction") -> Attr:
    return Attr(value=value, source="provided_by_user", note=note, evidence_obs_ids=[])


def apply_correction(inventory: list[Asset], observations: list[Observation],
                     req: CorrectionRequest) -> tuple[list[Asset], list[str]]:
    """Apply one correction to an inventory. Raises UnknownAssetError (404) or ValueError (422)."""
    by_id = {a.id: a for a in inventory}
    if req.asset_id not in by_id:
        raise UnknownAssetError(req.asset_id)
    asset = by_id[req.asset_id].model_copy(deep=True)

    if req.field == "label":
        if req.value not in ASSET_LABELS:
            raise ValueError(f"label {req.value!r} is not an asset label")
        allowed = VOCAB[str(req.value)]
        asset.label = str(req.value)
        asset.attrs = {k: v for k, v in asset.attrs.items() if k in allowed}
        asset.next_step = next_step_for(asset.label, asset.attrs)
        by_id[asset.id] = asset
        return sorted(by_id.values(), key=lambda a: asset_id_key(a.id)), [asset.id]

    if req.field == "merge_into":
        target_id = str(req.value)
        if target_id not in by_id or target_id == asset.id:
            raise ValueError(f"merge_into must name another existing asset, got {target_id!r}")
        target = by_id[target_id]
        if target.label != asset.label:
            raise ValueError("merge_into requires two assets with the same label")
        obs_by_id = {o.id: o for o in observations}
        members = [obs_by_id[o] for o in asset.observation_ids + target.observation_ids if o in obs_by_id]
        if not members:
            raise ValueError("assets have no observations to merge")
        merged = merge_group(members)
        # keep earlier user corrections from either asset (the target wins on conflicts)
        for src in (asset, target):
            for key, attr in src.attrs.items():
                if attr.source == "provided_by_user":
                    merged.attrs[key] = attr
        merged.label = target.label
        merged.next_step = next_step_for(merged.label, merged.attrs)
        del by_id[asset.id], by_id[target.id]
        by_id[merged.id] = merged
        changed = sorted({asset.id, target.id, merged.id}, key=asset_id_key)
        return sorted(by_id.values(), key=lambda a: asset_id_key(a.id)), changed

    value = _validate_value(asset.label, req.field, req.value)
    asset.attrs[req.field] = _user_attr(value)
    if req.field in ("width_m", "height_m"):
        w, h = asset.attrs.get("width_m"), asset.attrs.get("height_m")
        if w is not None and h is not None and w.value is not None and h.value is not None:
            asset.attrs["area_m2"] = _user_attr(round(float(w.value) * float(h.value), 1), "width_m x height_m (user correction)")
    # next_step is left as it was: shared/examples/correction_response.json keeps it after a correction.
    by_id[asset.id] = asset
    return sorted(by_id.values(), key=lambda a: asset_id_key(a.id)), [asset.id]


def apply_corrections_with_notes(observations: list[Observation],
                                 corrections: list[CorrectionRequest]) -> tuple[list[Asset], list[str]]:
    """Rebuild from observations, then re-apply every stored correction in order.

    Corrections that refer to an asset id that no longer exists are skipped with a note.
    """
    inventory = build_inventory(observations)
    notes: list[str] = []
    for req in corrections:
        try:
            inventory, _ = apply_correction(inventory, observations, req)
        except UnknownAssetError:
            notes.append(f"correction for {req.asset_id} no longer applies")
    return inventory, notes


def apply_corrections(observations: list[Observation], corrections: list[CorrectionRequest]) -> list[Asset]:
    return apply_corrections_with_notes(observations, corrections)[0]
