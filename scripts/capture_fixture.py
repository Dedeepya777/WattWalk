"""Capture live geometry and building context to fixtures/live/<sid>/.

Owner: Person 1.
Usage:
    python scripts/capture_fixture.py <sid>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add backend to sys.path so scripts can run standalone
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from wattwalk import config
from wattwalk.data.building import get_building
from wattwalk.data.matterport import get_geometry


def capture(sid: str) -> None:
    print(f"Capturing fixture for sid: {sid}...")

    # Fetch geometry and building (live mode should be active or requested)
    geom = get_geometry(sid)
    bld = get_building(sid, geom)

    out_dir = config.FIXTURES_DIR / "live" / sid
    out_dir.mkdir(parents=True, exist_ok=True)

    geom_data = geom.model_dump(mode="json")
    geom_data["status"] = "fixture"

    bld_data = bld.model_dump(mode="json")
    if "layer_status" in bld_data and isinstance(bld_data["layer_status"], dict):
        for k in bld_data["layer_status"]:
            if bld_data["layer_status"][k] == "live":
                bld_data["layer_status"][k] = "fixture"
    if "roof" in bld_data and isinstance(bld_data["roof"], dict):
        if bld_data["roof"].get("status") == "live":
            bld_data["roof"]["status"] = "fixture"
        if bld_data["roof"].get("ortho_ref"):
            bld_data["roof"]["ortho_ref"] = "vexcel/ortho.jpg"

    geom_file = out_dir / "geometry.json"
    geom_file.write_text(json.dumps(geom_data, indent=2), encoding="utf-8")

    bld_file = out_dir / "building.json"
    bld_file.write_text(json.dumps(bld_data, indent=2), encoding="utf-8")

    print(f"Saved: {geom_file}")
    print(f"Saved: {bld_file}")
    print("\nSummary:")
    print(f"  Rooms count: {len(geom.rooms)}")
    print(f"  Panos count: {len(geom.panos)}")
    print(f"  Walls count: {len(geom.walls)}")
    print(f"  Geometry status: {geom_data['status']}")
    print(f"  Building address: {bld.address} ({bld.city})")
    print(f"  Layer statuses: {bld_data.get('layer_status')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture live geometry and building fixtures for a model sid")
    parser.add_argument("sid", help="Model scan ID (e.g. r1NfhYW4TAr)")
    args = parser.parse_args()
    capture(args.sid)


if __name__ == "__main__":
    main()
