"""LA EBEWE benchmark data adapter.

Owner: Person 1.
See plan/plan.md section 13.3, Appendix A.1.3.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

import requests

from wattwalk import config
from wattwalk.contracts import EbeweRecord
from wattwalk.errors import UpstreamError

EBEWE_ENDPOINT = "https://data.lacity.org/resource/9yda-i4ya.json"

_EBEWE_CACHE: dict[str, EbeweRecord | None] = {}

ABBREVIATIONS = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
    "PLACE": "PL",
    "ROAD": "RD",
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
}


def normalize_address(address: str) -> str:
    """Normalize street address for LA EBEWE Socrata query."""
    if not address:
        return ""

    # Uppercase
    s = address.upper()

    # First comma-separated part
    parts = s.split(",")
    first = parts[0].strip()

    # Remove periods
    first = first.replace(".", "")

    # Remove unit suffixes (APT, UNIT, STE, SUITE, #...)
    first = re.sub(r"\b(APT|UNIT|STE|SUITE|BLDG|FLOOR|FL)\s*#?\s*\w*", "", first, flags=re.IGNORECASE)
    first = re.sub(r"#\s*\w*", "", first)

    # Tokenize and abbreviate words
    tokens = first.split()
    normalized_tokens = [ABBREVIATIONS.get(t, t) for t in tokens]
    res = " ".join(normalized_tokens).strip()

    # Escape single quotes by doubling
    return res.replace("'", "''")


def _record_health(ok: bool, detail: str = "") -> None:
    mode = config.effective_data_mode()
    if mode == "fixture":
        return
    try:
        from wattwalk import health_registry
        health_registry.record("ebewe", ok, detail)
    except (ImportError, AttributeError):
        pass


def lookup(address: str, city: str = "Los Angeles") -> EbeweRecord | None:
    """Look up building energy intensity in LA EBEWE dataset.

    Returns EbeweRecord or None if not found or outside LA.
    """
    if city != "Los Angeles":
        return None

    norm_addr = normalize_address(address)
    if not norm_addr:
        return None

    if norm_addr in _EBEWE_CACHE:
        return _EBEWE_CACHE[norm_addr]

    timeout = config.TIMEOUTS_S.get("ebewe", 15)
    params = {
        "$where": f"upper(building_address)='{norm_addr}' AND site_eui IS NOT NULL AND site_eui != 'Not Available'",
        "$order": "program_year DESC",
        "$limit": "1",
    }

    try:
        resp = requests.get(EBEWE_ENDPOINT, params=params, timeout=timeout)
        if resp.status_code >= 500:
            _record_health(False, str(resp.status_code))
            raise UpstreamError("ebewe", retryable=True, message=f"EBEWE server error: {resp.status_code}", http_status=resp.status_code)
        resp.raise_for_status()
        records = resp.json()
        _record_health(True)
    except UpstreamError:
        raise
    except requests.exceptions.Timeout:
        _record_health(False, "504")
        raise UpstreamError("ebewe", retryable=True, message="EBEWE request timed out", http_status=504)
    except Exception as e:
        _record_health(False, type(e).__name__)
        raise UpstreamError("ebewe", retryable=True, message=f"EBEWE request failed: {e}")


    if not records or not isinstance(records, list):
        _EBEWE_CACHE[norm_addr] = None
        return None

    r = records[0]
    site_eui_str = r.get("site_eui")
    if not site_eui_str or site_eui_str == "Not Available":
        _EBEWE_CACHE[norm_addr] = None
        return None

    site_eui = float(site_eui_str)

    gfa_val = r.get("property_gfa_1")
    gfa_ft2 = float(gfa_val) if (gfa_val and gfa_val != "Not Available") else None

    py_str = r.get("program_year", "0")
    program_year = int(py_str) if py_str.isdigit() else 2025

    yb_val = r.get("year_built")
    year_built = int(yb_val) if (yb_val and yb_val.isdigit()) else None

    prop_type = r.get("primary_property_1", "")

    record = EbeweRecord(
        site_eui_kbtu_ft2=site_eui,
        gfa_ft2=gfa_ft2,
        program_year=program_year,
        year_built=year_built,
        property_type=prop_type,
    )
    _EBEWE_CACHE[norm_addr] = record
    return record
