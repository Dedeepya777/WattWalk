"""CoStar data kit adapter.

Owner: Person 1.
See plan/plan.md section 13.2, Appendix A.1.3.
"""
from __future__ import annotations

import csv
import os
import zipfile
from pathlib import Path
from typing import Any

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
