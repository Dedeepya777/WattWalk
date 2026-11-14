"""Doorway rescue: fix anchors whose sight line was stopped by a wall that is really an opening.

Matterport floor plans often draw a doorway as solid wall (every edge of 2ibibwUGQAe is type
"wall"). A pano inside a closet that sees the living-room window through the closet door then
anchors the window on the closet wall. When another pano saw the same object cleanly, the two
sight lines meet behind that "wall"; the blocked observation adopts the clean observation's anchor
so dedupe merges them.

Owner: Person 2. Uses Person 4's ray maths (spatial.geometry) and changes no anchor otherwise.
"""
from __future__ import annotations

import math

import numpy as np

from ..contracts import ModelGeometry, Observation

MAX_GAP_M = 0.25        # sight lines must pass this close to each other in 3D
BEYOND_WALL_M = 0.5     # the meeting point must be this far behind the blocked wall hit
MIN_RANGE_M = 0.3       # and in front of both cameras
MAX_RANGE_M = 15.0
CLEAN_AGREE_M = 0.5     # the clean observation's own anchor must agree with the meeting point


def _ray(geometry: ModelGeometry, obs: Observation):
    from ..spatial.geometry import anchor_pixel, basis_for_pano, load_basis, pixel_ray  # Person 4

    pano = next((p for p in geometry.panos if p.id == obs.pano_id), None)
    if pano is None:
        return None
    basis = basis_for_pano(load_basis(), pano)
    u, v = anchor_pixel(obs.bbox, obs.label)
    origin = np.array([pano.position.x, pano.position.y, pano.position.z], dtype=float)
    return pano, origin, pixel_ray(basis, obs.face, u, v, obs.face_px)


def _closest(o1, d1, o2, d2):
    """Parameters (s, t) and gap of the closest points of two lines o + s*d (unit d)."""
    w = o1 - o2
    b = float(d1 @ d2)
    denom = 1.0 - b * b
    if denom < 1e-9:  # parallel
        return None
    d, e = float(d1 @ w), float(d2 @ w)
    s = (b * e - d) / denom
    t = (e - b * d) / denom
    gap = float(np.linalg.norm((o1 + s * d1) - (o2 + t * d2)))
    return s, t, gap


def rescue_blocked(observations: list[Observation], geometry: ModelGeometry) -> dict[str, Observation]:
    """Updated copies of the observations whose wall hit was really an opening, keyed by id.

    Works on the original anchors only (one pass), so a rescued anchor never rescues another.
    """
    try:
        rays = {o.id: _ray(geometry, o) for o in observations if o.anchor is not None}
    except Exception:  # spatial module missing or a different API: change nothing
        return {}
    from .views import room_for

    fixed: dict[str, Observation] = {}
    for a in observations:
        if a.anchor_method != "wall_raycast" or rays.get(a.id) is None:
            continue
        pano_a, oa, da = rays[a.id]
        hit = math.dist((oa[0], oa[1], oa[2]), (a.anchor.x, a.anchor.y, a.anchor.z))
        best = None
        for b in observations:
            if b.id == a.id or b.label != a.label or b.pano_id == a.pano_id or rays.get(b.id) is None:
                continue
            _, ob, db = rays[b.id]
            res = _closest(oa, da, ob, db)
            if res is None:
                continue
            s, t, gap = res
            if gap > MAX_GAP_M or s < hit + BEYOND_WALL_M or s > MAX_RANGE_M or not MIN_RANGE_M < t < MAX_RANGE_M:
                continue
            meet = (oa + s * da + ob + t * db) / 2.0
            if math.dist(tuple(meet), (b.anchor.x, b.anchor.y, b.anchor.z)) > CLEAN_AGREE_M:
                continue  # the other view is not clean either
            if best is None or gap < best[0]:
                best = (gap, b)
        if best is not None:
            anchor = best[1].anchor
            fixed[a.id] = a.model_copy(update={"anchor": anchor, "room_id": room_for(geometry, pano_a, anchor)})
    return fixed
