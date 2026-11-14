"""CoStar data kit adapter.

Owner: Person 1.
See plan/plan.md section 13.2, Appendix A.1.3.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wattwalk import config
from wattwalk.contracts import IntegrationStatus

_COSTAR_CACHE: dict[str, dict[str, Any]] = {}


def kit_status() -> IntegrationStatus:
    """Return status of CoStar data kit integration."""
    mode = config.effective_data_mode()
    if mode == "fixture":
        return "fixture"

    kit_path = Path(config.COSTAR_KIT_ZIP)
    if not config.COSTAR_KIT_ZIP or not kit_path.exists():
        return "unavailable"

    return "live"


def costar_record(costar_property_id: str | None, homes_listing_id: str | None) -> dict[str, Any] | None:
    """Join against CoStar commercial property records or residential listings."""
    mode = config.effective_data_mode()
    if mode == "fixture":
        return None

    if not costar_property_id and not homes_listing_id:
        return None

    target_id = costar_property_id or homes_listing_id
    if target_id in _COSTAR_CACHE:
        return _COSTAR_CACHE[target_id]

    kit_path = Path(config.COSTAR_KIT_ZIP)
    if not config.COSTAR_KIT_ZIP or not kit_path.exists():
        return None

    # Check if kit_path is a directory (extracted kit)
    if kit_path.is_dir():
        for csv_file in kit_path.glob("*.csv"):
            try:
                with open(csv_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        for val in row.values():
                            if val and str(val).strip() == str(target_id).strip():
                                res = _map_costar_row(row)
                                _COSTAR_CACHE[target_id] = res
                                return res
            except Exception:
                continue

    # Or zip file
    elif kit_path.is_file() and kit_path.suffix.lower() == ".zip":
        try:
            pwd = config.COSTAR_ZIP_PASSWORD.encode("utf-8") if config.COSTAR_ZIP_PASSWORD else None
            with zipfile.ZipFile(kit_path, "r") as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".csv"):
                        try:
                            with zf.open(name, "r", pwd=pwd) as zf_file:
                                reader = csv.DictReader(zf_file.read().decode("utf-8", errors="ignore").splitlines())
                                for row in reader:
                                    for val in row.values():
                                        if val and str(val).strip() == str(target_id).strip():
                                            res = _map_costar_row(row)
                                            _COSTAR_CACHE[target_id] = res
                                            return res
                        except Exception:
                            continue
        except Exception:
            return None

    return None


# ---------- direct join by Matterport model id (sid) ----------
# The kit's starter CSVs map every Matterport model id to a CoStar key: commercial-properties.csv
# (PropertyId -> data/commercial-property.jsonl `id`) and residential-listings.csv (ListingId ->
# data/residential-listings.jsonl `id`). The full records hold year built, units and prices; the CSVs
# hold only ids and addresses. See the kit's index.md, "The starter files".

_SID_CACHE: dict[str, dict[str, Any] | None] = {}

LISTING_PROPERTY_TYPE = {1: "Detached house", 2: "Townhouse", 4: "Condo", 8: "Other", 16: "Multifamily",
                         32: "Lot or land", 64: "Mobile or manufactured", 128: "Commercial"}
COMMERCIAL_PROPERTY_TYPE = {1: "Hospitality", 2: "Industrial", 3: "Land", 5: "Office", 6: "Retail", 7: "Flex",
                            8: "Sports and entertainment", 9: "Mixed use", 10: "Specialty", 11: "Multifamily"}
CONSTRUCTION_COMPLETE = 2  # ConstructionEventType


@contextmanager
def _kit_file(rel: str) -> Iterator[Any]:
    """Open a kit file (a path such as "data/apartment-listing.jsonl") as text, from a folder or a zip."""
    kit = Path(config.COSTAR_KIT_ZIP)
    if kit.is_dir():
        path = kit / rel
        if not path.exists():
            yield None
            return
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            yield f
        return
    if kit.is_file() and kit.suffix.lower() == ".zip":
        pwd = config.COSTAR_ZIP_PASSWORD.encode("utf-8") if config.COSTAR_ZIP_PASSWORD else None
        with zipfile.ZipFile(kit, "r") as zf:
            name = next((n for n in zf.namelist() if n.replace("\\", "/").endswith(rel)), None)
            if name is None:
                yield None
                return
            with zf.open(name, "r", pwd=pwd) as raw:
                yield io.TextIOWrapper(raw, encoding="utf-8", errors="ignore")
        return
    yield None


def _keys_for_sid(sid: str) -> tuple[list[int], list[int]]:
    """(commercial PropertyIds, residential ListingIds) whose Matterport model id is sid."""
    found: dict[str, list[int]] = {"commercial-properties.csv": [], "residential-listings.csv": []}
    for rel, key in (("commercial-properties.csv", "PropertyId"), ("residential-listings.csv", "ListingId")):
        with _kit_file(rel) as f:
            if f is None:
                continue
            for row in csv.DictReader(f):
                if (row.get("MatterportModelId") or "").strip() == sid and (row.get(key) or "").strip().isdigit():
                    value = int(row[key])
                    if value not in found[rel]:
                        found[rel].append(value)
    return found["commercial-properties.csv"], found["residential-listings.csv"]


_ID_PREFIX = re.compile(r'\{\s*"id"\s*:\s*(\d+)\s*,')


def _records_by_id(rel: str, ids: list[int]) -> dict[int, dict[str, Any]]:
    """Records of a JSON Lines dataset whose `id` is in ids. Checks the id prefix before parsing a line."""
    wanted, out = set(ids), {}
    if not wanted:
        return out
    with _kit_file(rel) as f:
        if f is None:
            return out
        for line in f:
            m = _ID_PREFIX.match(line)
            if m and int(m.group(1)) in wanted:
                out[int(m.group(1))] = json.loads(line)
                if len(out) == len(wanted):
                    break
    return out


def _apartment_listing(property_id: int) -> dict[str, Any] | None:
    needle = f'"propertyId":{property_id},'
    with _kit_file("data/apartment-listing.jsonl") as f:
        if f is None:
            return None
        for line in f:
            if needle in line.replace(" ", ""):
                record = json.loads(line)
                if record.get("propertyId") == property_id:
                    return record
    return None


def _usd(value: float) -> str:
    return f"${value:,.0f}"


def _from_residential(rec: dict[str, Any]) -> dict[str, Any]:
    prop = rec.get("property") or {}
    out: dict[str, Any] = {"notes": {}, "source_record": f"Homes.com listing {rec.get('id')}"}
    if rec.get("propertyId"):
        out["costar_property_id"] = str(rec["propertyId"])
    year = prop.get("yearBuilt") or ((rec.get("resoValues") or {}).get("structure") or {}).get("yearBuilt")
    if year:
        out["year_built"] = int(year)
        out["notes"]["year_built"] = "From CoStar residential listing (Homes.com)"
    if prop.get("unitsCount"):
        out["units"] = int(prop["unitsCount"])
        out["notes"]["units"] = "Units in the building, from CoStar residential listing (Homes.com)"
    if prop.get("propertyType") in LISTING_PROPERTY_TYPE:
        out["property_type"] = LISTING_PROPERTY_TYPE[prop["propertyType"]]
    price = rec.get("currentPrice") or (rec.get("resoValues") or {}).get("listPrice")
    if price:
        if rec.get("transactionType") == 2:  # ForRent: the price is the monthly rent
            out["asking_rent_usd_month"] = float(price)
            out["notes"]["asking_rent_usd_month"] = "Monthly rent from CoStar residential listing (Homes.com)"
        else:  # ForSale: a sale price is not a rent, so it is reported separately
            out["list_price_usd"] = float(price)
    return out


def _from_commercial(rec: dict[str, Any], listing: dict[str, Any] | None) -> dict[str, Any]:
    apt = rec.get("propertyApartment") or {}
    out: dict[str, Any] = {"notes": {}, "costar_property_id": str(rec["id"]),
                           "source_record": f"CoStar property {rec['id']}"}
    years = [e.get("year") for e in rec.get("constructionEvents") or []
             if e.get("eventType") == CONSTRUCTION_COMPLETE and e.get("year")]
    if years:
        out["year_built"] = int(min(years))
        out["notes"]["year_built"] = "From CoStar property record (construction complete)"
    elif listing and listing.get("yearBuilt"):
        out["year_built"] = int(listing["yearBuilt"])
        out["notes"]["year_built"] = "From CoStar apartment listing (Apartments.com)"
    units = apt.get("totalNumUnits") or (listing or {}).get("totalNumUnits")
    if units:
        out["units"] = int(units)
        out["notes"]["units"] = "From CoStar property record"
    if rec.get("propertyType") in COMMERCIAL_PROPERTY_TYPE:
        out["property_type"] = COMMERCIAL_PROPERTY_TYPE[rec["propertyType"]]
    lo, hi = (listing or {}).get("minRent"), (listing or {}).get("maxRent")
    if lo and hi:
        out["asking_rent_usd_month"] = round((float(lo) + float(hi)) / 2, 2)
        out["notes"]["asking_rent_usd_month"] = (f"Midpoint of the community's asking rents {_usd(lo)} to {_usd(hi)} "
                                                 "a month (CoStar apartment listing, Apartments.com); not this unit")
    elif lo or hi:
        out["asking_rent_usd_month"] = float(lo or hi)
        out["notes"]["asking_rent_usd_month"] = "Community asking rent (CoStar apartment listing, Apartments.com)"
    return out


def record_for_sid(sid: str) -> dict[str, Any] | None:
    """CoStar facts for a Matterport model, joined by model id. None in fixture mode, without a kit, or
    when the kit has no record for the model. A residential listing (the unit itself) wins over the
    commercial property record (the building)."""
    if config.effective_data_mode() == "fixture" or not config.COSTAR_KIT_ZIP or not Path(config.COSTAR_KIT_ZIP).exists():
        return None
    if sid in _SID_CACHE:
        return _SID_CACHE[sid]
    result: dict[str, Any] | None = None
    try:
        commercial_ids, listing_ids = _keys_for_sid(sid)
        listings = _records_by_id("data/residential-listings.jsonl", listing_ids)
        if listings:
            result = _from_residential(listings[next(i for i in listing_ids if i in listings)])
        elif commercial_ids:
            props = _records_by_id("data/commercial-property.jsonl", commercial_ids)
            if props:
                pid = next(i for i in commercial_ids if i in props)
                result = _from_commercial(props[pid], _apartment_listing(pid))
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
        result = None  # a wrong password or damaged kit: the layer is reported unavailable, not fatal
    _SID_CACHE[sid] = result
    return result


def _map_costar_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map arbitrary CoStar CSV row columns to standard fields."""
    normalized: dict[str, Any] = {}
    for k, v in row.items():
        k_lower = k.lower().replace(" ", "_").replace("-", "_")
        if not v or v == "None":
            continue

        if "year_built" in k_lower or "built_year" in k_lower or k_lower == "built":
            try:
                normalized["year_built"] = int(float(v))
            except ValueError:
                pass
        elif "unit" in k_lower and ("count" in k_lower or "total" in k_lower or k_lower == "units"):
            try:
                normalized["units"] = int(float(v))
            except ValueError:
                pass
        elif "rent" in k_lower or "asking" in k_lower:
            try:
                cleaned = str(v).replace("$", "").replace(",", "")
                normalized["asking_rent_usd_month"] = float(cleaned)
            except ValueError:
                pass
        elif "area" in k_lower or "sqft" in k_lower or "gfa" in k_lower:
            try:
                cleaned = str(v).replace(",", "")
                sqft = float(cleaned)
                # Convert sqft to m2 if large
                if sqft > 500:
                    normalized["unit_floor_area_m2"] = round(sqft * 0.092903, 1)
                else:
                    normalized["unit_floor_area_m2"] = sqft
            except ValueError:
                pass

    return normalized
