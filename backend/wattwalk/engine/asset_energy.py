"""Energy and heat per inventory asset (step 1 of the 3D energy view).

Owner: Person 1 (engine); first version by Person 2. Not yet part of the API contract: the audit
response does not carry these numbers, so nothing in the UI changes until a contract change adds them.

Every number is a (low, high) range built from the same assumptions as the upgrade plan
(shared/contracts/assumptions.json through AssumptionContext), so per-asset numbers add up to the
plan's baseline: the high ends of all lights equal baseline().lighting, the fridges' high ends equal
baseline().fridge, and the cooling units share baseline().cooling. Unknown attributes widen the range
and are listed in ``assumed``; nothing is guessed silently.

Physics used (honest, deliberately simple):
- Electricity used indoors ends up as heat in the room (lights, fridge, electronics). So heat added
  per year equals the electricity used, and the heat while running equals the power draw.
- A window adds sun heat. The sourced assumption is the *cooling electricity* that heat causes per m²
  of window per year; the heat itself is that times the AC's coefficient of performance
  (COP = EER / 3.412, using the old window-AC EER).
- A window AC or mini split moves heat outside: its heat is negative.
Temperatures are not computed: a room's temperature depends on airflow, insulation and weather, which
a scan cannot measure. Heat is reported in kWh per year and in watts.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from typing import Optional

from wattwalk.contracts import Asset, Building
from wattwalk.engine.assumptions import AssumptionContext

HOURS_PER_YEAR = 8760.0
BTU_PER_WH = 3.412
LIGHTS = {"ceiling_light", "lamp"}
COOLING_UNITS = {"window_ac", "mini_split"}
NOT_ESTIMATED = {
    "thermostat": "uses a few watts: negligible",
    "supply_vent": "part of the building's central system; counted in cooling, not per vent",
    "washer": "no sourced assumption yet for washers",
    "dryer": "no sourced assumption yet for dryers",
    "dishwasher": "no sourced assumption yet for dishwashers",
    "range_gas": "no sourced assumption yet for gas ranges (and gas is not electricity)",
    "range_electric": "no sourced assumption yet for electric ranges",
    "water_heater": "no sourced assumption yet for water heaters",
    "ceiling_fan": "no sourced assumption yet for ceiling fans",
}

Range = tuple[float, float]


@dataclass
class AssetEnergy:
    asset_id: str
    label: str
    room_id: Optional[str]
    estimated: bool
    kwh_yr: Optional[Range] = None        # electricity per year caused by this asset
    usd_yr: Optional[Range] = None        # kwh_yr times the electricity rate
    heat_kwh_yr: Optional[Range] = None   # heat added to the room per year (negative: removes heat)
    power_w: Optional[Range] = None       # electrical draw / heat while running (W); average for a fridge
    basis: str = ""                       # one line: how the numbers were made
    assumed: list[str] = field(default_factory=list)   # attributes not seen in the scan
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _value(asset: Asset, attr: str):
    a = asset.attrs.get(attr)
    return a.value if a is not None else None


def _r(low: float, high: float, digits: int = 1) -> Range:
    return (round(low, digits), round(high, digits))


def _money(kwh: Range, rate: float) -> Range:
    return _r(kwh[0] * rate, kwh[1] * rate, 2)


def _light(asset: Asset, ctx: AssumptionContext, rate: float) -> AssetEnergy:
    assumed: list[str] = []
    count = _value(asset, "bulb_count")
    if not isinstance(count, (int, float)):
        count = ctx.get("default_bulb_count_per_fixture")
        assumed.append("bulb_count")
    count = int(count)
    w_led, w_inc = ctx.get("bulb_w_led"), ctx.get("bulb_w_incandescent")
    kind = _value(asset, "bulb_type")
    if kind == "led":
        w_low = w_high = w_led
    elif kind == "incandescent":
        w_low = w_high = w_inc
    else:  # unknown, or CFL (no sourced CFL wattage): between LED and incandescent
        w_low, w_high = w_led, w_inc
        if kind is None:
            assumed.append("bulb_type")
    hours = ctx.get("lighting_hours_per_day")
    kwh = _r(count * w_low * hours * 365 / 1000, count * w_high * hours * 365 / 1000)
    kind_text = kind or "unknown bulb type"
    return AssetEnergy(asset.id, asset.label, asset.room_id, True, kwh, _money(kwh, rate), kwh,
                       _r(count * w_low, count * w_high, 0),
                       f"{count} bulb(s), {kind_text}, {w_low:g}-{w_high:g} W each, {hours:g} h/day", assumed)


def _fridge(asset: Asset, ctx: AssumptionContext, rate: float) -> AssetEnergy:
    new, old = ctx.get("fridge_kwh_yr_new"), ctx.get("fridge_kwh_yr_old")
    age = _value(asset, "age_years")
    assumed = []
    if isinstance(age, (int, float)):
        low = high = new if age < 10 else old
    else:
        low, high = new, old
        assumed.append("age_years")
    kwh = _r(low, high)
    avg_w = _r(low * 1000 / HOURS_PER_YEAR, high * 1000 / HOURS_PER_YEAR, 0)
    return AssetEnergy(asset.id, asset.label, asset.room_id, True, kwh, _money(kwh, rate), kwh, avg_w,
                       f"{low:g}-{high:g} kWh/yr (new to older model); all of it ends up as heat in the room",
                       assumed, "power is the average over the day; the compressor cycles on and off")


def _window(asset: Asset, ctx: AssumptionContext, rate: float) -> AssetEnergy:
    area = _value(asset, "area_m2")
    if not isinstance(area, (int, float)) or area <= 0:
        return AssetEnergy(asset.id, asset.label, asset.room_id, False,
                           note="window size not visible, so its sun heat cannot be estimated",
                           assumed=["area_m2"])
    solar = ctx.get("window_solar_cooling_kwh_per_m2_yr")
    cop = ctx.get("eer_window_ac_old") / BTU_PER_WH
    cooling_kwh = area * solar
    heat = cooling_kwh * cop
    assumed = ["panes"] if _value(asset, "panes") is None else []
    return AssetEnergy(asset.id, asset.label, asset.room_id, True, _r(cooling_kwh, cooling_kwh),
                       _money(_r(cooling_kwh, cooling_kwh), rate), _r(heat, heat), None,
                       f"{area:g} m2 x {solar:g} kWh/m2/yr of cooling caused by sun through the glass "
                       f"(heat = cooling electricity x COP {cop:.2f})", assumed,
                       "single or double pane cannot be seen; the city average is used")


def _cooling(asset: Asset, ctx: AssumptionContext, rate: float, area_m2: float, n_units: int) -> AssetEnergy:
    unit_cooling = area_m2 * ctx.get("cooling_kwh_per_m2_yr")
    share = unit_cooling / max(n_units, 1)
    cop = ctx.get("eer_window_ac_old") / BTU_PER_WH
    kwh = _r(share, share)
    removed = -share * cop
    return AssetEnergy(asset.id, asset.label, asset.room_id, True, kwh, _money(kwh, rate), _r(removed, removed),
                       None, f"apartment cooling {area_m2:g} m2 x {ctx.get('cooling_kwh_per_m2_yr'):g} kWh/m2/yr, "
                       f"shared by {n_units} cooling unit(s); heat moved outside = electricity x COP {cop:.2f}",
                       note="negative heat: it removes heat from the apartment")


def inventory_energy(inventory: list[Asset], building: Building, ctx: AssumptionContext | None = None) -> list[AssetEnergy]:
    """Energy and heat for every asset, in inventory order."""
    ctx = ctx or AssumptionContext(building)
    rate = ctx.get("electricity_rate_usd_per_kwh")
    unit_area = building.unit_floor_area_m2.value
    area_m2 = float(unit_area) if isinstance(unit_area, (int, float)) and unit_area > 0 else ctx.get("default_unit_floor_area_m2")
    n_cooling = sum(1 for a in inventory if a.label in COOLING_UNITS)
    out: list[AssetEnergy] = []
    for asset in inventory:
        if asset.label in LIGHTS:
            out.append(_light(asset, ctx, rate))
        elif asset.label == "refrigerator":
            out.append(_fridge(asset, ctx, rate))
        elif asset.label == "window":
            out.append(_window(asset, ctx, rate))
        elif asset.label in COOLING_UNITS:
            out.append(_cooling(asset, ctx, rate, area_m2, n_cooling))
        else:
            out.append(AssetEnergy(asset.id, asset.label, asset.room_id, False,
                                   note=NOT_ESTIMATED.get(asset.label, "no sourced assumption yet")))
    return out


def _fmt(r: Optional[Range], unit: str, money: bool = False) -> str:
    if r is None:
        return "-"
    lo, hi = r
    if money:
        return f"${lo:,.0f}" if lo == hi else f"${lo:,.0f}-{hi:,.0f}"
    return f"{lo:,.0f} {unit}" if lo == hi else f"{lo:,.0f}-{hi:,.0f} {unit}"


def main(argv: list[str] | None = None) -> None:
    """Print the per-asset table for an audit folder: python -m wattwalk.engine.asset_energy --sid <sid>"""
    from wattwalk import store

    p = argparse.ArgumentParser(prog="python -m wattwalk.engine.asset_energy")
    p.add_argument("--sid", required=True)
    p.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = p.parse_args(argv)
    inventory = store.read(args.sid, "inventory.json", list[Asset])
    building = store.read(args.sid, "building.json", Building)
    if inventory is None or building is None:
        raise SystemExit(f"no finished audit for {args.sid} (inventory.json and building.json needed)")
    rows = inventory_energy(inventory, building)
    if args.json:
        print(json.dumps([r.to_dict() for r in rows], indent=2))
        return
    print(f"{'asset':10} {'label':14} {'energy/yr':>16} {'cost/yr':>10} {'heat/yr':>18} {'power':>10}  assumed")
    for r in rows:
        if not r.estimated:
            print(f"{r.asset_id:10} {r.label:14} {'not estimated: ' + r.note}")
            continue
        print(f"{r.asset_id:10} {r.label:14} {_fmt(r.kwh_yr, 'kWh'):>16} {_fmt(r.usd_yr, '', True):>10} "
              f"{_fmt(r.heat_kwh_yr, 'kWh'):>18} {_fmt(r.power_w, 'W'):>10}  {', '.join(r.assumed) or '-'}")
    est = [r for r in rows if r.estimated and r.kwh_yr]
    lo = sum(r.kwh_yr[0] for r in est)
    hi = sum(r.kwh_yr[1] for r in est)
    usd = (sum(r.usd_yr[0] for r in est), sum(r.usd_yr[1] for r in est))
    print(f"\n{len(est)} of {len(rows)} assets estimated: {lo:,.0f}-{hi:,.0f} kWh/yr, ${usd[0]:,.0f}-{usd[1]:,.0f}/yr")


if __name__ == "__main__":
    main()
