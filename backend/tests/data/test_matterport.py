"""Test Matterport adapter in fixture and live modes.

Owner: Person 1.
See plan/plan.md section 15.3, acceptance criteria G items 5, 8.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from wattwalk import config
from wattwalk.contracts import ModelGeometry
from wattwalk.data.matterport import get_face_image, get_geometry


def test_get_geometry_fixture_mode() -> None:
    # In fixture mode (default), fixtureUnitA returns model_geometry.json with status fixture without network
    geom = get_geometry("fixtureUnitA")
    assert geom.sid == "fixtureUnitA"
    assert geom.status == "fixture"
    assert len(geom.rooms) == 6
    assert len(geom.panos) == 7
    assert len(geom.walls) > 0


def test_get_geometry_fixture_mode_unknown_raises() -> None:
    with pytest.raises(ValueError, match="no geometry fixture"):
        get_geometry("unknown_nonexistent_sid")


def test_get_face_image_fixture_mode_raises() -> None:
    with pytest.raises(ValueError, match="fixture mode"):
        get_face_image("fixtureUnitA", "p01", 1, "2k")


def test_polygon_area_within_15_percent_of_area_floor() -> None:
    geom = get_geometry("fixtureUnitA")
    for room in geom.rooms:
        coords = [(p.x, p.y) for p in room.polygon]
        poly = Polygon(coords)
        poly_area = poly.area
        assert abs(poly_area - room.area_m2) / room.area_m2 <= 0.15, (
            f"Room {room.id} polygon area {poly_area} differs by >15% from area_m2 {room.area_m2}"
        )
