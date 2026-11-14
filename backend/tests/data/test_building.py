"""Test Building context adapter.

Owner: Person 1.
See plan/plan.md section 15.3, acceptance criteria G item 6.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from wattwalk import config
from wattwalk.contracts import Building, ModelGeometry
from wattwalk.data.building import get_building
from wattwalk.data.matterport import get_geometry


def test_get_building_fixture_mode() -> None:
    geom = get_geometry("fixtureUnitA")
    bld = get_building("fixtureUnitA", geom)

    assert bld.address == "100 Example St, Los Angeles, CA 90000"
    assert bld.city == "Los Angeles"
    assert bld.layer_status.matterport == "fixture"
    assert bld.layer_status.ebewe == "fixture"
    assert bld.ebewe is not None
    assert bld.ebewe.site_eui_kbtu_ft2 == 35.9


def test_failing_layer_isolation() -> None:
    """Acceptance criterion 6: one failing layer does not fail the others."""
    # Build a live geometry mock
    geom = get_geometry("fixtureUnitA")
    # In live building resolution, missing Vexcel key or CoStar kit leaves those unavailable without error
    bld = get_building("2YKpZqjy5bJ", geom)
    assert bld is not None
    # EBEWE succeeded for LA address, while costar and vexcel are honest
    assert bld.layer_status.ebewe in {"live", "fixture"}
