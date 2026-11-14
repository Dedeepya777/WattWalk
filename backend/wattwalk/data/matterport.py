"""Matterport Model API and Skybox Face adapter.

Owner: Person 1.
See plan/plan.md section 13.1, Appendix A.1.2.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Literal

import requests
from requests.auth import HTTPBasicAuth
from shapely.geometry import Point, Polygon

from wattwalk import config
from wattwalk.contracts import (
    ModelGeometry,
    Pano,
    Quat,
    Room,
    Vec2,
    Vec3,
    WallSegment,
)
from wattwalk.data.index import lookup
from wattwalk.errors import UpstreamError

MATTERPORT_GRAPHQL_URL = "https://api.matterport.com/api/models/graph"

_SKYBOX_CACHE: dict[tuple[str, str], tuple[float, dict[str, list[str]]]] = {}
# Signed skybox URLs carry their expiry ("t=2-<signature>-<unix expiry>-..."); measured lifetime is
# 300 s. Reuse a cached list only while every URL in it has at least this much life left.
SKYBOX_MIN_LIFE_S = 60
SKYBOX_FALLBACK_TTL_S = 240  # when an expiry cannot be read from the URLs
# Status codes Matterport's CDN returns for a stale or invalid signed URL: refresh the URLs once.
STALE_URL_STATUSES = (401, 403, 410)


def _url_expiry(url: str) -> int | None:
    m = re.search(r"[?&]t=\d+-[0-9a-fA-F]+-(\d{9,})-", url)
    return int(m.group(1)) if m else None


def _skybox_cache_valid(cached_time: float, urls: dict[str, list[str]], now: float) -> bool:
    expiries = [e for vs in urls.values() for u in vs if (e := _url_expiry(u)) is not None]
    if expiries:
        return min(expiries) - now > SKYBOX_MIN_LIFE_S
    return now - cached_time < SKYBOX_FALLBACK_TTL_S


def _record_health(ok: bool, detail: str = "") -> None:
    mode = config.effective_data_mode()
    if mode == "fixture":
        return
    try:
        from wattwalk import health_registry
        health_registry.record("matterport", ok, detail)
    except (ImportError, AttributeError):
        pass


def graph(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """Execute a GraphQL query against Matterport Model API with retries and basic auth."""
    key = config.MATTERPORT_API_KEY
    token = config.MATTERPORT_API_TOKEN
    if not key or not token:
        _record_health(False, "401")
        raise UpstreamError("matterport", retryable=False, message="Missing Matterport API credentials", http_status=401)

    timeout = config.TIMEOUTS_S.get("matterport", 30)
    auth = HTTPBasicAuth(key, token)

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(
                MATTERPORT_GRAPHQL_URL,
                json={"query": query, "variables": variables},
                auth=auth,
                timeout=timeout,
            )
            if resp.status_code in (401, 403):
                _record_health(False, str(resp.status_code))
                raise UpstreamError("matterport", retryable=False, message=f"Auth error: {resp.text}", http_status=resp.status_code)
            if resp.status_code >= 500:
                time.sleep(1.0 * (2**attempt))
                continue
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data and not data.get("data"):
                _record_health(False, "errors")
                raise UpstreamError("matterport", retryable=False, message=str(data["errors"]))
            _record_health(True)
            return data.get("data", {})
        except UpstreamError:
            raise
        except Exception as e:
            last_error = e
            time.sleep(1.0 * (2**attempt))

    _record_health(False, type(last_error).__name__ if last_error else "503")
    raise UpstreamError(
        "matterport",
        retryable=True,
        message=f"Matterport request failed after retries: {last_error}",
        http_status=503,
    )



def skybox_urls(sid: str, resolution: str) -> dict[str, list[str]]:
    """Query and cache panorama skybox face image URLs."""
    now = time.time()
    cache_key = (sid, resolution)
    if cache_key in _SKYBOX_CACHE:
        cached_time, cached_urls = _SKYBOX_CACHE[cache_key]
        if _skybox_cache_valid(cached_time, cached_urls, now):
            return cached_urls

    if resolution not in ("2k", "4k"):
        raise ValueError(f"resolution must be 2k or 4k, got {resolution!r}")
    # Plan F.2: the resolution is a literal in the query string; children is a list of 6 signed URLs
    # in face order 0 to 5. A pano whose skybox status is not "available" has no faces.
    query = 'query Skybox($id: ID!) { model(id: $id) { panoLocations { id skybox(resolution: "%s") { status children } } } }' % resolution
    data = graph(query, {"id": sid})
    panos_data = (data.get("model") or {}).get("panoLocations") or []
    result: dict[str, list[str]] = {}
    for p in panos_data:
        p_id = p.get("id")
        sky = p.get("skybox") or {}
        if p_id:
            children = sky.get("children") or []
            result[p_id] = [str(u) for u in children] if sky.get("status") == "available" else []

    _SKYBOX_CACHE[cache_key] = (now, result)
    return result


def _chain_edges_to_polygon(edges: list[dict[str, Any]]) -> list[Vec2]:
    """Chain unordered segment edges into a closed 2D polygon."""
    if not edges:
        return [Vec2(x=0.0, y=0.0), Vec2(x=1.0, y=0.0), Vec2(x=1.0, y=1.0), Vec2(x=0.0, y=1.0)]

    points: list[tuple[float, float]] = []
    for edge in edges:
        v = edge.get("vertices", [])
        if len(v) >= 2:
            p1 = (round(float(v[0]["x"]), 4), round(float(v[0]["y"]), 4))
            p2 = (round(float(v[1]["x"]), 4), round(float(v[1]["y"]), 4))
            if not points:
                points.extend([p1, p2])
            else:
                if p1 == points[-1]:
                    points.append(p2)
                elif p2 == points[-1]:
                    points.append(p1)
                else:
                    points.append(p1)

    # Ensure at least 3 points
    if len(points) < 3:
        points = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]

    # Remove trailing duplicate if closed
    if len(points) > 3 and points[0] == points[-1]:
        points.pop()

    return [Vec2(x=pt[0], y=pt[1]) for pt in points]


def _quat(raw: dict | None) -> Quat | None:
    """Pano rotation from the Model API; ``None`` when missing or not a usable quaternion."""
    if not raw:
        return None
    try:
        q = Quat(x=float(raw["x"]), y=float(raw["y"]), z=float(raw["z"]), w=float(raw["w"]))
    except (KeyError, TypeError, ValueError):
        return None
    if abs(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w - 1.0) > 0.05:
        return None
    return q


def _ring_from_edge_ids(edge_ids: list[str], edges: dict[str, tuple[str, str]],
                        vertices: dict[str, tuple[float, float]]) -> list[tuple[float, float]]:
    """Chain a room's boundary edges into a ring of vertex positions (plan 8.1.1): start with the first
    edge, then repeatedly append the unused edge that shares the ring's last vertex."""
    pairs = [edges[e] for e in edge_ids if e in edges]
    if not pairs:
        return []
    ring = list(pairs[0])
    used = {0}
    while True:
        nxt = next((i for i, (a, b) in enumerate(pairs) if i not in used and ring[-1] in (a, b)), None)
        if nxt is None:
            break
        a, b = pairs[nxt]
        used.add(nxt)
        ring.append(b if a == ring[-1] else a)
    if len(ring) > 1 and ring[-1] == ring[0]:
        ring.pop()
    return [vertices[v] for v in ring if v in vertices]


