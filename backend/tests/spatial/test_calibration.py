"""Calibration tests for Person 4 (plan 9.6 and Appendix H.5)."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from wattwalk.contracts import Pano, Room, Vec2
from wattwalk.spatial.calibrate import (
    CandidateScore,
    Correspondence,
    candidate_bases,
    choose_basis,
    evaluate_candidates,
    read_points_csv,
    score_candidate,
)
from wattwalk.spatial.geometry import FaceBasis, load_basis, pixel_ray

FACE_PX = 2048


def _room() -> Room:
    return Room(
        id="r",
        label="Room",
        floor_id="f1",
        area_m2=200.0,
        height_m=2.6,
        polygon=[
            Vec2(x=-5, y=-5),
            Vec2(x=20, y=-5),
            Vec2(x=20, y=20),
            Vec2(x=-5, y=20),
        ],
        pano_ids=["pa", "pb"],
    )


def _panos() -> dict[str, Pano]:
    return {
        "pa": Pano(id="pa", label="a", position={"x": 0.0, "y": 0.0, "z": 1.5}),
        "pb": Pano(id="pb", label="b", position={"x": 3.0, "y": 0.0, "z": 1.5}),
    }


def _pixel_for_point(
    basis: FaceBasis, pano: Pano, point: tuple[float, float, float], point_id: str
) -> Correspondence:
    origin = np.array([pano.position.x, pano.position.y, pano.position.z], dtype=float)
    direction = np.array(point, dtype=float) - origin
    direction /= np.linalg.norm(direction)
    ranked = sorted(range(1, 5), key=lambda face: -float(np.dot(direction, basis.faces[face].forward)))
    for face in ranked:
        directions = basis.faces[face]
        forward = np.asarray(directions.forward)
        right = np.asarray(directions.right)
        up = np.asarray(directions.up)
        fdot = float(np.dot(direction, forward))
        if fdot <= 0.15:
            continue
        a = float(np.dot(direction, right)) / fdot
        b = float(np.dot(direction, up)) / fdot
        if abs(a) <= 0.92 and abs(b) <= 0.92:
            u = (a + 1.0) * FACE_PX / 2.0 - 0.5
            v = (1.0 - b) * FACE_PX / 2.0 - 0.5
            return Correspondence(pano.id, face, u, v, point_id)
    raise AssertionError(f"point {point} is not visible from {pano.id}")


def _synthetic_pairs(basis: FaceBasis):
    panos = _panos()
    points = {
        "p1": (6.0, 4.0, 1.6),
        "p2": (5.0, 7.0, 0.6),
        "p3": (7.0, 2.0, 2.1),
        "p4": (8.0, 6.0, 1.2),
    }
    pairs = []
    for point_id, point in points.items():
        pairs.append(
            (
                _pixel_for_point(basis, panos["pa"], point, point_id),
                _pixel_for_point(basis, panos["pb"], point, point_id),
            )
        )
    return pairs, panos


def test_candidate_bases_are_eight_and_include_default():
    bases = candidate_bases()
    assert len(bases) == 8
    defaults = load_basis()
    matches = [
        basis
        for basis in bases
        if all(
            tuple(basis.faces[face].forward) == tuple(defaults.faces[face].forward)
            and tuple(basis.faces[face].right) == tuple(defaults.faces[face].right)
            for face in (1, 2, 3, 4)
        )
    ]
    assert len(matches) == 1


def test_calibration_synthetic_recovers_default_basis():
    known = load_basis()
    pairs, panos = _synthetic_pairs(known)
    scores = evaluate_candidates(pairs, panos, [_room()])
    best = scores[0]
    assert best.mean == pytest.approx(0.0, abs=1e-6)
    assert best.inside_ratio == 1.0
    assert best.basis.faces[1].forward == known.faces[1].forward
    assert best.basis.faces[1].right == known.faces[1].right

    winner, verdict = choose_basis(scores)
    assert winner is not None, verdict
    assert winner.faces[3].forward == known.faces[3].forward
    assert verdict == "accepted"


def test_calibration_synthetic_recovers_rotated_basis():
    known = candidate_bases()[5]
    pairs, panos = _synthetic_pairs(known)
    scores = evaluate_candidates(pairs, panos, [_room()])
    assert scores[0].mean == pytest.approx(0.0, abs=1e-6)
    assert scores[0].basis.faces[2].forward == known.faces[2].forward
    winner, verdict = choose_basis(scores)
    assert winner is not None, verdict


def test_score_rejects_pairs_with_point_outside_room():
    known = load_basis()
    pairs, panos = _synthetic_pairs(known)
    tiny_room = Room(
        id="tiny",
        label="Tiny",
        floor_id="f1",
        area_m2=1.0,
        height_m=2.6,
        polygon=[Vec2(x=0, y=0), Vec2(x=1, y=0), Vec2(x=1, y=1), Vec2(x=0, y=1)],
        pano_ids=[],
    )
    score = score_candidate(known, pairs, panos, [tiny_room])
    assert score.inside_ratio == 0.0
    winner, verdict = choose_basis([score])
    assert winner is None
    assert "inside the room" in verdict


def test_choose_basis_rejects_high_residual():
    basis = load_basis()
    score = CandidateScore(basis=basis, mean=0.45, inside_ratio=1.0, n_pairs=3)
    winner, verdict = choose_basis([score])
    assert winner is None
    assert "0.30" in verdict


def test_choose_basis_rejects_ambiguous_second_best():
    bases = candidate_bases()
    scores = [
        CandidateScore(basis=bases[0], mean=0.10, inside_ratio=1.0, n_pairs=3),
        CandidateScore(basis=bases[1], mean=0.15, inside_ratio=1.0, n_pairs=3),
    ]
    winner, verdict = choose_basis(scores)
    assert winner is None
    assert "2x" in verdict


def test_choose_basis_rejects_two_perfect_candidates():
    bases = candidate_bases()
    scores = [
        CandidateScore(basis=bases[0], mean=0.0, inside_ratio=1.0, n_pairs=3),
        CandidateScore(basis=bases[1], mean=0.0, inside_ratio=1.0, n_pairs=3),
    ]
    winner, verdict = choose_basis(scores)
    assert winner is None
    assert "ambiguous" in verdict


def test_read_points_csv(tmp_path: Path):
    path = tmp_path / "points.csv"
    path.write_text(
        "pano,face,u,v,point_id\n"
        "p01,1,100,200,p1\n"
        "p02,2,300,400,p1\n"
        "p01,3,500,600,p2\n"
        "p02,4,700,800,p2\n"
        "p01,1,900,1000,p3\n"
        "p02,2,1100,1200,p3\n",
        encoding="utf-8",
    )
    pairs = read_points_csv(path)
    assert len(pairs) == 3
    assert pairs[0][0].point_id == "p1"
    assert pairs[2][1].face == 2


def test_pixel_ray_is_normalised():
    known = load_basis()
    ray = pixel_ray(known, 1, 123.5, 456.5, FACE_PX)
    assert float(np.linalg.norm(ray)) == pytest.approx(1.0)
