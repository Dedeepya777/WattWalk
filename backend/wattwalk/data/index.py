"""Models index loader and lookup.

Owner: Person 1.
See plan/plan.md section 13.1, Appendix A.1.1, P1-4.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from wattwalk import config

log = logging.getLogger("wattwalk.data.index")


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


FIXTURE_UNIT_A = IndexRow(
    sid="fixtureUnitA",
    name="Fixture Unit A",
    segment="residential",
    lat=None,
    lon=None,
    address="100 Example St, Los Angeles, CA 90000",
    city="Los Angeles",
    costar_property_id="illustrative-0001",
    homes_listing_id=None,
    pano_count=7,
    room_count=6,
    splat=False,
)

_INDEX_CACHE: dict[Path, dict[str, IndexRow]] = {}


def _normalize_city(raw_city: str, raw_address: str) -> str:
    combined = f"{raw_city} {raw_address}".strip()
    if "Houston" in combined or ", TX" in combined or " TX " in combined or " TX," in combined:
        return "Houston"
    return "Los Angeles"


def _clean_str(val: str | None) -> str | None:
    if val is None:
        return None
    s = val.strip().replace("\r", "")
    return s if s else None


def load_index(path: Path | None = None) -> dict[str, IndexRow]:
    """Load and cache the hackathon models index CSV (full or sample fallback)."""
    if path is not None:
        p = path
    else:
        full_p = config.FIXTURES_DIR / "models_index.csv"
        sample_p = config.FIXTURES_DIR / "models_index.sample.csv"
        if full_p.exists():
            p = full_p
            log.info("Loaded full models index from %s", p)
        elif sample_p.exists():
            p = sample_p
            log.info("sample index: loaded sample models index from %s", p)
        else:
            p = full_p

    if p in _INDEX_CACHE:
        return _INDEX_CACHE[p]

    if not p.exists():
        return {"fixtureUnitA": FIXTURE_UNIT_A}

    rows: dict[str, IndexRow] = {}
    with open(p, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for d in reader:
            sid = _clean_str(d.get("sid"))
            if not sid:
                continue

            lat_str = _clean_str(d.get("lat"))
            lon_str = _clean_str(d.get("lon"))
            lat: float | None = None
            lon: float | None = None
            if lat_str:
                try:
                    lat = float(lat_str)
                except ValueError:
                    lat = None
            if lon_str:
                try:
                    lon = float(lon_str)
                except ValueError:
                    lon = None

            addr = _clean_str(d.get("address")) or ""
            raw_city = _clean_str(d.get("city")) or ""
            city = _normalize_city(raw_city, addr)

            costar_id = _clean_str(d.get("costar_property_id"))
            homes_id = _clean_str(d.get("homes_listing_id"))

            pano_cnt_str = _clean_str(d.get("pano_count")) or "0"
            room_cnt_str = _clean_str(d.get("room_count")) or "0"
            pano_count = int(pano_cnt_str) if pano_cnt_str.isdigit() else 0
            room_count = int(room_cnt_str) if room_cnt_str.isdigit() else 0

            splat_val = (_clean_str(d.get("splat")) or "false").lower()
            splat = splat_val in {"true", "1", "yes"}

            row = IndexRow(
                sid=sid,
                name=_clean_str(d.get("name")) or "",
                segment=_clean_str(d.get("segment")) or "",
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

    if "fixtureUnitA" not in rows:
        rows["fixtureUnitA"] = FIXTURE_UNIT_A

    _INDEX_CACHE[p] = rows
    return rows


def lookup(sid: str) -> IndexRow | None:
    """Look up an index row by sid."""
    idx = load_index()
    return idx.get(sid)


def same_building(costar_property_id: str) -> list[IndexRow]:
    """Return all index rows with the same costar_property_id."""
    idx = load_index()
    return [r for r in idx.values() if r.costar_property_id == costar_property_id]
