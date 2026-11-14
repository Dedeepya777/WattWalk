"""Vexcel aerial imagery and roof attributes adapter.

Owner: Person 1.
See plan/plan.md section 13.4, Appendix A.1.3.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import requests

from wattwalk import config
from wattwalk.errors import UpstreamError

VEXCEL_ORTHO_URL = "https://api.vexcelgroup.com/v2/ortho/extract"


def ortho(sid: str, lat: float, lon: float, half_width_m: float = 70.0) -> Path | None:
    """Extract ortho aerial image centered at (lat, lon) within half_width_m bounding box."""
    mode = config.effective_data_mode()
    if mode == "fixture":
        return Path("audits/fixtureUnitA/vexcel/ortho.jpg")

    cache_dir = config.CACHE_DIR / "vexcel"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{sid}_ortho.jpg"
    if cache_path.exists():
        return cache_path

    key = config.VEXCEL_API_KEY
    if not key:
        return None

    # Calculate bounding polygon in degrees (lon lat WKT order)
    dlat = half_width_m / 111320.0
    dlon = half_width_m / (111320.0 * math.cos(math.radians(lat)))

    min_lon, max_lon = lon - dlon, lon + dlon
    min_lat, max_lat = lat - dlat, lat + dlat

    wkt = f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, {max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"

    timeout = config.TIMEOUTS_S.get("vexcel", 20)
    headers = {"x-api-key": key, "Content-Type": "application/json"}
    body = {"geometry": wkt, "format": "image/jpeg"}

    try:
        resp = requests.post(VEXCEL_ORTHO_URL, headers=headers, json=body, timeout=timeout)
        if resp.status_code == 200 and len(resp.content) > 500:
            with open(cache_path, "wb") as f:
                f.write(resp.content)
            return cache_path
        return None
    except Exception:
        return None


def roof_attributes(lat: float, lon: float) -> dict[str, Any] | None:
    """Fetch roof attributes for solar potential or return empty dict."""
    mode = config.effective_data_mode()
    if mode == "fixture":
        return {}

    key = config.VEXCEL_API_KEY
    if not key:
        return {}

    # Roof attributes tutorial endpoint (fallback to empty dict per plan A.1.3 / scope cut)
    return {}
