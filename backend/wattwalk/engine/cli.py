"""Command-line interface for the savings engine.

Owner: Person 1.
Usage:
    python -m wattwalk.engine.cli --inventory <json> --building <json> --request <json> [--sid <sid>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from wattwalk.contracts import Asset, Building, PlanRequest
from wattwalk.engine.optimizer import plan


def main() -> None:
    parser = argparse.ArgumentParser(description="WattWalk Savings Engine CLI")
    parser.add_argument("--inventory", required=True, type=Path, help="Path to inventory JSON")
    parser.add_argument("--building", required=True, type=Path, help="Path to building JSON")
    parser.add_argument("--request", required=True, type=Path, help="Path to plan request JSON")
    parser.add_argument("--sid", default="fixtureUnitA", help="Scan ID (default: fixtureUnitA)")

    args = parser.parse_args()

    with open(args.inventory, "r", encoding="utf-8") as f:
        inv_data = json.load(f)
    inventory = [Asset.model_validate(item) for item in inv_data]

    with open(args.building, "r", encoding="utf-8") as f:
        b_data = json.load(f)
    building = Building.model_validate(b_data)

    with open(args.request, "r", encoding="utf-8") as f:
        req_data = json.load(f)
    req = PlanRequest.model_validate(req_data)

    response = plan(args.sid, inventory, building, req)
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
