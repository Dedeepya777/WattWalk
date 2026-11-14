"""Building context aggregator and adapter.

Owner: Person 1.
See plan/plan.md section 7.5, 13.1 to 13.4, and Appendix A.1.3.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wattwalk import config
from wattwalk.contracts import (
    Attr,
    Building,
    City,
    EbeweRecord,
    LayerStatus,
    ModelGeometry,
    Roof,
)
from wattwalk.data import costar, ebewe, index, vexcel


def get_building(sid: str, geometry: ModelGeometry) -> Building:
    """Aggregate building context from CoStar, EBEWE, and Vexcel with honest status reporting."""
    mode = config.effective_data_mode()

    if mode == "fixture":
        if sid == config.FIXTURE_SID:
            fixture_path = config.EXAMPLES_DIR / "building.json"
            with open(fixture_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Building.model_validate(data)

        live_fix = config.FIXTURES_DIR / "live" / sid / "building.json"
        if live_fix.exists():
            with open(live_fix, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Building.model_validate(data)

    idx = index.lookup(sid)
    addr = geometry.address or (idx.address if idx else "Unknown Address")
    city_val: City = "Houston" if (idx and idx.city == "Houston") else "Los Angeles"
    costar_prop_id = idx.costar_property_id if idx else None
    homes_id = idx.homes_listing_id if idx else None

    # 1. CoStar layer
    costar_data = None
    layer_costar = costar.kit_status()
    try:
        # Join by Matterport model id first (the kit's starter CSVs carry it); the index-id join is a fallback.
        costar_data = costar.record_for_sid(sid) or costar.costar_record(costar_prop_id, homes_id)
        if costar_data:
            layer_costar = "live"
            costar_prop_id = costar_data.get("costar_property_id") or costar_prop_id
    except Exception:
        layer_costar = "unavailable"
    costar_notes = (costar_data or {}).get("notes", {})

    # 2. EBEWE layer (Los Angeles only)
    ebewe_rec: EbeweRecord | None = None
    layer_ebewe = "unavailable"
    if city_val == "Los Angeles":
        try:
            ebewe_rec = ebewe.lookup(addr, city_val)
            layer_ebewe = "live"
        except Exception:
            layer_ebewe = "unavailable"

    # 3. Vexcel layer
    lat = geometry.lat or (idx.lat if idx else None)
    lon = geometry.lon or (idx.lon if idx else None)
    ortho_path = None
    roof_attrs: dict[str, Any] = {}
    layer_vexcel = "unavailable"
    if lat is not None and lon is not None:
        try:
            ortho_path = vexcel.ortho(sid, lat, lon)
            roof_attrs = vexcel.roof_attributes(lat, lon) or {}
            if ortho_path:
                layer_vexcel = "live"
        except Exception:
            layer_vexcel = "unavailable"

    # Field precedence (plan section 7.5)
    # year_built
    if costar_data and "year_built" in costar_data:
        yb_attr = Attr(value=costar_data["year_built"], source="reported_in_data",
                     note=costar_notes.get("year_built", "From CoStar property record"))
    elif ebewe_rec and ebewe_rec.year_built is not None:
        yb_attr = Attr(value=ebewe_rec.year_built, source="reported_in_data", note="From LA EBEWE benchmark record")
    else:
        yb_attr = Attr(value=None, source="needs_verification")

    # units
    if costar_data and "units" in costar_data:
        units_attr = Attr(value=costar_data["units"], source="reported_in_data",
                     note=costar_notes.get("units", "From CoStar property record"))
    else:
        units_attr = Attr(value=None, source="needs_verification")

    # asking_rent_usd_month
    if costar_data and "asking_rent_usd_month" in costar_data:
        rent_attr = Attr(value=costar_data["asking_rent_usd_month"], source="reported_in_data",
                     note=costar_notes.get("asking_rent_usd_month", "From CoStar listing"))
    else:
        rent_attr = Attr(value=None, source="needs_verification")

    # unit_floor_area_m2
    if costar_data and "unit_floor_area_m2" in costar_data:
        area_attr = Attr(value=costar_data["unit_floor_area_m2"], source="reported_in_data", note="From CoStar listing")
    elif geometry.rooms:
        tot_area = round(sum(r.area_m2 for r in geometry.rooms), 1)
        if tot_area > 0:
            area_attr = Attr(value=tot_area, source="reported_in_data", note="Sum of room floor areas from Matterport scan")
        else:
            area_attr = Attr(value=None, source="needs_verification")
    else:
        area_attr = Attr(value=None, source="needs_verification")

    layer_status = LayerStatus(
        matterport=geometry.status,
        costar=layer_costar,
        vexcel=layer_vexcel,
        ebewe=layer_ebewe,
    )

    roof = Roof(
        status=layer_vexcel,
        attributes=roof_attrs,
        ortho_ref=str(ortho_path) if ortho_path else None,
    )

    return Building(
        address=addr,
        city=city_val,
        costar_property_id=costar_prop_id,
        year_built=yb_attr,
        units=units_attr,
        asking_rent_usd_month=rent_attr,
        unit_floor_area_m2=area_attr,
        ebewe=ebewe_rec,
        roof=roof,
        layer_status=layer_status,
    )
