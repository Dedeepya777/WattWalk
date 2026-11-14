"""Per-pano rotation and camera height (real Model API panoramas)."""
import math

import pytest

from wattwalk.contracts import BBox, Pano, Quat, Vec3, WallSegment, Vec2
from wattwalk.data.matterport import _quat
from wattwalk.spatial.geometry import (
    anchor_from_bbox,
    basis_for_pano,
    camera_height,
    face_forward_xy,
    load_basis,
)

N = 2048
CENTRE = BBox(x0=1000, y0=1000, x1=1048, y1=1048)  # pixel centre ~ (1024, 1024): straight ahead


def _yaw(deg: float) -> Quat:
    half = math.radians(deg) / 2.0
    return Quat(x=0.0, y=0.0, z=math.sin(half), w=math.cos(half))


def _pano(z: float = 1.3, rotation: Quat | None = None) -> Pano:
    return Pano(id="p", label="1", position=Vec3(x=0.0, y=0.0, z=z), room_id=None, rotation=rotation)


def test_pano_without_rotation_keeps_global_basis():
    basis = load_basis()
    assert basis_for_pano(basis, _pano()) is basis
    assert Pano.model_validate(_pano().model_dump()).model_dump().keys() == {"id", "label", "position", "room_id"}


@pytest.mark.parametrize(
    "yaw, face1",
    [(0.0, (1.0, 0.0)), (90.0, (0.0, 1.0)), (180.0, (-1.0, 0.0)), (-90.0, (0.0, -1.0))],
)
def test_face1_follows_pano_yaw(yaw, face1):
    forwards = face_forward_xy(_pano(rotation=_yaw(yaw)))
    assert forwards[1] == pytest.approx(face1, abs=1e-9)
    # faces go clockwise seen from above: face 2 is face 1 turned -90 degrees
    fx, fy = face1
    assert forwards[2] == pytest.approx((fy, -fx), abs=1e-9)


def test_rotated_basis_stays_orthonormal_and_right_handed():
    basis = basis_for_pano(load_basis(), _pano(rotation=_yaw(47.0)))
    for face in (1, 2, 3, 4):
        d = basis.faces[face]
        assert math.hypot(*d.forward) == pytest.approx(1.0)
        assert sum(a * b for a, b in zip(d.forward, d.right)) == pytest.approx(0.0, abs=1e-9)
        assert d.up == pytest.approx((0.0, 0.0, 1.0))


def test_anchor_uses_rotation_to_pick_the_wall():
    # a wall 3 m along +y; with a 90 degree yaw face 1 looks at it
    walls = [WallSegment(a=Vec2(x=-5, y=3), b=Vec2(x=5, y=3), floor_id="f")]
    point, method = anchor_from_bbox(_pano(rotation=_yaw(90.0)), 1, CENTRE, N, walls, None)
    assert method == "wall_raycast"
    assert point.y == pytest.approx(2.9, abs=0.01)
    assert abs(point.x) < 0.05
    unrotated, _ = anchor_from_bbox(_pano(rotation=_yaw(0.0)), 1, CENTRE, N, walls, None)
    assert unrotated is None  # face 1 now looks along +x, away from the wall


def test_camera_height_is_pano_z_in_band_else_constant():
    basis = load_basis()
    assert camera_height(_pano(z=1.27), basis) == pytest.approx(1.27)
    assert camera_height(_pano(z=4.3), basis) == pytest.approx(basis.camera_height_m)


def test_floor_standing_object_lands_on_floor_zero():
    bottom = BBox(x0=1000, y0=1500, x1=1048, y1=1700)  # below the horizon
    point, method = anchor_from_bbox(
        _pano(z=1.25, rotation=_yaw(0.0)), 1, bottom, N, [], None, label="refrigerator"
    )
    assert method == "floor_plane"
    assert point.z == pytest.approx(0.0, abs=1e-3)


def test_quat_parsing_rejects_bad_values():
    assert _quat({"x": 0, "y": 0, "z": 0.7071068, "w": 0.7071068}) == Quat(x=0, y=0, z=0.7071068, w=0.7071068)
    assert _quat(None) is None
    assert _quat({"x": 0, "y": 0, "z": 0}) is None
    assert _quat({"x": 0, "y": 0, "z": 0, "w": 3}) is None
