"""Heat shares for floor plan heat map.

Owner: Person 1.
See plan/plan.md section 10.8 and Appendix A.2.
"""
from __future__ import annotations

from wattwalk.contracts import Asset, Building, HeatShare, Room
from wattwalk.engine.assumptions import AssumptionContext


def heat_shares(rooms: list[Room], inventory: list[Asset], building: Building) -> list[HeatShare]:
    """Compute relative cooling pressure weights and shares per room in geometry order."""
    ctx = AssumptionContext(building)
    vol_weight = ctx.get("heat_share_volume_weight_per_m3")
    win_weight = ctx.get("heat_share_window_weight_per_m2")
    def_height = ctx.get("default_room_height_m")

    # Map window areas by room_id
    win_area_by_room: dict[str, float] = {}
    for a in inventory:
        if a.label == "window" and a.room_id is not None:
            wa = a.attrs.get("area_m2")
            if wa is not None and wa.value is not None and isinstance(wa.value, (int, float)):
                win_area_by_room[a.room_id] = win_area_by_room.get(a.room_id, 0.0) + float(wa.value)

    weights: list[tuple[Room, float]] = []
    for r in rooms:
        h = r.height_m if (r.height_m is not None and r.height_m > 0) else def_height
        w_m2 = win_area_by_room.get(r.id, 0.0)
        raw_w = (r.area_m2 * h * vol_weight) + (w_m2 * win_weight)
        rounded_w = round(raw_w, 1)
        weights.append((r, rounded_w))

    tot_weight = sum(w for _, w in weights)
    results: list[HeatShare] = []
    for r, w in weights:
        share = round(w / tot_weight, 3) if tot_weight > 0 else 0.0
        results.append(HeatShare(room_id=r.id, share=share, weight=w))

    return results
