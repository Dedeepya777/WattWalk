"""Matterport Model API and Skybox Face adapter.

Owner: Person 1.
See plan/plan.md section 13.1, Appendix A.1.2.
"""
from __future__ import annotations

import json
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
    Room,
    Vec2,
    Vec3,
    WallSegment,
)
from wattwalk.data.index import lookup
from wattwalk.errors import UpstreamError

MATTERPORT_GRAPHQL_URL = "https://api.matterport.com/api/models/graph"

_SKYBOX_CACHE: dict[tuple[str, str], tuple[float, dict[str, list[str]]]] = {}


def graph(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """Execute a GraphQL query against Matterport Model API with retries and basic auth."""
    key = config.MATTERPORT_API_KEY
    token = config.MATTERPORT_API_TOKEN
    if not key or not token:
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
                raise UpstreamError("matterport", retryable=False, message=f"Auth error: {resp.text}", http_status=resp.status_code)
            if resp.status_code >= 500:
                time.sleep(1.0 * (2**attempt))
                continue
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data and not data.get("data"):
                raise UpstreamError("matterport", retryable=False, message=str(data["errors"]))
            return data.get("data", {})
        except UpstreamError:
            raise
        except Exception as e:
            last_error = e
            time.sleep(1.0 * (2**attempt))

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
        if now - cached_time < 600:
            return cached_urls

    query = """
    query GetSkybox($id: ID!, $resolution: String!) {
      model(id: $id) {
        panos {
          id
          skybox(resolution: $resolution) {
            children {
              url
            }
          }
        }
      }
    }
    """
    data = graph(query, {"id": sid, "resolution": resolution})
    panos_data = data.get("model", {}).get("panos", [])
    result: dict[str, list[str]] = {}
    for p in panos_data:
        p_id = p.get("id")
        children = p.get("skybox", {}).get("children", [])
        urls = [c.get("url", "") for c in children]
        if p_id:
            result[p_id] = urls

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
        return ModelGeometry.model_validate(data)

    # Query live Matterport GraphQL API
    query = """
    query GetModelGeometry($id: ID!) {
      model(id: $id) {
        id
        name
        address {
          formattedAddress
        }
        geolocation {
          latitude
          longitude
        }
        floors {
          id
          rooms {
            id
            classification
            dimensions {
              areaFloor
              height
            }
            boundary {
              edges {
                type
                vertices {
                  x
                  y
                  z
                }
              }
            }
          }
        }
        panoLocations {
          id
          label
          position {
            x
            y
            z
          }
        }
      }
    }
    """
    raw_data = graph(query, {"id": sid})
    model_data = raw_data.get("model")
    if not model_data:
        raise UpstreamError("matterport", retryable=False, message=f"Model {sid} not found in Matterport API", http_status=404)

    idx = lookup(sid)
    addr_str = ""
    if model_data.get("address"):
        addr_str = model_data["address"].get("formattedAddress") or ""
    if not addr_str and idx:
        addr_str = idx.address

    lat = None
    lon = None
    geo = model_data.get("geolocation")
    if geo:
        lat = geo.get("latitude")
        lon = geo.get("longitude")
    if lat is None and idx:
        lat = idx.lat
        lon = idx.lon

    rooms: list[Room] = []
    walls: list[WallSegment] = []
    shapely_rooms: list[tuple[Room, Polygon]] = []

    floors = model_data.get("floors", [])
    for floor in floors:
        floor_id = floor.get("id", "f1")
        for r in floor.get("rooms", []):
            classification = r.get("classification", "")
            if classification == "Void":
                continue

            edges = r.get("boundary", {}).get("edges", [])
            for edge in edges:
                if edge.get("type") == "wall":
                    v = edge.get("vertices", [])
                    if len(v) >= 2:
                        walls.append(
                            WallSegment(
                                a=Vec2(x=float(v[0]["x"]), y=float(v[0]["y"])),
                                b=Vec2(x=float(v[1]["x"]), y=float(v[1]["y"])),
                                floor_id=floor_id,
                            )
                        )

            poly_vecs = _chain_edges_to_polygon(edges)
            coords = [(p.x, p.y) for p in poly_vecs]
            sh_poly = Polygon(coords)

            dims = r.get("dimensions", {})
            area_floor = dims.get("areaFloor")
            if area_floor is not None and area_floor > 0:
                area_m2 = float(area_floor)
            else:
                area_m2 = round(float(sh_poly.area), 2)

            height_val = dims.get("height")
            height_m = float(height_val) if height_val is not None else None

            room_obj = Room(
                id=r.get("id", f"r_{len(rooms)+1}"),
                label=classification or f"Room {len(rooms)+1}",
                floor_id=floor_id,
                area_m2=area_m2,
                height_m=height_m,
                polygon=poly_vecs,
                pano_ids=[],
            )
            rooms.append(room_obj)
            shapely_rooms.append((room_obj, sh_poly))

    # Assign panos to rooms by point-in-polygon
    panos: list[Pano] = []
    for pl in model_data.get("panoLocations", []):
        pos = pl.get("position", {})
        px = float(pos.get("x", 0.0))
        py = float(pos.get("y", 0.0))
        pz = float(pos.get("z", 0.0))
        pt = Point(px, py)

        assigned_room_id: str | None = None
        for room_obj, sh_poly in shapely_rooms:
            if sh_poly.contains(pt) or sh_poly.covers(pt):
                assigned_room_id = room_obj.id
                room_obj.pano_ids.append(pl.get("id", ""))
                break

        pano_obj = Pano(
            id=pl.get("id", ""),
            label=pl.get("label", ""),
            position=Vec3(x=px, y=py, z=pz),
            room_id=assigned_room_id,
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
        if resp.status_code in (401, 403):
            # Clear URL cache and retry once with fresh signed URLs
            _SKYBOX_CACHE.pop((sid, resolution), None)
            urls = skybox_urls(sid, resolution)
            pano_urls = urls.get(pano_id, [])
            if pano_urls and face < len(pano_urls):
                resp = requests.get(pano_urls[face], timeout=30)

        resp.raise_for_status()
        with open(cache_path, "wb") as f:
            f.write(resp.content)
        return cache_path
    except Exception as e:
        raise UpstreamError("matterport", retryable=True, message=f"Failed to download face image: {e}")
