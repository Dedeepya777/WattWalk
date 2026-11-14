"""Template explanation generator.

Owner: Person 1.
See plan/plan.md section 10.11 and Appendix A.2.
"""
from __future__ import annotations

from wattwalk.contracts import PlanResponse


def explain_template(plan: PlanResponse, upgrade_id: str) -> str:
    """Return a short deterministic explanation paragraph built only from plan numbers."""
    matching_line = None
    for line in plan.upgrades:
        if line.upgrade_id == upgrade_id:
            matching_line = line
            break

    if matching_line is None:
        raise ValueError(f"Upgrade {upgrade_id} is not part of the plan")

    rate_val = 0.30
    for a in plan.assumptions_used:
        if a.key == "electricity_rate_usd_per_kwh":
            rate_val = float(a.value)
            break

    rate_str = f"${rate_val:.2f}/kWh"
    bill_str = f"${matching_line.bill_saved_usd_yr:.2f} per year"
    cost_str = f"Cost range ${int(round(matching_line.cost_low_usd)):,} to ${int(round(matching_line.cost_high_usd)):,}"

    # Who decides and receives savings
    if matching_line.who_pays.approval == "owner_decision":
        decides = "the owner decides"
    elif matching_line.who_pays.approval == "landlord_approval":
        decides = "the tenant decides with landlord approval"
    else:
        if matching_line.who_pays.pays == "owner":
            decides = "the owner decides"
        elif matching_line.who_pays.pays == "tenant":
            decides = "the tenant decides"
        else:
            decides = "either owner or tenant decides"

    saves = f"and the {matching_line.who_pays.saves} receives the bill savings"
    tail = f"{cost_str}; {decides} {saves}."

    if upgrade_id == "heat_pump":
        eer_old = 9.0
        eer_new = 18.0
        for a in plan.assumptions_used:
            if a.key == "eer_window_ac_old":
                eer_old = float(a.value)
            elif a.key == "eer_heat_pump_new":
                eer_new = float(a.value)
        prefix = (
            f"The existing window AC is assumed to run at EER {eer_old:g} (unverified default; its label was not read). "
            f"A ductless heat pump at EER {eer_new:g} would cut the remaining cooling electricity in half: "
        )
    elif upgrade_id == "led":
        prefix = "Bulbs of unknown type are assumed to draw 60 W (unverified default). Upgrading to LED bulbs: "
    elif upgrade_id == "window_film":
        prefix = "Solar heat gain through windows adds to the cooling load. Applying solar control window film: "
    elif upgrade_id == "fridge":
        prefix = "The existing refrigerator is assumed to draw 700 kWh/yr (unverified default). Replacing with an efficient model: "
    elif upgrade_id == "smart_thermostat":
        prefix = "A smart thermostat optimizes HVAC schedules. Upgrading thermostat: "
    else:
        prefix = ""

    return f"{prefix}{matching_line.explanation}. At {rate_str} that is {bill_str}. {tail}"