def get_geometry(sid: str) -> ModelGeometry:
    """Retrieve 3D model geometry (rooms, panos, walls) from fixture or live Matterport API."""
    mode = config.effective_data_mode()

    if mode == "fixture":
        if sid == config.FIXTURE_SID:
            fixture_path = config.EXAMPLES_DIR / "model_geometry.json"
            with open(fixture_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["status"] = "fixture"
            return ModelGeometry.model_validate(data)

        live_fix = config.FIXTURES_DIR / "live" / sid / "geometry.json"
        if live_fix.exists():
            with open(live_fix, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["status"] = "fixture"
            return ModelGeometry.model_validate(data)

        raise ValueError(f"no geometry fixture for sid {sid}")

    # Live mode: check local cache
    cache_path = config.CACHE_DIR / "geometry" / f"{sid}.json"
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cached = ModelGeometry.model_validate(data)
        # Caches written before pano rotations were fetched would anchor every pin with the wrong
        # face directions; refetch those once.
        if not cached.panos or any(p.rotation is not None for p in cached.panos):
            return cached

    # Query live Matterport GraphQL API (plan Appendix F.1). Walls and vertex positions live on floors;
    # rooms reference boundary edge ids; classifications is a list with confidences.
    query = """
    query Geometry($id: ID!) {
      model(id: $id) {
        id name
        address { address locality administrativeArea postalCode }
        geolocation { lat long }
        floors { id label
                 vertices { id position { x y } }
                 edges { id type thickness vertices { id } } }
        rooms { id floor { id }
                classifications { label confidence }
                boundary { edges { id } }
                dimensions(units: metric) { areaFloor width depth height } }
        panoLocations { id label position { x y z } rotation { x y z w } }
      }
    }
    """
    raw_data = graph(query, {"id": sid})
    model_data = raw_data.get("model")
    if not model_data:
        raise UpstreamError("matterport", retryable=False, message=f"Model {sid} not found in Matterport API", http_status=404)

    idx = lookup(sid)
    addr_str = ((model_data.get("address") or {}).get("address") or "").strip()
    if not addr_str and idx:
        addr_str = idx.address

    lat = None
    lon = None
    geo = model_data.get("geolocation") or {}
    try:
        lat = float(geo["lat"]) if geo.get("lat") not in (None, "") else None
        lon = float(geo["long"]) if geo.get("long") not in (None, "") else None
    except (TypeError, ValueError):
        lat = lon = None
    if lat is None and idx:
        lat = idx.lat
        lon = idx.lon

    # Vertex positions and edges per floor; every edge of type "wall" is a WallSegment (plan 7.4).
    vertices: dict[str, tuple[float, float]] = {}
    edges: dict[str, tuple[str, str]] = {}
    walls: list[WallSegment] = []
    for floor in model_data.get("floors") or []:
        floor_id = floor.get("id", "f1")
        floor_vertices = {v["id"]: (float(v["position"]["x"]), float(v["position"]["y"]))
                          for v in floor.get("vertices") or [] if v.get("position")}
        vertices.update(floor_vertices)
        for e in floor.get("edges") or []:
            ids = [v["id"] for v in e.get("vertices") or []]
            if len(ids) != 2:
                continue
            edges[e["id"]] = (ids[0], ids[1])
            if e.get("type") == "wall" and ids[0] in floor_vertices and ids[1] in floor_vertices:
                (ax, ay), (bx, by) = floor_vertices[ids[0]], floor_vertices[ids[1]]
                walls.append(WallSegment(a=Vec2(x=ax, y=ay), b=Vec2(x=bx, y=by), floor_id=floor_id))

    rooms: list[Room] = []
    shapely_rooms: list[tuple[Room, Polygon]] = []
    for r in model_data.get("rooms") or []:
        classes = sorted(r.get("classifications") or [], key=lambda c: -(c.get("confidence") or 0))
        label = (classes[0].get("label") if classes else None) or "Unlabelled"
        if label == "Void":
            continue  # layout artifacts (plan 7.4)
        ring = _ring_from_edge_ids([e["id"] for e in (r.get("boundary") or {}).get("edges") or []], edges, vertices)
        if len(ring) < 3:
            continue  # no polygon: excluded (plan 8.1.1)
        sh_poly = Polygon(ring).buffer(0)  # repairs self-intersections (plan 8.1.1)
        dims = r.get("dimensions") or {}
        area_floor = dims.get("areaFloor")
        area_m2 = float(area_floor) if area_floor else round(float(sh_poly.area), 2)
        height_val = dims.get("height")
        room_obj = Room(
            id=r["id"],
            label=label,
            floor_id=(r.get("floor") or {}).get("id", "f1"),
            area_m2=area_m2,
            height_m=float(height_val) if height_val else None,
            polygon=[Vec2(x=x, y=y) for x, y in ring],
            pano_ids=[],
        )
        rooms.append(room_obj)
        shapely_rooms.append((room_obj, sh_poly))

    # Assign each pano to the smallest room containing it (rooms can overlap at their edges)
    panos: list[Pano] = []
    for pl in model_data.get("panoLocations", []):
        pos = pl.get("position", {})
        px = float(pos.get("x", 0.0))
        py = float(pos.get("y", 0.0))
        pz = float(pos.get("z", 0.0))
        pt = Point(px, py)

        assigned_room_id: str | None = None
        containing = sorted((ro for ro, poly in shapely_rooms if poly.covers(pt)), key=lambda ro: ro.area_m2)
        if containing:
            assigned_room_id = containing[0].id
            containing[0].pano_ids.append(pl.get("id", ""))

        pano_obj = Pano(
            id=pl.get("id", ""),
            label=pl.get("label", ""),
            position=Vec3(x=px, y=py, z=pz),
            room_id=assigned_room_id,
            rotation=_quat(pl.get("rotation")),
        )
        panos.append(pano_obj)

    geometry = ModelGeometry(
        schema_version="1.0.0",
        sid=sid,
        address=addr_str or "Unknown Address",
        lat=lat,
        lon=lon,
        rooms=rooms,
        panos=panos,
        walls=walls,
        status="live",
    )

    # Persist cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(geometry.model_dump_json(indent=2))

    return geometry


def get_face_image(sid: str, pano_id: str, face: int, resolution: Literal["2k", "4k"]) -> Path:
    """Download and return local path for a skybox face image."""
    mode = config.effective_data_mode()
    if mode == "fixture":
        raise ValueError("fixture mode: face images are not available or needed in fixture mode")

    cache_dir = config.CACHE_DIR / "faces" / sid
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{pano_id}_{face}_{resolution}.jpg"
    if cache_path.exists():
        return cache_path

    urls = skybox_urls(sid, resolution)
    pano_urls = urls.get(pano_id, [])
    if not pano_urls or face >= len(pano_urls):
        raise UpstreamError("matterport", retryable=False, message=f"No image URL found for pano {pano_id} face {face}")

    img_url = pano_urls[face]
    try:
        resp = requests.get(img_url, timeout=30)
        if resp.status_code in STALE_URL_STATUSES:
            # Stale or invalid signed URL (410 Gone once it expires): fetch fresh URLs and retry once
            _SKYBOX_CACHE.pop((sid, resolution), None)
            urls = skybox_urls(sid, resolution)
            pano_urls = urls.get(pano_id, [])
            if pano_urls and face < len(pano_urls):
                resp = requests.get(pano_urls[face], timeout=30)

        resp.raise_for_status()
        with open(cache_path, "wb") as f:
            f.write(resp.content)
        _record_health(True)
        return cache_path
    except Exception as e:
        _record_health(False, type(e).__name__)
        raise UpstreamError("matterport", retryable=True, message=f"Failed to download face image: {e}")

