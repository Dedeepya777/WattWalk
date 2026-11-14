"""Package evaluation and costing.

Owner: Person 1.
See plan/plan.md section 10.3, 10.4 and Appendix A.2.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from wattwalk.contracts import Asset, Building, PlanRequest, UpgradeLine
from wattwalk.engine.assumptions import AssumptionContext
from wattwalk.engine.baseline import BaselineState
from wattwalk.engine.savings import apply_upgrade
from wattwalk.engine.stakeholders import evidence_level, who_pays

STAGE_ORDER = {"load": 0, "equipment": 1, "controls": 2}


@dataclass
class PackageEval:
    upgrade_ids: tuple[str, ...]
    cost_low: float
    cost_high: float
    kwh_saved: float
    usd_saved: float
    lines: list[UpgradeLine]
    final_state: BaselineState


def cost(upgrade: dict[str, Any], inventory: list[Asset], s0: BaselineState) -> tuple[float, float]:
    """Calculate low and high cost for a single upgrade."""
    basis = upgrade["cost_basis"]
    if basis == "per_m2_window":
        n = s0.window_m2
    elif basis == "per_bulb":
        n = float(s0.n_other)
    elif basis == "per_asset":
        n = float(sum(1 for a in inventory if a.label in upgrade["applies_to"]))
    elif basis == "per_unit_flat":
        # Flat per apartment unit when target asset is present
        target_count = sum(1 for a in inventory if a.label in upgrade["applies_to"])
        n = 1.0 if target_count > 0 else 0.0
    else:
        raise ValueError(f"Unknown cost basis: {basis}")

    low = float(upgrade["cost_low_usd"]) * n
    high = float(upgrade["cost_high_usd"]) * n
    return low, high


def evaluate(
    upgrade_ids: Sequence[str],
    all_upgrades_by_id: dict[str, dict[str, Any]],
    inventory: list[Asset],
    building: Building,
    ctx: AssumptionContext,
    req: PlanRequest,
    s0: BaselineState,
) -> PackageEval:
    """Evaluate a subset of upgrades in canonical stage order."""
    selected_upgrades = [all_upgrades_by_id[uid] for uid in upgrade_ids]
    # Canonical application order: stage (load, equipment, controls), then id alphabetically
    ordered_upgrades = sorted(
        selected_upgrades,
        key=lambda u: (STAGE_ORDER.get(u.get("stage", "load"), 99), u["id"]),
    )

    state = s0.clone()
    rate = ctx.get("electricity_rate_usd_per_kwh")

    lines: list[UpgradeLine] = []
    tot_cost_low = 0.0
    tot_cost_high = 0.0

    for u in ordered_upgrades:
        u_id = u["id"]
        c_low, c_high = cost(u, inventory, s0)
        tot_cost_low += c_low
        tot_cost_high += c_high

        saved_kwh, explanation = apply_upgrade(u_id, state, ctx)
        saved_bill = saved_kwh * rate

        target_assets = [a for a in inventory if a.label in u["applies_to"]]
        asset_ids = [a.id for a in target_assets]
        ev = evidence_level(u, inventory)
        wp = who_pays(u, req)

        lines.append(
            UpgradeLine(
                upgrade_id=u_id,
                name=u["name"],
                cost_low_usd=round(c_low, 2),
                cost_high_usd=round(c_high, 2),
                kwh_saved_yr=round(saved_kwh, 1),
                bill_saved_usd_yr=round(saved_bill, 2),
                explanation=explanation,
                asset_ids=asset_ids,
                evidence_level=ev,  # type: ignore[arg-type]
                who_pays=wp,
            )
        )

    kwh_saved = s0.total - state.total
    usd_saved = kwh_saved * rate

    return PackageEval(
        upgrade_ids=tuple(u["id"] for u in ordered_upgrades),
        cost_low=tot_cost_low,
        cost_high=tot_cost_high,
        kwh_saved=kwh_saved,
        usd_saved=usd_saved,
        lines=lines,
        final_state=state,
    )
