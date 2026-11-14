"""Capture live geometry and building context to fixtures/live/<sid>/.

Owner: Person 1.
Usage:
    python scripts/capture_fixture.py <sid>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add backend to sys.path so scripts can run standalone
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from wattwalk import config
from wattwalk.data.building import get_building
from wattwalk.data.matterport import get_geometry


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture live geometry and building fixtures for a model sid")
    parser.add_argument("sid", help="Model scan ID (e.g. 2YKpZqjy5bJ)")
    args = parser.parse_args()

    sid = args.sid
    print(f"Capturing fixture for sid: {sid}...")

    # Fetch geometry and building
    geom = get_geometry(sid)
    bld = get_building(sid, geom)

    out_dir = config.FIXTURES_DIR / "live" / sid
    out_dir.mkdir(parents=True, exist_ok=True)

    geom_file = out_dir / "geometry.json"
    with open(geom_file, "w", encoding="utf-8") as f:
        f.write(geom.model_dump_json(indent=2))

    bld_file = out_dir / "building.json"
    with open(bld_file, "w", encoding="utf-8") as f:
        f.write(bld.model_dump_json(indent=2))

    print(f"Saved: {geom_file}")
    print(f"Saved: {bld_file}")
    print("\nSummary:")
    print(f"  Rooms count: {len(geom.rooms)}")
    print(f"  Panos count: {len(geom.panos)}")
    print(f"  Walls count: {len(geom.walls)}")
    print(f"  Geometry status: {geom.status}")
    print(f"  Building address: {bld.address} ({bld.city})")
    print(f"  Layer statuses: {bld.layer_status.model_dump()}")


if __name__ == "__main__":
    main()
