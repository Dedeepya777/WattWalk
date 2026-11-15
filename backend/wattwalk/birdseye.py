"""Bird's-eye (oblique aerial) view of an apartment's building from Vexcel, looking from one side.

Uses Vexcel API 2.0 /oriented/extract with product-type oblique-<direction>, centred on the scan's
coordinates from the models index. Images are cached under the audits cache folder (never committed:
Vexcel imagery is licensed) and keep Vexcel's attribution overlay.
"""
from __future__ import annotations

from pathlib import Path

import requests

from wattwalk import config
from wattwalk.data import index

ORIENTED_URL = "https://api.vexcelgroup.com/v2/oriented/extract"
DIRECTIONS = ("north", "east", "south", "west")
VIEW_METRES = 120  # area around the building shown in the photo
PIXELS = "800,600"


class NoKey(RuntimeError):
    """VEXCEL_API_KEY is not set."""


class NoLocation(LookupError):
    """The scan has no coordinates in the models index."""


class Unavailable(RuntimeError):
    """Vexcel returned no image (no coverage here, or an error)."""


def _cache_path(lat: float, lon: float, direction: str) -> Path:
    return config.CACHE_DIR / "vexcel" / f"oblique_{lat:.6f}_{lon:.6f}_{direction}.jpg"


def birdseye(sid: str, direction: str = "north") -> Path:
    """Path to a JPEG bird's-eye view of the building of `sid`, seen looking `direction`."""
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {', '.join(DIRECTIONS)}")
    row = index.lookup(sid)
    if row is None or row.lat is None or row.lon is None:
        raise NoLocation(sid)
    path = _cache_path(row.lat, row.lon, direction)
    if path.exists():
        return path
    if not config.VEXCEL_API_KEY:
        raise NoKey("VEXCEL_API_KEY is not set; add it to .env to show bird's-eye views.")
    params = {
        "wkt": f"POINT({row.lon} {row.lat})",
        "srid": "4326",
        "layer": "urban,urban-r,wide-area,urban-g",
        "product-type": f"oblique-{direction}",
        "bbox-dimensions": f"{VIEW_METRES},{VIEW_METRES}",
        "destination-dimensions": PIXELS,
        "image-format": "jpeg",
        "attribution": "true",
    }
    try:
        resp = requests.get(ORIENTED_URL, headers={"x-api-key": config.VEXCEL_API_KEY}, params=params,
                            timeout=config.TIMEOUTS_S.get("vexcel", 20) * 2)
    except requests.exceptions.RequestException as exc:
        raise Unavailable(f"Vexcel not reachable: {exc}") from exc
    if resp.status_code != 200 or not resp.headers.get("Content-Type", "").startswith("image/"):
        raise Unavailable(f"Vexcel returned HTTP {resp.status_code} for this building")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return path
