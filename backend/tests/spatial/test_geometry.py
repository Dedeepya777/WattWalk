"""Anchor tests for Person 4 (plan 15.6 and Appendix B).

The fixture boxes in shared/examples/observations.json are the inputs and the
ten anchors in plan 4.6.2 are the expected outputs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from wattwalk.contracts import BBox, ModelGeometry, Observation, Pano, Room, Vec2, WallSegment
from wattwalk.spatial.geometry import (
    FaceBasis,
    anchor_from_bbox,
    anchor_observation,
    anchor_pixel,
    load_basis,
    pixel_ray,
    ray_wall_hit,
    room_centroid,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = REPO_ROOT / "shared" / "examples"

# Plan 4.6.2: (x, y, z) and method for each fixture observation id.
EXPECTED_ANCHORS: dict[str, tuple[tuple[float, float, float], str]] = {
    "o001": ((2.895, 0.1, 1.738), "wall_raycast"),
    "o002": ((2.912, 0.045, 1.738), "wall_raycast"),
    "o003": ((7.895, 0.1, 1.72), "wall_raycast"),
    "o004": ((7.28, 0.094, 1.562), "wall_raycast"),
    "o005": ((3.002, 3.145, 2.6), "ceiling_plane"),
    "o006": ((4.368, 1.998, 2.6), "ceiling_plane"),
    "o007": ((8.002, 3.22, 2.6), "ceiling_plane"),
    "o008": ((2.002, 6.345, 2.6), "ceiling_plane"),
    "o009": ((0.094, 4.505, 0.241), "wall_raycast"),
    "o010": ((3.902, 4.779, 0.615), "wall_raycast"),
}


def _fixture():
    geometry = ModelGeometry.model_validate_json(
        (EXAMPLES / "model_geometry.json").read_text(encoding="utf-8")
    )
    observations = TypeAdapter(list[Observation]).validate_json(
        (EXAMPLES / "observations.json").read_text(encoding="utf-8")
    )
    panos = {pano.id: pano for pano in geometry.panos}
    rooms = {room.id: room for room in geometry.rooms}
    return geometry, observations, panos, rooms


def test_anchor_fixture_table():
    """All ten anchors in plan 4.6.2, to three decimals, with the default basis."""
    geometry, observations, panos, rooms = _fixture()
    basis = load_basis()
    assert basis.status == "unverified"
    assert len(observations) == 10

    for observation in observations:
        pano = panos[observation.pano_id]
        room = rooms.get(observation.room_id) if observation.room_id else None
        point, method = anchor_from_bbox(
            pano,
            observation.face,
            observation.bbox,
            observation.face_px,
            geometry.walls,
            room,
            label=observation.label,
            basis=basis,
        )
        expected, expected_method = EXPECTED_ANCHORS[observation.id]
        assert point is not None, observation.id
        assert (point.x, point.y, point.z) == pytest.approx(expected, abs=0.0), observation.id
        assert method == expected_method, observation.id
        # The fixture file carries the same result; keep the two in sync.
        assert (point.x, point.y, point.z) == pytest.approx(
            (observation.anchor.x, observation.anchor.y, observation.anchor.z),
            abs=0.0,
        ), observation.id
        assert observation.anchor_method == method

        # Person 2 convenience entry point must produce the same answer.
        wrapper_point, wrapper_method = anchor_observation(observation, geometry, basis)
        assert wrapper_point is not None
        assert (wrapper_point.x, wrapper_point.y, wrapper_point.z) == pytest.approx(
            expected, abs=0.0
        )
        assert wrapper_method == expected_method


def test_fixture_merged_anchor_is_mean():
    """a_o001 in plan 4.6.3 is the mean of o001 and o002 anchors."""
    inventory = json.loads((EXAMPLES / "inventory.json").read_text(encoding="utf-8"))
    merged = next(asset for asset in inventory if asset["id"] == "a_o001")
    expected = (2.904, 0.073, 1.738)
    got = (
        merged["anchor"]["x"],
        merged["anchor"]["y"],
        merged["anchor"]["z"],
    )
    assert got == pytest.approx(expected, abs=0.0)


def test_anchor_horizon_wall_check_from_plan_9_5():
    """A centred face-1 detection from p01 hits y = 4 at (3.0, 3.9, 1.5)."""
    geometry, _, panos, rooms = _fixture()
    # Symmetric about the face centre: u + 0.5 = 1024 and v + 0.5 = 1024.
    bbox = BBox(x0=1000, y0=1000, x1=1047, y1=1047)
    point, method = anchor_from_bbox(
        panos["p01"], 1, bbox, 2048, geometry.walls, rooms["r_living"], basis=load_basis()
    )
    assert (point.x, point.y, point.z) == pytest.approx((3.0, 3.9, 1.5))
    assert method == "wall_raycast"


def test_pixel_ray_centre_and_directions():
    basis = load_basis()
    centre = pixel_ray(basis, 1, 1023.5, 1023.5, 2048)
    assert centre == pytest.approx((0.0, 1.0, 0.0))
    assert pixel_ray(basis, 2, 1023.5, 1023.5, 2048) == pytest.approx((1.0, 0.0, 0.0))
    assert pixel_ray(basis, 3, 1023.5, 1023.5, 2048) == pytest.approx((0.0, -1.0, 0.0))
    assert pixel_ray(basis, 4, 1023.5, 1023.5, 2048) == pytest.approx((-1.0, 0.0, 0.0))


def test_anchor_pixel_uses_top_and_bottom_centre():
    bbox = BBox(x0=100, y0=200, x1=300, y1=400)
    assert anchor_pixel(bbox, None) == (200.0, 300.0)
    assert anchor_pixel(bbox, "window") == (200.0, 300.0)
    assert anchor_pixel(bbox, "ceiling_light") == (200.0, 200.0)
    assert anchor_pixel(bbox, "refrigerator") == (200.0, 400.0)


def test_anchor_ceiling_plane():
    """An upward ray with no walls hits the ceiling at z = ceiling_z."""
    pano = Pano(
        id="p",
        label="p",
        position={"x": 3.0, "y": 2.0, "z": 1.5},
        room_id="r",
    )
    room = Room(
        id="r",
        label="Room",
        floor_id="f1",
        area_m2=24.0,
        height_m=2.6,
        polygon=[Vec2(x=0, y=0), Vec2(x=6, y=0), Vec2(x=6, y=4), Vec2(x=0, y=4)],
        pano_ids=["p"],
    )
    # Bbox near the top of face 1: b is positive, so the ray goes up.
    bbox = BBox(x0=1000, y0=10, x1=1047, y1=60)
    point, method = anchor_from_bbox(pano, 1, bbox, 2048, [], room, label="ceiling_light")
    assert method == "ceiling_plane"
    assert point is not None
    assert point.z == pytest.approx(2.6)
    assert point.x == pytest.approx(3.0, abs=0.02)


def test_anchor_floor_plane():
    """A downward ray with no walls hits the floor at z = floor_z."""
    pano = Pano(
        id="p",
        label="p",
        position={"x": 3.0, "y": 2.0, "z": 1.5},
        room_id="r",
    )
    room = Room(
        id="r",
        label="Room",
        floor_id="f1",
        area_m2=24.0,
        height_m=2.6,
        polygon=[Vec2(x=0, y=0), Vec2(x=6, y=0), Vec2(x=6, y=4), Vec2(x=0, y=4)],
        pano_ids=["p"],
    )
    # Bbox near the bottom of face 1: b is negative, so the ray goes down.
    bbox = BBox(x0=1000, y0=1900, x1=1047, y1=1947)
    point, method = anchor_from_bbox(pano, 1, bbox, 2048, [], room, label="refrigerator")
    assert method == "floor_plane"
    assert point is not None
    assert point.z == pytest.approx(0.0)
    assert point.y > 2.0


def test_anchor_no_walls_horizontal_ray_returns_none():
    pano = Pano(id="p", label="p", position={"x": 3.0, "y": 2.0, "z": 1.5}, room_id=None)
    bbox = BBox(x0=1000, y0=1000, x1=1047, y1=1047)
    point, method = anchor_from_bbox(pano, 1, bbox, 2048, [], None)
    assert point is None
    assert method == "none"


def test_anchor_nothing_within_15_metres():
    pano = Pano(id="p", label="p", position={"x": 0.0, "y": 0.0, "z": 1.5}, room_id=None)
    walls = [WallSegment(a=Vec2(x=0, y=100), b=Vec2(x=10, y=100), floor_id="f1")]
    bbox = BBox(x0=1000, y0=1000, x1=1047, y1=1047)
    point, method = anchor_from_bbox(pano, 1, bbox, 2048, walls, None)
    assert point is None
    assert method == "none"


def test_ray_wall_hit_parallel_and_behind():
    walls = [WallSegment(a=Vec2(x=0, y=1), b=Vec2(x=10, y=1), floor_id="f1")]
    assert ray_wall_hit((0, 0), (1, 0), walls) is None  # parallel
    assert ray_wall_hit((0, 2), (0, 1), walls) is None  # points away
    assert ray_wall_hit((0, 0), (0, 1), walls) == pytest.approx(1.0)


def test_room_centroid_rectangle():
    room = Room(
        id="r",
        label="Room",
        floor_id="f1",
        area_m2=24.0,
        height_m=2.6,
        polygon=[Vec2(x=0, y=0), Vec2(x=6, y=0), Vec2(x=6, y=4), Vec2(x=0, y=4)],
        pano_ids=[],
    )
    centroid = room_centroid(room)
    assert (centroid.x, centroid.y) == (3.0, 2.0)


def test_load_basis_faces_and_camera_height():
    basis = load_basis()
    assert isinstance(basis, FaceBasis)
    assert basis.camera_height_m == 1.5
    assert set(basis.faces) == {1, 2, 3, 4}
    for face in basis.faces.values():
        assert face.up == (0.0, 0.0, 1.0)
