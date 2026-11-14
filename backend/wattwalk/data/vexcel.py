"""Vexcel aerial imagery and roof attributes adapter.

Owner: Person 1.
See plan/plan.md section 13.4, Appendix A.1.3, Appendix F.3.
"""
from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Any

import requests

from wattwalk import config
from wattwalk.errors import UpstreamError

log = logging.getLogger("wattwalk.data.vexcel")

VEXCEL_ORTHO_URL = "https://api.vexcelgroup.com/v2/ortho/extract"


def _record_health(ok: bool, detail: str = "") -> None:
    try:
        from wattwalk import health_registry
        health_registry.record("vexcel", ok, detail)
    except (ImportError, AttributeError):
        pass


def _cache_key(lat: float, lon: float, half_width_m: float) -> str:
    return f"{lat:.6f}_{lon:.6f}_{int(half_width_m)}"


def ortho(sid: str, lat: float, lon: float, half_width_m: float = 70.0) -> Path | None:
    """Extract ortho aerial image centered at (lat, lon) within half_width_m bounding box.
    
    Returns path to cached JPEG, or None if key is missing. Raises UpstreamError on API failure.
    """
    mode = config.effective_data_mode()
    if mode == "fixture":
        return Path("audits/fixtureUnitA/vexcel/ortho.jpg")

    cache_dir = config.CACHE_DIR / "vexcel"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = _cache_key(lat, lon, half_width_m)
    cache_path = cache_dir / f"{cache_key}.jpg"
    if cache_path.exists():
        return cache_path

    key = config.VEXCEL_API_KEY
    if not key:
        return None

    # Calculate bounding polygon in degrees (lon lat WKT order)
    dlat = half_width_m / 111_320
    dlon = half_width_m / (111_320 * math.cos(math.radians(lat)))
    lon0, lon1, lat0, lat1 = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    wkt = f"POLYGON(({lon0} {lat0},{lon1} {lat0},{lon1} {lat1},{lon0} {lat1},{lon0} {lat0}))"

    body = {
        "wkt": wkt,
        "srid": 4326,
        "layer": "urban,urban-r,wide-area,urban-g",
        "crop": "bounding_box",
        "image-format": "jpeg",
        "destination-dimensions": "1400,1400",
        "attribution": "false",
    }
    timeout = config.TIMEOUTS_S.get("vexcel", 20)
    headers = {"x-api-key": key, "Content-Type": "application/json"}

    attempts = 2
    for attempt in range(attempts):
        try:
            resp = requests.post(VEXCEL_ORTHO_URL, headers=headers, json=body, timeout=timeout)
            ctype = resp.headers.get("Content-Type", "")
            if resp.status_code == 200 and ctype.startswith("image/"):
                cache_path.write_bytes(resp.content)
                _record_health(True)
                return cache_path

            # Error response (often JSON)
            detail = ""
            try:
                err_json = resp.json()
                detail = str(err_json.get("message") or err_json)[:200]
            except Exception:
                detail = resp.text[:200]

            if resp.status_code == 403:
                detail = f"Keys answer 403 outside Houston and Los Angeles: {detail}"

            is_retryable = resp.status_code >= 500
            if is_retryable and attempt < attempts - 1:
                time.sleep(2)
                continue

            _record_health(False, str(resp.status_code))
            raise UpstreamError("vexcel", retryable=is_retryable, message=detail, http_status=resp.status_code)

        except requests.exceptions.RequestException as exc:
            if attempt < attempts - 1:
                time.sleep(2)
                continue
            _record_health(False, type(exc).__name__)
            raise UpstreamError("vexcel", retryable=True, message=f"Vexcel request failed: {exc}") from exc

    return None


def roof_attributes(lat: float, lon: float) -> dict[str, Any] | None:
    """Fetch roof attributes for solar potential or return None if unsupported."""
    mode = config.effective_data_mode()
    if mode == "fixture":
        return {}

    key = config.VEXCEL_API_KEY
    if not key:
        return None

    # Finding: Hackathon keys do not provide access to building/parcel/roof attribute endpoints.
    log.info("Vexcel roof attributes endpoint not available to hackathon keys")
    return None
