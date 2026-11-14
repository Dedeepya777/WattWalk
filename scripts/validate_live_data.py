"""Validate live data providers and probes end-to-end.

Owner: Person 1.
Usage:
    python scripts/validate_live_data.py <sid>
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add backend to sys.path so scripts can run standalone
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from wattwalk import config
from wattwalk.data import probes
from wattwalk.data.building import get_building
from wattwalk.data.matterport import get_face_image, get_geometry


def time_call(func, *args, **kwargs):
    t0 = time.perf_counter()
    ok = False
    detail = ""
    res = None
    try:
        res = func(*args, **kwargs)
        ok = True
        elapsed = time.perf_counter() - t0
        return ok, res, elapsed, ""
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return False, None, elapsed, f"{type(exc).__name__}: {exc}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Live data provider validation script")
    parser.add_argument("sid", nargs="?", default="r1NfhYW4TAr", help="Model scan ID (default: r1NfhYW4TAr)")
    args = parser.parse_args()

    sid = args.sid
    print(f"\n================================================================================")
    print(f" WattWalk Live Data Validation: {sid}")
    print(f" Environment: DATA_MODE={config.effective_data_mode()}")
    print(f"================================================================================\n")

    results = []

    # 1. Matterport Geometry
    ok, geom, elapsed, err = time_call(get_geometry, sid)
    detail = f"{len(geom.rooms)} rooms, {len(geom.panos)} panos, {len(geom.walls)} walls" if ok else err
    results.append(("Matterport", "get_geometry", ok, detail, elapsed))

    # 2. Matterport Face 2k
    pano_id = geom.panos[0].id if (geom and geom.panos) else "p01"
    ok, p2k, elapsed, err = time_call(get_face_image, sid, pano_id, 1, "2k")
    detail = f"Pano {pano_id} face 1 (2k): {p2k}" if ok else err
    results.append(("Matterport", "face_download_2k", ok, detail, elapsed))

    # 3. Matterport Face 4k
    ok, p4k, elapsed, err = time_call(get_face_image, sid, pano_id, 1, "4k")
    detail = f"Pano {pano_id} face 1 (4k): {p4k}" if ok else err
    results.append(("Matterport", "face_download_4k", ok, detail, elapsed))

    # 4. Building Composite
    if geom:
        ok, bld, elapsed, err = time_call(get_building, sid, geom)
        if ok:
            detail = f"Addr: {bld.address} | Layers: {bld.layer_status.model_dump()}"
            results.append(("Building", "get_building", ok, detail, elapsed))

            # Breakdown sub-layers
            ebewe_ok = bld.ebewe is not None
            ebewe_detail = f"Site EUI: {bld.ebewe.site_eui_kbtu_ft2}" if bld.ebewe else "No record found"
            results.append(("EBEWE", "building_ebewe", ebewe_ok, ebewe_detail, 0.0))

            costar_ok = bld.layer_status.costar == "live"
            costar_detail = f"PropId: {bld.costar_property_id}, YB: {bld.year_built.value}" if costar_ok else "Not matched in kit"
            results.append(("CoStar", "building_costar", costar_ok, costar_detail, 0.0))

            vexcel_ok = bld.roof.status == "live"
            vexcel_detail = f"Ortho: {bld.roof.ortho_ref}" if vexcel_ok else "Key not configured or 403"
            results.append(("Vexcel", "building_roof", vexcel_ok, vexcel_detail, 0.0))
        else:
            results.append(("Building", "get_building", False, err, elapsed))

    # 5. Probes
    t0 = time.perf_counter()
    m_ok, m_det = probes.probe_matterport()
    results.append(("Matterport", "probe_matterport", m_ok, m_det, time.perf_counter() - t0))

    t0 = time.perf_counter()
    e_ok, e_det = probes.probe_ebewe()
    results.append(("EBEWE", "probe_ebewe", e_ok, e_det, time.perf_counter() - t0))

    t0 = time.perf_counter()
    c_ok, c_det = probes.probe_costar_kit()
    results.append(("CoStar", "probe_costar_kit", c_ok, c_det, time.perf_counter() - t0))

    t0 = time.perf_counter()
    v_ok, v_det = probes.probe_vexcel()
    results.append(("Vexcel", "probe_vexcel", v_ok, v_det, time.perf_counter() - t0))

    # Print Table
    print(f"{'Integration':<12} | {'Operation':<18} | {'Status':<6} | {'Timing (s)':<10} | {'Detail'}")
    print(f"{'-'*12}-+-{'-'*18}-+-{'-'*6}-+-{'-'*10}-+-{'-'*40}")
    for integ, op, ok, det, el in results:
        status_str = "OK" if ok else "FAIL"
        print(f"{integ:<12} | {op:<18} | {status_str:<6} | {el:<10.3f} | {det}")
    print(f"================================================================================\n")


if __name__ == "__main__":
    main()
