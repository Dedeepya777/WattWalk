"""Integration probe functions for GET /health?probe=1.

Owner: Person 1.
See plan P1-6.
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import requests

from wattwalk import config

log = logging.getLogger("wattwalk.data.probes")

PROBE_TIMEOUT_S = 10


def _record(integration: str, ok: bool, detail: str = "") -> None:
    try:
        from wattwalk import health_registry
        health_registry.record(integration, ok, detail)
    except (ImportError, AttributeError):
        pass


def probe_matterport() -> tuple[bool, str]:
    """Probe Matterport GraphQL endpoint with minimal query { rootFolder { name } }."""
    key = config.MATTERPORT_API_KEY
    token = config.MATTERPORT_API_TOKEN
    if not key or not token:
        detail = "missing credentials"
        _record("matterport", False, detail)
        return False, detail

    url = "https://api.matterport.com/api/models/graph"
    query = "query { rootFolder { name } }"
    try:
        resp = requests.post(
            url,
            json={"query": query},
            auth=(key, token),
            timeout=PROBE_TIMEOUT_S,
        )
        if resp.status_code == 200:
            _record("matterport", True, "200")
            return True, "200"
        detail = f"{resp.status_code}"
        _record("matterport", False, detail)
        return False, detail
    except Exception as exc:
        detail = type(exc).__name__
        _record("matterport", False, detail)
        return False, detail


def probe_ebewe() -> tuple[bool, str]:
    """Probe City of Los Angeles EBEWE Socrata endpoint with $limit=1."""
    url = "https://data.lacity.org/resource/9yda-i4ya.json"
    try:
        resp = requests.get(url, params={"$limit": "1"}, timeout=PROBE_TIMEOUT_S)
        if resp.status_code == 200:
            _record("ebewe", True, "200")
            return True, "200"
        detail = f"{resp.status_code}"
        _record("ebewe", False, detail)
        return False, detail
    except Exception as exc:
        detail = type(exc).__name__
        _record("ebewe", False, detail)
        return False, detail


def probe_costar_kit() -> tuple[bool, str]:
    """Probe CoStar data kit by opening zip or folder and listing at least one file."""
    if not config.COSTAR_KIT_ZIP:
        detail = "COSTAR_KIT_ZIP not configured"
        _record("costar_kit", False, detail)
        return False, detail

    kit_path = Path(config.COSTAR_KIT_ZIP)
    if not kit_path.exists():
        detail = f"path does not exist: {kit_path}"
        _record("costar_kit", False, detail)
        return False, detail

    try:
        if kit_path.is_dir():
            files = list(kit_path.iterdir())
            if files:
                detail = f"folder with {len(files)} entries"
                _record("costar_kit", True, detail)
                return True, detail
            detail = "folder is empty"
            _record("costar_kit", False, detail)
            return False, detail

        if kit_path.is_file() and kit_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(kit_path, "r") as zf:
                names = zf.namelist()
                if names:
                    detail = f"zip with {len(names)} entries"
                    _record("costar_kit", True, detail)
                    return True, detail
                detail = "zip is empty"
                _record("costar_kit", False, detail)
                return False, detail

        detail = f"unsupported kit format: {kit_path}"
        _record("costar_kit", False, detail)
        return False, detail
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        _record("costar_kit", False, detail)
        return False, detail


def probe_vexcel() -> tuple[bool, str]:
    """Probe Vexcel ortho API with 64x64 extraction for downtown LA point, cached locally."""
    key = config.VEXCEL_API_KEY
    if not key:
        detail = "missing VEXCEL_API_KEY"
        _record("vexcel", False, detail)
        return False, detail

    cache_file = config.CACHE_DIR / "vexcel" / "probe_64.jpg"
    if cache_file.exists():
        _record("vexcel", True, "cached")
        return True, "cached"

    url = "https://api.vexcelgroup.com/v2/ortho/extract"
    # Fixed downtown LA point (34.0475, -118.2573) with ~50m box
    lat, lon = 34.0475, -118.2573
    dlat = 50.0 / 111_320
    dlon = 50.0 / (111_320 * 0.8286)
    lon0, lon1, lat0, lat1 = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    wkt = f"POLYGON(({lon0} {lat0},{lon1} {lat0},{lon1} {lat1},{lon0} {lat1},{lon0} {lat0}))"

    body = {
        "wkt": wkt,
        "srid": 4326,
        "layer": "urban,urban-r,wide-area,urban-g",
        "crop": "bounding_box",
        "image-format": "jpeg",
        "destination-dimensions": "64,64",
        "attribution": "false",
    }
    headers = {"x-api-key": key, "Content-Type": "application/json"}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=PROBE_TIMEOUT_S)
        ctype = resp.headers.get("Content-Type", "")
        if resp.status_code == 200 and ctype.startswith("image/"):
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(resp.content)
            _record("vexcel", True, "200")
            return True, "200"
        detail = f"{resp.status_code}"
        _record("vexcel", False, detail)
        return False, detail
    except Exception as exc:
        detail = type(exc).__name__
        _record("vexcel", False, detail)
        return False, detail
