"""Exact optimizer and plan generator.

Owner: Person 1.
See plan/plan.md section 10.5, 10.6, 10.9 and Appendix A.2.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any

from wattwalk.contracts import (
    Asset,
    Building,
    Exclusion,
    PlanRequest,
    PlanResponse,
    PlanTotals,
    UpgradeLine,
)
from wattwalk.engine.assumptions import AssumptionContext, load_upgrades
from wattwalk.engine.baseline import baseline
from wattwalk.engine.packages import cost, evaluate


@dataclass
class CompareKey:
    obj_val: float
    kwh_saved: float
    neg_cost_low: float
    neg_n: int
    ids_str: str

    def __lt__(self, other: CompareKey) -> bool:
        s_obj = round(self.obj_val, 9)
        o_obj = round(other.obj_val, 9)
        if s_obj != o_obj:
            return s_obj < o_obj

        s_kwh = round(self.kwh_saved, 9)
        o_kwh = round(other.kwh_saved, 9)
        if s_kwh != o_kwh:
            return s_kwh < o_kwh

        if self.neg_cost_low != other.neg_cost_low:
            return self.neg_cost_low < other.neg_cost_low

        if self.neg_n != other.neg_n:
            return self.neg_n < other.neg_n

        # Tie-breaker: lexicographically smallest comma-joined id list wins
        return self.ids_str > other.ids_str


def plan(sid: str, inventory: list[Asset], building: Building, req: PlanRequest) -> PlanResponse:
    """Generate optimal upgrade plan with deterministic baseline, exact enumeration, and constraints."""
    ctx = AssumptionContext(building, overrides=req.overrides)
    s0 = baseline(inventory, building, ctx)
    rate = ctx.get("electricity_rate_usd_per_kwh")

    all_upgrades = load_upgrades()
    all_upgrades_by_id = {u["id"]: u for u in all_upgrades}

    inventory_labels = {a.label for a in inventory}

    candidates: list[dict[str, Any]] = []
    initial_exclusions: dict[str, Exclusion] = {}

    # 10.5 Candidate filtering in upgrades.json order
    for u in all_upgrades:
        u_id = u["id"]
        applies_to = u.get("applies_to", [])
        target_assets = [a for a in inventory if a.label in applies_to]

        # 1. If no asset matches applies_to: omit entirely (not reported)
        if not target_assets:
            continue

        # 2. If requires_labels contains a label not present in the inventory: exclude missing_dependency
        req_labels = u.get("requires_labels", [])
        if any(lbl not in inventory_labels for lbl in req_labels):
            initial_exclusions[u_id] = Exclusion(
                upgrade_id=u_id,
                reason_code="missing_dependency",
                reason="Missing required asset label in inventory.",
            )
            continue

        # 3. If skip_if_all is set and every target asset has attr == equals: exclude already_efficient
        skip = u.get("skip_if_all")
        if skip:
            attr_name = skip["attr"]
            eq_val = skip["equals"]
            if all(
                a.attrs.get(attr_name) is not None and a.attrs[attr_name].value == eq_val
                for a in target_assets
            ):
                initial_exclusions[u_id] = Exclusion(
                    upgrade_id=u_id,
                    reason_code="already_efficient",
                    reason=f"All {len(target_assets)} matching assets already have {attr_name} = {eq_val}.",
                )
                continue

        # 4. If authorizer not allowed for role: exclude not_authorized
        authorizer = u.get("authorizer", "owner")
        if req.role == "tenant" and authorizer not in {"tenant", "tenant_with_approval"}:
            initial_exclusions[u_id] = Exclusion(
                upgrade_id=u_id,
                reason_code="not_authorized",
                reason="Requires an owner decision; current role is tenant.",
            )
            continue

        # 5. If objective is conservative and any target asset has any depends_on_attrs unknown: exclude unverified_evidence
        if req.objective == "conservative":
            depends = u.get("depends_on_attrs", [])
            unverified: list[str] = []
            for attr_name in depends:
                if any(
                    a.attrs.get(attr_name) is None or a.attrs[attr_name].value is None
                    for a in target_assets
                ):
                    unverified.append(attr_name)
            if unverified:
                initial_exclusions[u_id] = Exclusion(
                    upgrade_id=u_id,
                    reason_code="unverified_evidence",
                    reason=f"Conservative mode excludes upgrades that depend on unverified attributes: {', '.join(unverified)}.",
                )
                continue

        # 6. If upgrade's own cost exceeds budget: exclude over_budget
        c_low, c_high = cost(u, inventory, s0)
        if req.objective == "conservative":
            if c_high > req.budget_usd:
                initial_exclusions[u_id] = Exclusion(
                    upgrade_id=u_id,
                    reason_code="over_budget",
                    reason=f"The upper cost estimate ${int(round(c_high)):,} alone exceeds the budget ${int(round(req.budget_usd)):,}.",
                )
                continue
        else:
            if c_low > req.budget_usd:
                initial_exclusions[u_id] = Exclusion(
                    upgrade_id=u_id,
                    reason_code="over_budget",
                    reason=f"The lowest cost estimate ${int(round(c_low)):,} alone exceeds the budget ${int(round(req.budget_usd)):,}.",
                )
                continue

        # 7. Otherwise it is a candidate
        candidates.append(u)

    # 10.6 Optimizer enumeration
    n_candidates = len(candidates)
    combos_evaluated = (2**n_candidates - 1) if n_candidates > 0 else 0

    best_pkg = None
    best_key: CompareKey | None = None

    # Track packages that passed budget test and stay rule for reporting exclusions
    candidate_passed_budget: dict[str, bool] = {u["id"]: False for u in candidates}
    candidate_passed_stay: dict[str, bool] = {u["id"]: False for u in candidates}

    # Enumerate non-empty subsets in increasing size, then combinations order
    for size in range(1, n_candidates + 1):
        for combo in itertools.combinations(candidates, size):
            combo_ids = [u["id"] for u in combo]

            # 1. Mutual exclusions
            skip_combo = False
            for u in combo:
                for excl in u.get("excludes", []):
                    if excl in combo_ids:
                        skip_combo = True
                        break
                if skip_combo:
                    break
            if skip_combo:
                continue

            # 2. Missing requires
            for u in combo:
                for req_u in u.get("requires", []):
                    if req_u not in combo_ids:
                        skip_combo = True
                        break
                if skip_combo:
                    break
            if skip_combo:
                continue

            # 3. Budget test
            subset_cost_low = sum(cost(u, inventory, s0)[0] for u in combo)
            subset_cost_high = sum(cost(u, inventory, s0)[1] for u in combo)

            if req.objective == "conservative":
                if subset_cost_high > req.budget_usd:
                    continue
            else:
                if subset_cost_low > req.budget_usd:
                    continue

            for u_id in combo_ids:
                candidate_passed_budget[u_id] = True

            # 4. Evaluate savings
            pkg = evaluate(combo_ids, all_upgrades_by_id, inventory, building, ctx, req, s0)

            # 5. Tenant stay rule
            if req.role == "tenant":
                if pkg.usd_saved <= 0:
                    continue
                payback_months = (pkg.cost_low / pkg.usd_saved) * 12.0
                if payback_months > req.stay_months:
                    continue

            for u_id in combo_ids:
                candidate_passed_stay[u_id] = True

            # 6. Compute objective key
            if req.objective == "max_bill":
                obj_val = pkg.usd_saved
            elif req.objective == "max_kwh":
                obj_val = pkg.kwh_saved
            elif req.objective == "best_value":
                obj_val = pkg.usd_saved / max(pkg.cost_low, 1.0)
            elif req.objective == "conservative":
                obj_val = pkg.usd_saved
            else:
                obj_val = pkg.usd_saved

            key = CompareKey(
                obj_val=obj_val,
                kwh_saved=pkg.kwh_saved,
                neg_cost_low=-pkg.cost_low,
                neg_n=-len(combo_ids),
                ids_str=",".join(sorted(combo_ids)),
            )

            if best_key is None or key > best_key:
                best_key = key
                best_pkg = pkg

    winning_uids = set(best_pkg.upgrade_ids) if best_pkg else set()

    # 10.6.4 Candidate exclusions
    candidate_exclusions: dict[str, Exclusion] = {}
    for u in candidates:
        u_id = u["id"]
        if u_id not in winning_uids:
            if req.role == "tenant" and not candidate_passed_stay[u_id]:
                candidate_exclusions[u_id] = Exclusion(
                    upgrade_id=u_id,
                    reason_code="stay_too_short",
                    reason=f"No package including this upgrade recovers its cost within the {req.stay_months}-month stay.",
                )
            else:
                candidate_exclusions[u_id] = Exclusion(
                    upgrade_id=u_id,
                    reason_code="not_selected",
                    reason="Feasible, but the chosen package scores higher for this objective.",
                )

    # Excluded ordered by upgrades.json order
    excluded: list[Exclusion] = []
    for u in all_upgrades:
        u_id = u["id"]
        if u_id in initial_exclusions:
            excluded.append(initial_exclusions[u_id])
        elif u_id in candidate_exclusions:
            excluded.append(candidate_exclusions[u_id])

    # Totals
    if best_pkg and best_pkg.lines:
        cost_low_usd = round(best_pkg.cost_low, 2)
        cost_high_usd = round(best_pkg.cost_high, 2)
        kwh_saved_yr = round(best_pkg.kwh_saved, 1)
        bill_saved_usd_yr = round(best_pkg.usd_saved, 2)
        if best_pkg.cost_low > 0 and best_pkg.usd_saved > 0:
            payback_years: float | None = round(best_pkg.cost_low / best_pkg.usd_saved, 2)
        else:
            payback_years = None
        baseline_kwh_yr = round(s0.total, 1)
        after_kwh_yr = round(s0.total - best_pkg.kwh_saved, 1)
        upgrades_list = best_pkg.lines
    else:
        cost_low_usd = 0.0
        cost_high_usd = 0.0
        kwh_saved_yr = 0.0
        bill_saved_usd_yr = 0.0
        payback_years = None
        baseline_kwh_yr = round(s0.total, 1)
        after_kwh_yr = round(s0.total, 1)
        upgrades_list = []

    totals = PlanTotals(
        cost_low_usd=cost_low_usd,
        cost_high_usd=cost_high_usd,
        kwh_saved_yr=kwh_saved_yr,
        bill_saved_usd_yr=bill_saved_usd_yr,
        payback_years=payback_years,
        baseline_kwh_yr=baseline_kwh_yr,
        after_kwh_yr=after_kwh_yr,
    )

    # 10.9 Notes generated by the engine
    notes: list[str] = []

    # 1. Non-conservative and package cost_high > budget
    if req.objective != "conservative" and totals.cost_high_usd > req.budget_usd:
        notes.append(
            f"Upper cost estimate ${int(round(totals.cost_high_usd)):,} exceeds the budget ${int(round(req.budget_usd)):,}. "
            "Choose objective 'conservative' to plan against upper estimates."
        )

    # 2. No feasible package
    if not upgrades_list:
        notes.append("No feasible package for these constraints.")

    # 3. Unknown light bulb type
    if s0.has_unknown_bulb_type and s0.n_other > 0:
        notes.append("Lighting baseline assumes bulbs of unknown type draw 60 W (assumption).")

    # 4. CFL present
    if s0.has_cfl:
        notes.append("CFL bulbs are modelled at incandescent wattage; LED savings for them are overstated.")

    # 5. Building has an EBEWE record and unit area
    unit_area_val = building.unit_floor_area_m2.value
    if building.ebewe is not None and unit_area_val is not None and isinstance(unit_area_val, (int, float)) and unit_area_val > 0:
        kbtu_conv = ctx.get("kbtu_per_ft2_to_kwh_per_m2")
        x_val = s0.total / float(unit_area_val)
        y_val = building.ebewe.site_eui_kbtu_ft2 * kbtu_conv
        r_val = x_val / y_val if y_val > 0 else 0.0
        notes.append(
            f"Context, not validation: modelled end uses (cooling, lighting, refrigerator) = {round(x_val, 1):.1f} kWh/m2/yr; "
            f"LA EBEWE reported building site energy = {round(y_val, 1):.1f} kWh/m2/yr (program year {building.ebewe.program_year}; "
            f"includes gas, common areas and all other end uses). Ratio {round(r_val, 2):.2f}."
        )

    # 6. Unverified default assumptions count
    n_unverified = sum(1 for a in ctx.used() if a.status == "unverified_default")
    if n_unverified > 0:
        notes.append(f"{n_unverified} assumptions are unverified defaults; results are planning estimates.")

    return PlanResponse(
        schema_version="1.0.0",
        sid=sid,
        request=req,
        upgrades=upgrades_list,
        totals=totals,
        excluded=excluded,
        notes=notes,
        assumptions_used=ctx.used(),
        combos_evaluated=combos_evaluated,
    )
