"""Baseline energy calculation.

Owner: Person 1.
See plan/plan.md section 10.2 and Appendix A.2.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from wattwalk.contracts import Asset, Building
from wattwalk.engine.assumptions import AssumptionContext


@dataclass
class BaselineState:
    cooling: float
    lighting: float
    fridge: float
    window_m2: float
    n_led: int
    n_other: int
    n_fridge: int
    area_m2: float
    has_cfl: bool = False
    has_unknown_bulb_type: bool = False

    @property
    def total(self) -> float:
        return self.cooling + self.lighting + self.fridge

    def clone(self) -> BaselineState:
        return copy.deepcopy(self)


def baseline(inventory: list[Asset], building: Building, ctx: AssumptionContext) -> BaselineState:
    """Compute deterministic baseline state for cooling, lighting, and refrigeration."""
    unit_area = building.unit_floor_area_m2.value
    if unit_area is not None and isinstance(unit_area, (int, float)) and unit_area > 0:
        area_m2 = float(unit_area)
    else:
        area_m2 = ctx.get("default_unit_floor_area_m2")

    cooling_rate = ctx.get("cooling_kwh_per_m2_yr")
    cooling = area_m2 * cooling_rate

    n_led = 0
    n_other = 0
    has_cfl = False
    has_unknown_bulb_type = False

    for asset in inventory:
        if asset.label in {"ceiling_light", "lamp"}:
            bc = asset.attrs.get("bulb_count")
            if bc is not None and bc.value is not None and isinstance(bc.value, (int, float)):
                n = int(bc.value)
            else:
                n = int(ctx.get("default_bulb_count_per_fixture"))

            bt = asset.attrs.get("bulb_type")
            b_val = bt.value if bt is not None else None
            if b_val == "led":
                n_led += n
            else:
                n_other += n
                if b_val == "cfl":
                    has_cfl = True
                if b_val is None:
                    has_unknown_bulb_type = True

    bulb_w_inc = ctx.get("bulb_w_incandescent")
    bulb_w_led = ctx.get("bulb_w_led")
    hours_day = ctx.get("lighting_hours_per_day")

    lighting = (n_other * bulb_w_inc + n_led * bulb_w_led) * hours_day * 365.0 / 1000.0

    n_fridge = sum(1 for a in inventory if a.label == "refrigerator")
    fridge_old = ctx.get("fridge_kwh_yr_old")
    fridge = n_fridge * fridge_old

    window_m2 = 0.0
    for a in inventory:
        if a.label == "window":
            wa = a.attrs.get("area_m2")
            if wa is not None and wa.value is not None and isinstance(wa.value, (int, float)):
                window_m2 += float(wa.value)

    return BaselineState(
        cooling=cooling,
        lighting=lighting,
        fridge=fridge,
        window_m2=window_m2,
        n_led=n_led,
        n_other=n_other,
        n_fridge=n_fridge,
        area_m2=area_m2,
        has_cfl=has_cfl,
        has_unknown_bulb_type=has_unknown_bulb_type,
    )
