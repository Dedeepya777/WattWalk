"""Test template explanation generator against explain_response.json.

Owner: Person 1.
See plan/prompt_1.md section E Stage 2 and acceptance criteria G.
"""
from __future__ import annotations

import json

import pytest
from wattwalk import config
from wattwalk.contracts import Asset, Building, PlanRequest
from wattwalk.engine import explain_template, plan


def test_explain_template_exact_match() -> None:
    inv_path = config.EXAMPLES_DIR / "inventory.json"
    with open(inv_path, "r", encoding="utf-8") as f:
        inv = [Asset.model_validate(x) for x in json.load(f)]

    bld_path = config.EXAMPLES_DIR / "building.json"
    with open(bld_path, "r", encoding="utf-8") as f:
        bld = Building.model_validate(json.load(f))

    req_path = config.EXAMPLES_DIR / "plan_request_owner_5000_max_bill.json"
    with open(req_path, "r", encoding="utf-8") as f:
        req = PlanRequest.model_validate(json.load(f))

    plan_resp = plan("fixtureUnitA", inv, bld, req)

    expected_path = config.EXAMPLES_DIR / "explain_response.json"
    with open(expected_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    actual_text = explain_template(plan_resp, "heat_pump")
    assert actual_text == expected["text"]
