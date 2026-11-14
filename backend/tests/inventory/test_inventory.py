"""Inventory tests (plan Appendix B, Person 2)."""
from __future__ import annotations

import pytest

from wattwalk.contracts import Asset, CorrectionRequest, CorrectionResponse, Coverage, PlanRequest, Vec3
from wattwalk.inventory import (UnknownAssetError, apply_correction, apply_corrections, apply_corrections_with_notes,
                                build_inventory, compute_coverage, same_object)
from tests.conftest import load_example

REVIEWED = {"r_living": ["p01", "p02"], "r_bed": ["p03"], "r_kitchen": ["p04"], "r_bath": ["p05"],
            "r_hall": ["p06"], "r_closet": ["p07"]}
PARTIAL = {"r_bath": "1 of 4 faces rejected as too dark (brightness 31); no other panorama inside this room"}


def _expected_inventory() -> list[Asset]:
    return [Asset.model_validate(a) for a in load_example("inventory.json")]


def test_dedupe_fixture(fixture_observations):
    inventory = build_inventory(fixture_observations)
    assert inventory == _expected_inventory()
    window = inventory[0]
    assert window.id == "a_o001" and window.observation_ids == ["o001", "o002"]
    assert window.anchor == Vec3(x=2.904, y=0.073, z=1.738)


def test_dedupe_same_room_two_windows(fixture_observations):
    a = fixture_observations[0]
    b = a.model_copy(update={"id": "o011", "pano_id": "p02", "face": 2, "anchor": Vec3(x=3.895, y=0.1, z=1.738)})
    assert not same_object(a, b)  # 1.0 m apart, above the 0.6 m window threshold
    assert len([x for x in build_inventory([a, b]) if x.label == "window"]) == 2


def test_dedupe_refrigerator_seen_twice_merges(fixture_observations):
    fridge = next(o for o in fixture_observations if o.label == "refrigerator")
    other = fridge.model_copy(update={"id": "o011", "pano_id": "p99", "anchor": Vec3(x=1.294, y=4.505, z=0.241)})
    assets = build_inventory([fridge, other])
    assert len(assets) == 1 and assets[0].observation_ids == ["o009", "o011"]


def test_same_face_never_merges(fixture_observations):
    a = fixture_observations[4]  # ceiling light o005
    b = a.model_copy(update={"id": "o011"})
    assert not same_object(a, b)


def test_dedupe_disagreement(fixture_observations):
    a, b = fixture_observations[0], fixture_observations[1]
    b = b.model_copy(deep=True)
    b.attrs["shading"] = b.attrs["shading"].model_copy(update={"value": "none"})
    asset = build_inventory([a, b])[0]
    assert asset.disagreement is True
    assert asset.attrs["shading"].value == "blinds"  # lowest observation id wins without escalation
    assert "observations disagree: blinds vs none" in asset.attrs["shading"].note


def test_dedupe_prefers_escalated_value(fixture_observations):
    a, b = fixture_observations[0], fixture_observations[1].model_copy(deep=True)
    b.attrs["shading"] = b.attrs["shading"].model_copy(update={"value": "curtains"})
    b = b.model_copy(update={"escalated": True, "model_tier": "large"})
    assert build_inventory([a, b])[0].attrs["shading"].value == "curtains"


def test_coverage_fixture(geometry, fixture_observations):
    inventory = build_inventory(fixture_observations)
    coverage = compute_coverage(geometry, fixture_observations, inventory, REVIEWED, 1, PARTIAL)
    assert coverage == Coverage.model_validate(load_example("coverage.json"))


def test_coverage_not_visited_room(geometry, fixture_observations):
    reviewed = {k: v for k, v in REVIEWED.items() if k != "r_closet"}
    coverage = compute_coverage(geometry, fixture_observations, build_inventory(fixture_observations), reviewed, 1, PARTIAL)
    closet = next(r for r in coverage.rooms if r.room_id == "r_closet")
    assert closet.status == "not_visited" and coverage.rooms_reviewed == 5


def test_correction_fixture(geometry, fixture_observations):
    expected = CorrectionResponse.model_validate(load_example("correction_response.json"))
    req = CorrectionRequest.model_validate(load_example("correction_request.json"))
    inventory, changed = apply_correction(build_inventory(fixture_observations), fixture_observations, req)
    assert inventory == expected.inventory
    assert changed == expected.changed_asset_ids
    coverage = compute_coverage(geometry, fixture_observations, inventory, REVIEWED, 1, PARTIAL)
    assert coverage == expected.coverage


def _req(asset_id, field, value):
    return CorrectionRequest(asset_id=asset_id, field=field, value=value, plan_request=PlanRequest())


def test_correction_validation(fixture_observations):
    inventory = build_inventory(fixture_observations)
    with pytest.raises(UnknownAssetError):
        apply_correction(inventory, fixture_observations, _req("a_o999", "bulb_type", "led"))
    with pytest.raises(ValueError):
        apply_correction(inventory, fixture_observations, _req("a_o005", "bulb_type", "halogen"))
    with pytest.raises(ValueError):
        apply_correction(inventory, fixture_observations, _req("a_o005", "shading", "blinds"))
    with pytest.raises(ValueError):
        apply_correction(inventory, fixture_observations, _req("a_o005", "bulb_count", 40))


def test_correction_width_recomputes_area(fixture_observations):
    inventory, _ = apply_correction(build_inventory(fixture_observations), fixture_observations, _req("a_o001", "width_m", 2.0))
    window = inventory[0]
    assert window.attrs["width_m"].source == "provided_by_user"
    assert window.attrs["area_m2"].value == 2.4


def test_correction_label_drops_invalid_attrs(fixture_observations):
    inventory, changed = apply_correction(build_inventory(fixture_observations), fixture_observations, _req("a_o005", "label", "lamp"))
    lamp = next(a for a in inventory if a.id == "a_o005")
    assert lamp.label == "lamp" and set(lamp.attrs) == {"bulb_type", "bulb_count"} and changed == ["a_o005"]
    inventory, _ = apply_correction(inventory, fixture_observations, _req("a_o009", "label", "dishwasher"))
    assert next(a for a in inventory if a.id == "a_o009").attrs == {}


def test_correction_merge_into(fixture_observations):
    inventory = build_inventory(fixture_observations)
    inventory, _ = apply_correction(inventory, fixture_observations, _req("a_o006", "bulb_type", "cfl"))
    inventory, changed = apply_correction(inventory, fixture_observations, _req("a_o006", "merge_into", "a_o005"))
    merged = next(a for a in inventory if a.id == "a_o005")
    assert merged.observation_ids == ["o005", "o006"] and len(inventory) == 8
    assert merged.attrs["bulb_type"].value == "cfl"  # earlier user correction survives the merge
    assert changed == ["a_o005", "a_o006"]


def test_corrections_replay_and_skip(fixture_observations):
    reqs = [_req("a_o005", "bulb_type", "led"), _req("a_o777", "bulb_type", "led")]
    inventory, notes = apply_corrections_with_notes(fixture_observations, reqs)
    assert next(a for a in inventory if a.id == "a_o005").attrs["bulb_type"].value == "led"
    assert notes == ["correction for a_o777 no longer applies"]
    assert apply_corrections(fixture_observations, reqs) == inventory
