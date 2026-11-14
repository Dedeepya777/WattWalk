"""Savings formulas and interactions.

Owner: Person 1.
See plan/plan.md section 10.4 and Appendix A.2.
"""
from __future__ import annotations

from wattwalk.engine.assumptions import AssumptionContext
from wattwalk.engine.baseline import BaselineState


def apply_upgrade(upgrade_id: str, state: BaselineState, ctx: AssumptionContext) -> tuple[float, str]:
    """Apply an upgrade to the mutable BaselineState in canonical stage order.

    Returns:
        (saved_kwh, explanation_str)
    """
    if upgrade_id == "window_film":
        raw = state.window_m2 * ctx.get("window_solar_cooling_kwh_per_m2_yr") * ctx.get("window_film_reduction")
        cap_frac = ctx.get("window_film_cap_fraction")
        cap = state.cooling * cap_frac
        saved = min(raw, cap)
        state.cooling -= saved

        solar_rate = ctx.get("window_solar_cooling_kwh_per_m2_yr")
        reduction = ctx.get("window_film_reduction")
        if raw < cap:
            cap_note = f"cap not reached: max {int(round(cap_frac * 100))}% of cooling"
        else:
            cap_note = f"cap reached: max {int(round(cap_frac * 100))}% of cooling"
        explanation = f"{state.window_m2:.1f} m2 window x {solar_rate:g} kWh/m2/yr x {reduction:.2f} = {round(saved, 1):.1f} kWh/yr ({cap_note})"
        return saved, explanation

    elif upgrade_id == "led":
        bulb_w_inc = ctx.get("bulb_w_incandescent")
        bulb_w_led = ctx.get("bulb_w_led")
        hours_day = ctx.get("lighting_hours_per_day")
        saved = state.n_other * (bulb_w_inc - bulb_w_led) * hours_day * 365.0 / 1000.0
        state.lighting -= saved

        bulb_noun = "bulb" if state.n_other == 1 else "bulbs"
        explanation = f"{state.n_other} {bulb_noun} x ({bulb_w_inc:g} W - {bulb_w_led:g} W) x {hours_day:g} h/day x 365 / 1000 = {round(saved, 1):.1f} kWh/yr"
        return saved, explanation

    elif upgrade_id == "fridge":
        fridge_old = ctx.get("fridge_kwh_yr_old")
        fridge_new = ctx.get("fridge_kwh_yr_new")
        saved = state.n_fridge * (fridge_old - fridge_new)
        state.fridge -= saved

        fridge_noun = "refrigerator" if state.n_fridge == 1 else "refrigerators"
        explanation = f"{state.n_fridge} {fridge_noun} x ({fridge_old:g} - {fridge_new:g}) kWh/yr = {round(saved, 1):.1f} kWh/yr"
        return saved, explanation

    elif upgrade_id == "heat_pump":
        eer_old = ctx.get("eer_window_ac_old")
        eer_new = ctx.get("eer_heat_pump_new")
        prior_cooling = state.cooling
        saved = prior_cooling * (1.0 - eer_old / eer_new)
        state.cooling -= saved

        explanation = f"{prior_cooling:.1f} kWh cooling after earlier upgrades x (1 - {eer_old:g} / {eer_new:g}) = {round(saved, 1):.1f} kWh/yr"
        return saved, explanation

    elif upgrade_id == "smart_thermostat":
        fraction = ctx.get("thermostat_hvac_savings_fraction")
        prior_cooling = state.cooling
        saved = prior_cooling * fraction
        state.cooling -= saved

        explanation = f"{prior_cooling:.1f} kWh cooling after earlier upgrades x {fraction:.2f} = {round(saved, 1):.1f} kWh/yr"
        return saved, explanation

    else:
        raise ValueError(f"Unknown upgrade_id: {upgrade_id}")
