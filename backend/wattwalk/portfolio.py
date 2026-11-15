"""Landlord buildings: find a building by address in the Matterport models index, and keep a list of the
buildings (and their scanned units) the landlord tracks.

Search covers Los Angeles only (the city with EBEWE energy data). Addresses are matched forgivingly:
"1830 north cherokee avenue" finds "1830 N Cherokee Ave". The landlord's list is one JSON file in the
audits folder (one landlord, no login, for the demo).
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from wattwalk import config
from wattwalk.contracts import (
    BuildingMatch,
    BuildingSearchResponse,
    Portfolio,
    PortfolioBuilding,
    TestModel,
    TourMatch,
)

MAX_BUILDINGS = 8
PORTFOLIO_FILE = "portfolio.json"

# Street words as they are usually abbreviated in addresses (and in the index).
WORDS = {
    "STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "BOULEVARD": "BLVD", "ROAD": "RD", "DRIVE": "DR",
    "PLACE": "PL", "LANE": "LN", "COURT": "CT", "TERRACE": "TER", "PARKWAY": "PKWY", "HIGHWAY": "HWY",
    "CIRCLE": "CIR", "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
}
UNIT_WORDS = {"UNIT", "APT", "APARTMENT", "STE", "SUITE", "#"}


def normalize_street(text: str) -> str:
    """Upper-case street address with standard abbreviations and no unit part: '1830 N CHEROKEE AVE'."""
    first = text.split(",")[0].upper().replace("#", " # ")
    tokens = re.sub(r"[^A-Z0-9# ]+", " ", first).split()
    out: list[str] = []
    for token in tokens:
        if token in UNIT_WORDS:
            break  # the rest is the unit number
        out.append(WORDS.get(token, token))
    return " ".join(out)


def building_id(street: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_street(street).lower()).strip("-")


def _is_los_angeles(row: dict) -> bool:
    return row.get("city", "").strip() == "Los Angeles" or ", Los Angeles" in row.get("address", "")


def _int(value: str | None) -> int:
    try:
        return max(0, int(value or 0))
    except ValueError:
        return 0


@lru_cache(maxsize=1)
def _buildings(path: str) -> dict[str, dict]:
    """Los Angeles buildings in the index: building_id -> address, postal code and its tours."""
    out: dict[str, dict] = {}
    p = Path(path)
    if not p.exists():
        return out
    with open(p, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sid = (row.get("sid") or "").strip()
            address = (row.get("address") or "").strip()
            if not sid or not address or not _is_los_angeles(row):
                continue
            street = normalize_street(address)
            if not re.match(r"^\d", street):
                continue  # no street number: not a findable building address
            bid = building_id(address)
            entry = out.setdefault(bid, {
                "street": street,
                "display": address.split(",")[0].strip(),
                "postal_code": (row.get("postal_code") or "").strip() or None,
                "tours": [],
            })
            entry["tours"].append(TourMatch(
                sid=sid,
                name=(row.get("name") or "").strip() or sid,
                pano_count=_int(row.get("pano_count")),
                room_count=_int(row.get("room_count")),
                scanned_on=(row.get("created") or "").strip() or None,
                defurnished=(row.get("defurnished") or "").strip().lower() == "yes",
            ))
    return out


def _index_path() -> str:
    return str(config.FIXTURES_DIR / "models_index.csv")


def _match(entry: dict, bid: str) -> BuildingMatch:
    return BuildingMatch(
        building_id=bid,
        address=f"{entry['display']}, Los Angeles, CA",
        city="Los Angeles",
        postal_code=entry["postal_code"],
        tours=sorted(entry["tours"], key=lambda t: t.name.lower()),
    )


def search(query: str) -> BuildingSearchResponse:
    """Buildings whose street address matches the query: exact first, then starts-with, then contains."""
    q = normalize_street(query)
    if len(q) < 3:
        return BuildingSearchResponse(query=query, buildings=[])
    words = q.split()
    ranked: list[tuple[int, int, str]] = []
    for bid, entry in _buildings(_index_path()).items():
        street = entry["street"]
        if street == q:
            rank = 0
        elif street.startswith(q):
            rank = 1
        elif all(re.search(rf"\b{re.escape(w)}", street) for w in words):
            rank = 2
        else:
            continue
        ranked.append((rank, -len(entry["tours"]), bid))
    ranked.sort()
    buildings = _buildings(_index_path())
    return BuildingSearchResponse(
        query=query, buildings=[_match(buildings[bid], bid) for _, _, bid in ranked[:MAX_BUILDINGS]])


# ----------------------------------------------------------------------------- the landlord's list

def _portfolio_path() -> Path:
    return config.AUDITS_DIR / PORTFOLIO_FILE


def load() -> Portfolio:
    try:
        return Portfolio.model_validate_json(_portfolio_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Portfolio(buildings=[])


def _save(portfolio: Portfolio) -> Portfolio:
    path = _portfolio_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(portfolio.model_dump_json(indent=2), encoding="utf-8")
    return portfolio


def add_building(bid: str, sids: list[str]) -> Portfolio:
    """Add a building with the chosen units, or update the units of one already added.
    Raises KeyError for an unknown building and ValueError for a unit that is not in it."""
    entry = _buildings(_index_path()).get(bid)
    if entry is None:
        raise KeyError(bid)
    known = {t.sid for t in entry["tours"]}
    unknown = [s for s in sids if s not in known]
    if unknown:
        raise ValueError(f"not a unit of this building: {', '.join(unknown)}")
    chosen = list(dict.fromkeys(sids))
    portfolio = load()
    others = [b for b in portfolio.buildings if b.building_id != bid]
    existing = next((b for b in portfolio.buildings if b.building_id == bid), None)
    added = PortfolioBuilding(
        building_id=bid,
        address=_match(entry, bid).address,
        city="Los Angeles",
        sids=chosen,
        added_at=existing.added_at if existing else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    return _save(Portfolio(buildings=[*others, added]))


def remove_building(bid: str) -> Portfolio:
    portfolio = load()
    return _save(Portfolio(buildings=[b for b in portfolio.buildings if b.building_id != bid]))


def unit_addresses() -> dict[str, str]:
    """Address with the unit name ("1830 N Cherokee Ave, Studio - 331, Los Angeles, CA") for every unit in
    the landlord's buildings, so the picker can group units under their building."""
    buildings = _buildings(_index_path())
    out: dict[str, str] = {}
    for b in load().buildings:
        entry = buildings.get(b.building_id)
        names = {t.sid: t.name for t in entry["tours"]} if entry else {}
        street = b.address.split(",")[0]
        for sid in b.sids:
            out.setdefault(sid, f"{street}, {names.get(sid, sid)}, Los Angeles, CA")
    return out


def portfolio_models(already: set[str]) -> list[TestModel]:
    """The landlord's units as apartments for the picker (after the configured ones)."""
    out: list[TestModel] = []
    for sid, address in unit_addresses().items():
        if sid in already:
            continue
        already.add(sid)
        out.append(TestModel(
            sid=sid,
            address=address,
            city="Los Angeles",
            note=f"Your building: {address.split(',')[0]}",
            has_fixture=False,
            has_replay=False,
        ))
    return out


def reset_cache() -> None:
    _buildings.cache_clear()


__all__ = ["add_building", "load", "normalize_street", "portfolio_models", "remove_building", "search"]
