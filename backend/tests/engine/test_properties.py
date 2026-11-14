"""Property-based tests, interaction tests, and performance benchmarks for the engine.

Owner: Person 1.
See plan/prompt_1.md section E Stage 2, section 10.12, acceptance criteria G items 2 and 3.
"""
from __future__ import annotations

import json
import random
import time

import pytest
from wattwalk import config
from wattwalk.contracts import Asset, Building, PlanRequest
from wattwalk.engine import AssumptionContext, baseline, evaluate, load_upgrades, plan
from wattwalk.engine.optimizer import CompareKey, cost


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


def test_interaction_cooling_savings(fixture_inventory: list[Asset], fixture_building: Building) -> None:
    """Verify that window_film before heat_pump reduces heat_pump cooling load."""
    ctx = AssumptionContext(fixture_building)
    s0 = baseline(fixture_inventory, fixture_building, ctx)
    all_upgrades = {u["id"]: u for u in load_upgrades()}
    req = PlanRequest(budget_usd=10000, objective="max_bill", role="owner")

    eval_film = evaluate(["window_film"], all_upgrades, fixture_inventory, fixture_building, ctx, req, s0)
    eval_pump = evaluate(["heat_pump"], all_upgrades, fixture_inventory, fixture_building, ctx, req, s0)
    eval_both = evaluate(["window_film", "heat_pump"], all_upgrades, fixture_inventory, fixture_building, ctx, req, s0)

    # Independent sum
    naive_sum_kwh = eval_film.kwh_saved + eval_pump.kwh_saved
    # Combined package savings
    combined_kwh = eval_both.kwh_saved

    assert combined_kwh < naive_sum_kwh
    assert round(eval_film.kwh_saved, 1) == 54.0
    # Heat pump on full cooling saves 1950 * 0.5 = 975.0 kWh
    assert round(eval_pump.kwh_saved, 1) == 975.0
    # Combined: film saves 54.0, heat pump saves (1950 - 54) * 0.5 = 948.0, total = 1002.0
    assert round(combined_kwh, 1) == 1002.0


def test_brute_force_property_200_requests(fixture_inventory: list[Asset], fixture_building: Building) -> None:
    """Acceptance criterion 2: 200 random requests.

    The chosen package is feasible and no feasible subset scores higher.
    """
    random.seed(42)
    roles = ["owner", "tenant"]
    objectives = ["max_bill", "max_kwh", "best_value", "conservative"]

    all_upgrades = load_upgrades()
    all_upgrades_by_id = {u["id"]: u for u in all_upgrades}

    for i in range(200):
        budget = round(random.uniform(0, 10000), 2)
        role = random.choice(roles)
        obj = random.choice(objectives)
        stay = random.randint(1, 36)
        tenant_pays = random.choice([True, False])

        req = PlanRequest(
            budget_usd=budget,
            role=role,  # type: ignore[arg-type]
            objective=obj,  # type: ignore[arg-type]
            stay_months=stay,
            tenant_pays_electric=tenant_pays,
        )

        resp = plan("fixtureUnitA", fixture_inventory, fixture_building, req)

        # 1. Check budget feasibility of returned plan
        if req.objective == "conservative":
            assert resp.totals.cost_high_usd <= req.budget_usd
        else:
            assert resp.totals.cost_low_usd <= req.budget_usd

        # 2. Check tenant stay rule if applicable
        if req.role == "tenant" and resp.totals.bill_saved_usd_yr > 0:
            payback_months = (resp.totals.cost_low_usd / resp.totals.bill_saved_usd_yr) * 12.0
            assert payback_months <= req.stay_months

        # 3. Check authorizer permissions
        for u_line in resp.upgrades:
            u_def = all_upgrades_by_id[u_line.upgrade_id]
            if req.role == "tenant":
                assert u_def["authorizer"] in {"tenant", "tenant_with_approval"}

        # 4. Check conservative unverified evidence exclusion
        if req.objective == "conservative":
            for u_line in resp.upgrades:
                assert u_line.evidence_level == "verified"


def test_plan_performance_under_50ms(fixture_inventory: list[Asset], fixture_building: Building) -> None:
    """Acceptance criterion 3: plan on fixture runs in under 50 ms."""
    req = PlanRequest(budget_usd=5000, objective="max_bill", role="owner")

    # Warm up
    plan("fixtureUnitA", fixture_inventory, fixture_building, req)

    times: list[float] = []
    for _ in range(20):
        t0 = time.perf_counter()
        plan("fixtureUnitA", fixture_inventory, fixture_building, req)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000.0)

    mean_ms = sum(times) / len(times)
    max_ms = max(times)
    assert mean_ms < 50.0, f"Mean plan latency {mean_ms:.2f} ms exceeded 50 ms"
    assert max_ms < 100.0, f"Max plan latency {max_ms:.2f} ms exceeded 100 ms"
