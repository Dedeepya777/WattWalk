"""Models index loader and lookup.

Owner: Person 1.
See plan/plan.md section 13.1, Appendix A.1.1.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from wattwalk import config


@dataclass(frozen=True)
class IndexRow:
    sid: str
    name: str
    segment: str
    lat: float | None
    lon: float | None
    address: str
    city: str
    costar_property_id: str | None
    homes_listing_id: str | None
    pano_count: int
    room_count: int
    splat: bool


_INDEX_CACHE: dict[Path, dict[str, IndexRow]] = {}


def _normalize_city(raw_city: str, raw_address: str) -> str:
    combined = f"{raw_city} {raw_address}".strip()
    if "Houston" in combined or ", TX" in combined or " TX " in combined:
        return "Houston"
    return "Los Angeles"


def load_index(path: Path | None = None) -> dict[str, IndexRow]:
    """Load and cache the hackathon models index CSV."""
    p = path or (config.FIXTURES_DIR / "models_index.csv")
    if p in _INDEX_CACHE:
        return _INDEX_CACHE[p]

    if not p.exists():
        return {}

    rows: dict[str, IndexRow] = {}
    with open(p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for d in reader:
            sid = (d.get("sid") or "").strip()
            if not sid:
                continue

            lat_str = (d.get("lat") or "").strip()
            lon_str = (d.get("lon") or "").strip()
            lat = float(lat_str) if lat_str else None
            lon = float(lon_str) if lon_str else None

            addr = (d.get("address") or "").strip()
            raw_city = (d.get("city") or "").strip()
            city = _normalize_city(raw_city, addr)

            costar_id = (d.get("costar_property_id") or "").strip() or None
            homes_id = (d.get("homes_listing_id") or "").strip() or None

            pano_cnt_str = (d.get("pano_count") or "0").strip()
            room_cnt_str = (d.get("room_count") or "0").strip()
            pano_count = int(pano_cnt_str) if pano_cnt_str.isdigit() else 0
            room_count = int(room_cnt_str) if room_cnt_str.isdigit() else 0

            splat_val = (d.get("splat") or "false").strip().lower()
            splat = splat_val in {"true", "1", "yes"}

            row = IndexRow(
                sid=sid,
                name=(d.get("name") or "").strip(),
                segment=(d.get("segment") or "").strip(),
                lat=lat,
                lon=lon,
                address=addr,
                city=city,
                costar_property_id=costar_id,
                homes_listing_id=homes_id,
                pano_count=pano_count,
                room_count=room_count,
                splat=splat,
            )
            rows[sid] = row

    _INDEX_CACHE[p] = rows
    return rows


def lookup(sid: str) -> IndexRow | None:
    """Look up an index row by sid."""
    index = load_index()
    return index.get(sid)


def same_building(costar_property_id: str) -> list[IndexRow]:
    """Return all index rows with the same costar_property_id."""
    index = load_index()
    return [r for r in index.values() if r.costar_property_id == costar_property_id]
