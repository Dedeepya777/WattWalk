"""Test assumption overrides and validation.

Owner: Person 1.
See plan/prompt_1.md section E Stage 2, G item 4.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from wattwalk import config
from wattwalk.contracts import Asset, Building, PlanRequest
from wattwalk.engine import plan


@pytest.fixture
def fixture_inventory() -> list[Asset]:
    path = config.EXAMPLES_DIR / "inventory.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Asset.model_validate(item) for item in data]


@pytest.fixture
def fixture_building() -> Building:
    path = config.EXAMPLES_DIR / "building.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Building.model_validate(data)


def test_lighting_hours_override(fixture_inventory: list[Asset], fixture_building: Building) -> None:
    req = PlanRequest(
        budget_usd=2000,
        objective="max_bill",
        role="owner",
        overrides={"lighting_hours_per_day": 4.0},
    )
    resp = plan("fixtureUnitA", fixture_inventory, fixture_building, req)

    led_line = next(u for u in resp.upgrades if u.upgrade_id == "led")
    # 8 bulbs x (60 W - 9 W) x 4 h/day x 365 / 1000 = 595.68 -> 595.7 kWh/yr
    assert led_line.kwh_saved_yr == 595.7

    used_hours = next(a for a in resp.assumptions_used if a.key == "lighting_hours_per_day")
    assert used_hours.value == 4.0
    assert used_hours.status == "user_override"
    assert used_hours.source == "user override"


def test_invalid_override_key_raises_value_error(fixture_inventory: list[Asset], fixture_building: Building) -> None:
    req = PlanRequest(
        budget_usd=2000,
        overrides={"completely_unknown_key": 42.0},
    )
    with pytest.raises(ValueError, match="completely_unknown_key"):
        plan("fixtureUnitA", fixture_inventory, fixture_building, req)


def test_table_key_override_raises_value_error(fixture_inventory: list[Asset], fixture_building: Building) -> None:
    req = PlanRequest(
        budget_usd=2000,
        overrides={"cooling_kwh_per_m2_yr": 25.0},
    )
    with pytest.raises(ValueError, match="cooling_kwh_per_m2_yr"):
        plan("fixtureUnitA", fixture_inventory, fixture_building, req)


def test_fraction_override_bounds(fixture_inventory: list[Asset], fixture_building: Building) -> None:
    req = PlanRequest(
        budget_usd=2000,
        overrides={"window_film_reduction": 1.5},
    )
    with pytest.raises(ValueError, match="window_film_reduction"):
        plan("fixtureUnitA", fixture_inventory, fixture_building, req)


def test_negative_override_bounds(fixture_inventory: list[Asset], fixture_building: Building) -> None:
    req = PlanRequest(
        budget_usd=2000,
        overrides={"lighting_hours_per_day": -1.0},
    )
    with pytest.raises(ValueError, match="lighting_hours_per_day"):
        plan("fixtureUnitA", fixture_inventory, fixture_building, req)
