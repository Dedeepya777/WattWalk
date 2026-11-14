"""Test heat shares calculation against fixture.

Owner: Person 1.
See plan/prompt_1.md section E Stage 2 and acceptance criteria G.
"""
from __future__ import annotations

import json

import pytest
from wattwalk import config
from wattwalk.contracts import Asset, Building, ModelGeometry
from wattwalk.engine import heat_shares


def test_heat_shares_exact_match() -> None:
    geom_path = config.EXAMPLES_DIR / "model_geometry.json"
    with open(geom_path, "r", encoding="utf-8") as f:
        geom = ModelGeometry.model_validate(json.load(f))

    inv_path = config.EXAMPLES_DIR / "inventory.json"
    with open(inv_path, "r", encoding="utf-8") as f:
        inv = [Asset.model_validate(x) for x in json.load(f)]

    bld_path = config.EXAMPLES_DIR / "building.json"
    with open(bld_path, "r", encoding="utf-8") as f:
        bld = Building.model_validate(json.load(f))

    expected_path = config.EXAMPLES_DIR / "heat_shares.json"
    with open(expected_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    actual = heat_shares(geom.rooms, inv, bld)
    actual_dump = [h.model_dump(mode="json") for h in actual]

    assert actual_dump == expected
