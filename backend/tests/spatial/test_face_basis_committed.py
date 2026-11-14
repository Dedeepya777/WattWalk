"""Regression checks for the committed face basis (P4-7).

The committed file is the planning default while status is "unverified".  If a later live
calibration changes the basis, the expected anchors in plan 4.6.2 must be regenerated in a separate
test instead of silently keeping the old table.
"""
from __future__ import annotations

import math

import pytest

from wattwalk.spatial.geometry import anchor_from_bbox, load_basis

DEFAULT_FACES = {
    1: ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),
    2: ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),
    3: ((0.0, -1.0, 0.0), (-1.0, 0.0, 0.0)),
    4: ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
}


def test_committed_face_basis_is_well_formed():
    basis = load_basis()
    assert basis.status in {"unverified", "calibrated"}
    if basis.status == "calibrated":
        assert basis.calibrated_on, "a calibrated basis needs calibrated_on"
        assert basis.residual_m is not None
        assert basis.residual_m <= 0.30
    else:
        assert basis.residual_m is None

    for face in (1, 2, 3, 4):
        directions = basis.faces[face]
        forward = directions.forward
        right = directions.right
        up = directions.up
        assert math.isclose(math.hypot(*forward), 1.0, abs_tol=1e-9)
        assert math.isclose(math.hypot(*right), 1.0, abs_tol=1e-9)
        assert math.isclose(sum(a * b for a, b in zip(forward, right)), 0.0, abs_tol=1e-9)
        assert up == pytest.approx((0.0, 0.0, 1.0), abs=1e-12)
        # right = forward x up keeps the basis right-handed.
        cross = (
            forward[1] * 1.0 - forward[2] * 0.0,
            forward[2] * 0.0 - forward[0] * 1.0,
            forward[0] * 0.0 - forward[1] * 0.0,
        )
        assert cross == pytest.approx(right, abs=1e-9)


def test_committed_basis_keeps_fixture_anchor_table():
    """When the committed basis is the planning default, plan 4.6.2 anchors must still match."""
    basis = load_basis()
    is_default = all(
        tuple(basis.faces[face].forward) == DEFAULT_FACES[face][0]
        and tuple(basis.faces[face].right) == DEFAULT_FACES[face][1]
        for face in (1, 2, 3, 4)
    )
    if not is_default:
        pytest.skip(
            "committed basis differs from the planning default; regenerate the plan 4.6.2 "
            "anchor expectations in a dedicated test"
        )

    from tests.spatial.test_geometry import EXPECTED_ANCHORS, _fixture

    geometry, observations, panos, rooms = _fixture()
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
