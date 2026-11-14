"""View selection: which panoramas to inspect (plan 8.1). Owner: Person 2."""
from __future__ import annotations

import math

from ..contracts import ModelGeometry, Observation, Pano, Room, Vec2
from .deps import face_forward_xy
from .types import ViewTask

LARGE_ROOM_M2 = 20.0
NO_ROOMS_CAP = 20
NEIGHBOR_RADIUS_M = 3.0


def polygon_centroid(points: list[Vec2]) -> tuple[float, float]:
    """Area-weighted centroid (shoelace); falls back to the vertex mean for degenerate polygons."""
    a = cx = cy = 0.0
    n = len(points)
    for i in range(n):
        p, q = points[i], points[(i + 1) % n]
        cross = p.x * q.y - q.x * p.y
        a += cross
        cx += (p.x + q.x) * cross
        cy += (p.y + q.y) * cross
    if abs(a) < 1e-12:
        return sum(p.x for p in points) / n, sum(p.y for p in points) / n
    return cx / (3 * a), cy / (3 * a)


def _dist_xy(p: Pano, x: float, y: float) -> float:
    return math.hypot(p.position.x - x, p.position.y - y)


def _room_panos(geometry: ModelGeometry, room: Room) -> list[Pano]:
    by_id = {p.id: p for p in geometry.panos}
    return [by_id[pid] for pid in room.pano_ids if pid in by_id]


def plan_views(geometry: ModelGeometry) -> list[ViewTask]:
    if not geometry.rooms:
        panos = geometry.panos
        if len(panos) > NO_ROOMS_CAP:
            panos = [panos[i * len(panos) // NO_ROOMS_CAP] for i in range(NO_ROOMS_CAP)]
        return [ViewTask(room_id=None, pano_id=p.id, reason="no_rooms_fallback") for p in panos]

    tasks: list[ViewTask] = []
    for room in geometry.rooms:
        panos = _room_panos(geometry, room)
        if not panos:
            continue  # coverage reports not_visited
        cx, cy = polygon_centroid(room.polygon)
        best = min(panos, key=lambda p: (_dist_xy(p, cx, cy), p.id))
        tasks.append(ViewTask(room_id=room.id, pano_id=best.id, reason="best_view"))
        others = [p for p in panos if p.id != best.id]
        if room.area_m2 >= LARGE_ROOM_M2 and others:
            # farthest from the best view; ties go to the lower pano id
            far = min(others, key=lambda p: (-_dist_xy(p, best.position.x, best.position.y), p.id))
            tasks.append(ViewTask(room_id=room.id, pano_id=far.id, reason="second_view_large_room"))
    return tasks


def neighbor_pano(geometry: ModelGeometry, observation: Observation, tried_panos: set[str]) -> Pano | None:
    """Nearest other pano in the same room, or else any pano within 3 m (plan 8.4.2 neighbor_view)."""
    by_id = {p.id: p for p in geometry.panos}
    origin = by_id.get(observation.pano_id)
    if origin is None:
        return None
    target = observation.anchor or origin.position
    skip = tried_panos | {observation.pano_id}
    candidates = [p for p in geometry.panos if p.id not in skip]
    same_room = [p for p in candidates if observation.room_id is not None and p.room_id == observation.room_id]
    if same_room:
        return min(same_room, key=lambda p: (_dist_xy(p, origin.position.x, origin.position.y), p.id))
    near = [p for p in candidates if _dist_xy(p, target.x, target.y) <= NEIGHBOR_RADIUS_M]
    return min(near, key=lambda p: (_dist_xy(p, target.x, target.y), p.id)) if near else None


ROOM_EDGE_TOLERANCE_M = 0.3  # wall anchors sit on a room's boundary; count them as inside that room


def _inside(x: float, y: float, poly: list[Vec2]) -> bool:
    hit = False
    for p, q in zip(poly, poly[1:] + poly[:1]):
        if (p.y > y) != (q.y > y) and x < (q.x - p.x) * (y - p.y) / (q.y - p.y) + p.x:
            hit = not hit
    return hit


def _edge_distance(x: float, y: float, poly: list[Vec2]) -> float:
    best = math.inf
    for p, q in zip(poly, poly[1:] + poly[:1]):
        dx, dy = q.x - p.x, q.y - p.y
        t = max(0.0, min(1.0, ((x - p.x) * dx + (y - p.y) * dy) / (dx * dx + dy * dy))) if dx or dy else 0.0
        best = min(best, math.hypot(x - (p.x + t * dx), y - (p.y + t * dy)))
    return best


def room_for(geometry: ModelGeometry, pano: Pano, anchor) -> str | None:
    """The room an object is in. Plan 7.6 uses the pano's room, which is wrong for objects seen through
    a doorway (a closet pano seeing the main window counted it in the closet, so dedupe could never
    merge it). With an anchor: keep the pano's room if the anchor is in it or on its boundary,
    otherwise use the room that contains the anchor. Without an anchor: the pano's room."""
    if anchor is None:
        return pano.room_id
    own = next((r for r in geometry.rooms if r.id == pano.room_id), None)
    if own is not None and (_inside(anchor.x, anchor.y, own.polygon)
                            or _edge_distance(anchor.x, anchor.y, own.polygon) <= ROOM_EDGE_TOLERANCE_M):
        return own.id
    containing = [r for r in geometry.rooms if _inside(anchor.x, anchor.y, r.polygon)]
    return min(containing, key=lambda r: r.area_m2).id if containing else pano.room_id


def face_toward(pano: Pano, x: float, y: float) -> int:
    """The horizon face whose centre ray points closest to (x, y)."""
    dx, dy = x - pano.position.x, y - pano.position.y
    forwards = face_forward_xy()
    return max(forwards, key=lambda f: forwards[f][0] * dx + forwards[f][1] * dy)
