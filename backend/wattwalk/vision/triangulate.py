"""Doorway rescue: fix anchors whose sight line was stopped by a wall that is really an opening.

Matterport floor plans often draw a doorway as solid wall (every edge of 2ibibwUGQAe is type
"wall"). A pano inside a closet that sees the living-room window through the closet door then
anchors the window on the closet wall. When another pano saw the same object cleanly, the two
sight lines meet behind that "wall"; the blocked observation adopts the clean observation's anchor
so dedupe merges them.

Two-view anchors: a scan without walls (some Matterport models have no floor plan) cannot place
windows by casting a sight line onto a wall, so they had no anchor, could not glow, and were never
merged across panoramas (one window seen from three panos became three windows). When two panoramas
see the same kind of object, their sight lines nearly cross at it; the crossing point becomes the
anchor ("two_view") for both, so dedupe merges them.

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


# ---------- two-view anchors (no wall to cast onto) ----------

TWO_VIEW_GAP_M = 0.6    # windows are big: the two sight lines may aim at slightly different points of it
TWO_VIEW_MIN_M = 0.5    # crossing point must be in front of both cameras, at a plausible distance
TWO_VIEW_MAX_M = 10.0
HEIGHT_RANGE_M = (0.2, 2.6)  # above the floor (model z): a window centre or wall item is in this band


def anchor_unplaced(observations: list[Observation], geometry: ModelGeometry) -> dict[str, Observation]:
    """Updated copies (keyed by id) of observations that had no anchor and now have a two-view one.

    For each unanchored observation, the observation of the same label from another panorama whose
    sight line passes closest to it (within TWO_VIEW_GAP_M, in front of both cameras, at a plausible
    height) gives the crossing point. Observations that already have an anchor are never changed.
    """
    from .views import room_for

    try:
        rays = {o.id: _ray(geometry, o) for o in observations}
    except Exception:  # spatial module missing or a different API: change nothing
        return {}
    floor = 0.0
    fixed: dict[str, Observation] = {}
    for a in observations:
        if a.anchor is not None or rays.get(a.id) is None:
            continue
        pano_a, oa, da = rays[a.id]
        best = None
        for b in observations:
            if b.id == a.id or b.label != a.label or b.pano_id == a.pano_id or rays.get(b.id) is None:
                continue
            _, ob, db = rays[b.id]
            res = _closest(oa, da, ob, db)
            if res is None:
                continue
            s, t, gap = res
            if gap > TWO_VIEW_GAP_M or not (TWO_VIEW_MIN_M < s < TWO_VIEW_MAX_M and TWO_VIEW_MIN_M < t < TWO_VIEW_MAX_M):
                continue
            meet = (oa + s * da + ob + t * db) / 2.0
            if not HEIGHT_RANGE_M[0] <= float(meet[2]) - floor <= HEIGHT_RANGE_M[1]:
                continue
            if best is None or gap < best[0]:
                best = (gap, meet)
        if best is None:
            continue
        from ..contracts import Vec3

        meet = best[1]
        anchor = Vec3(x=float(meet[0]), y=float(meet[1]), z=float(meet[2]))
        fixed[a.id] = a.model_copy(update={
            "anchor": anchor, "anchor_method": "two_view", "room_id": room_for(geometry, pano_a, anchor)})
    return fixed
