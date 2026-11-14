"""Test exact reproduction of all six plan examples and the correction example.

Owner: Person 1.
See plan/prompt_1.md section E Stage 1 and acceptance criteria G.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from wattwalk import config
from wattwalk.contracts import Asset, Building, PlanRequest, PlanResponse
from wattwalk.engine import plan


@pytest.fixture
def fixture_inventory() -> list[Asset]:
    path = config.EXAMPLES_DIR / "inventory.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Asset.model_validate(item) for item in data]


@pytest.fixture
def fixture_building() -> Building:
    path = config.EXAMPLES_DIR / "building.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Building.model_validate(data)


PLAN_EXAMPLE_PAIRS = [
    ("plan_request_owner_2000_max_bill.json", "plan_response_owner_2000_max_bill.json"),
    ("plan_request_owner_0_boundary.json", "plan_response_owner_0_boundary.json"),
    ("plan_request_owner_5000_max_bill.json", "plan_response_owner_5000_max_bill.json"),
    ("plan_request_owner_5000_conservative.json", "plan_response_owner_5000_conservative.json"),
    ("plan_request_tenant_2000_max_bill.json", "plan_response_tenant_2000_max_bill.json"),
    ("plan_request_tenant_2000_stay1_boundary.json", "plan_response_tenant_2000_stay1_boundary.json"),
]


@pytest.mark.parametrize("req_file,resp_file", PLAN_EXAMPLE_PAIRS)
def test_plan_example_exact_match(
    req_file: str,
    resp_file: str,
    fixture_inventory: list[Asset],
    fixture_building: Building,
) -> None:
    req_path = config.EXAMPLES_DIR / req_file
    with open(req_path, "r", encoding="utf-8") as f:
        req_data = json.load(f)
    req = PlanRequest.model_validate(req_data)

    resp_path = config.EXAMPLES_DIR / resp_file
    with open(resp_path, "r", encoding="utf-8") as f:
        expected_raw = json.load(f)
    expected_resp = PlanResponse.model_validate(expected_raw)

    actual_resp = plan("fixtureUnitA", fixture_inventory, fixture_building, req)

    # Compare full model_dump mode="json"
    actual_dump = actual_resp.model_dump(mode="json")
    expected_dump = expected_resp.model_dump(mode="json")

    assert actual_dump == expected_dump


def test_correction_example_exact_match(fixture_building: Building) -> None:
    corr_resp_path = config.EXAMPLES_DIR / "correction_response.json"
    with open(corr_resp_path, "r", encoding="utf-8") as f:
        corr_resp_data = json.load(f)

    # Use the inventory inside correction_response.json
    corrected_inventory = [Asset.model_validate(item) for item in corr_resp_data["inventory"]]

    corr_req_path = config.EXAMPLES_DIR / "correction_request.json"
    with open(corr_req_path, "r", encoding="utf-8") as f:
        corr_req_data = json.load(f)
    req = PlanRequest.model_validate(corr_req_data["plan_request"])

    expected_plan = PlanResponse.model_validate(corr_resp_data["plan"])

    actual_plan = plan("fixtureUnitA", corrected_inventory, fixture_building, req)

    assert actual_plan.model_dump(mode="json") == expected_plan.model_dump(mode="json")
