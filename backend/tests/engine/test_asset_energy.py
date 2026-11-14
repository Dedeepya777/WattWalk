"""Per-asset energy and heat: ranges that add up to the plan's baseline, with unknowns widening them."""
import json

import pytest

from wattwalk import config
from wattwalk.contracts import Asset, Attr, Building
from wattwalk.engine import AssumptionContext, baseline
from wattwalk.engine.asset_energy import inventory_energy


def _example(name):
    return json.loads((config.EXAMPLES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def building():
    return Building.model_validate(_example("building.json"))


@pytest.fixture
def inventory():
    return [Asset.model_validate(a) for a in _example("inventory.json")]


def _asset(aid, label, **attrs):
    return Asset(id=aid, label=label, room_id="r1", observation_ids=["o1"],
                 attrs={k: Attr(value=v, source="visible_in_scan" if v is not None else "needs_verification",
                                note="", evidence_obs_ids=["o1"]) for k, v in attrs.items()},
                 anchor=None, next_step="", disagreement=False)


def test_per_asset_numbers_add_up_to_the_plan_baseline(inventory, building):
    ctx = AssumptionContext(building)
    base = baseline(inventory, building, ctx)
    rows = {r.asset_id: r for r in inventory_energy(inventory, building)}
    lights_high = sum(r.kwh_yr[1] for r in rows.values() if r.label in ("ceiling_light", "lamp"))
    fridge_high = sum(r.kwh_yr[1] for r in rows.values() if r.label == "refrigerator")
    window_kwh = sum(r.kwh_yr[0] for r in rows.values() if r.label == "window" and r.estimated)
    assert lights_high == pytest.approx(base.lighting, abs=0.5)      # unknown bulbs count as incandescent there
    assert fridge_high == pytest.approx(base.fridge, abs=0.5)        # the plan assumes the older fridge
    assert window_kwh == pytest.approx(base.window_m2 * ctx.get("window_solar_cooling_kwh_per_m2_yr"), abs=0.5)
    cooling = [r for r in rows.values() if r.label in ("window_ac", "mini_split")]
    if cooling:
        assert sum(r.kwh_yr[0] for r in cooling) == pytest.approx(base.cooling, abs=0.5)


def test_light_ranges_follow_what_was_seen(building):
    rows = inventory_energy([_asset("a1", "lamp", bulb_type="led", bulb_count=2),
                             _asset("a2", "ceiling_light", bulb_type=None, bulb_count=1),
                             _asset("a3", "ceiling_light", bulb_type="incandescent", bulb_count=None)], building)
    led, unknown, inc = rows
    assert led.power_w == (18, 18) and led.assumed == []
    assert unknown.power_w == (9, 60) and unknown.assumed == ["bulb_type"]
    assert inc.power_w == (60, 60) and inc.assumed == ["bulb_count"]
    assert led.heat_kwh_yr == led.kwh_yr  # electricity used indoors ends up as heat
    assert led.kwh_yr == (pytest.approx(2 * 9 * 3 * 365 / 1000, abs=0.1),) * 2


def test_window_heat_is_sun_gain_and_ac_removes_heat(building):
    window, no_size, ac, washer = inventory_energy(
        [_asset("w", "window", area_m2=2.0, panes=None), _asset("w2", "window", area_m2=None),
         _asset("ac", "window_ac"), _asset("wa", "washer")], building)
    assert window.estimated and window.heat_kwh_yr[0] > window.kwh_yr[0] > 0  # heat = cooling electricity x COP
    assert window.assumed == ["panes"]
    assert not no_size.estimated and "size not visible" in no_size.note
    assert ac.heat_kwh_yr[0] < 0 and ac.kwh_yr[0] > 0
    assert not washer.estimated and washer.kwh_yr is None


def test_fridge_age_known_narrows_the_range(building):
    new, old, unknown = inventory_energy([_asset("f1", "refrigerator", age_years=3),
                                          _asset("f2", "refrigerator", age_years=15),
                                          _asset("f3", "refrigerator", age_years=None)], building)
    assert new.kwh_yr == (400, 400) and old.kwh_yr == (700, 700) and unknown.kwh_yr == (400, 700)
    assert unknown.power_w == (46, 80)


def test_alternatives_match_the_upgrade_library(building):
    rows = {r.asset_id: r for r in inventory_energy([
        _asset("inc", "lamp", bulb_type="incandescent", bulb_count=2),
        _asset("led", "lamp", bulb_type="led", bulb_count=1),
        _asset("unk", "ceiling_light", bulb_type=None, bulb_count=1),
        _asset("win", "window", area_m2=2.0),
        _asset("old", "refrigerator", age_years=15),
        _asset("new", "refrigerator", age_years=3),
        _asset("ac", "window_ac"),
        _asset("t", "thermostat"),
    ], building)}
    inc = rows["inc"].alternatives[0]
    assert inc["upgrade_id"] == "led" and inc["power_w"] == (18, 18)
    assert inc["saves_kwh_yr"][0] == pytest.approx(2 * (60 - 9) * 3 * 365 / 1000, abs=0.1)
    assert inc["cost_usd"] == (10, 16) and inc["payback_years"][0] < 1
    assert rows["led"].alternatives == []                        # already LED: nothing to offer
    assert rows["unk"].alternatives[0]["saves_kwh_yr"][0] == 0    # unknown bulb: may already be LED
    assert "best case" in rows["unk"].alternatives[0]["basis"]
    film = rows["win"].alternatives[0]
    assert film["upgrade_id"] == "window_film" and film["kwh_yr"][0] == pytest.approx(rows["win"].kwh_yr[0] * 0.7, abs=0.1)
    assert rows["old"].alternatives[0]["kwh_yr"] == (400, 400) and rows["new"].alternatives == []
    assert rows["ac"].alternatives[0]["kwh_yr"][0] == pytest.approx(rows["ac"].kwh_yr[0] / 2, abs=0.1)
    assert rows["t"].alternatives[0]["upgrade_id"] == "smart_thermostat" and rows["t"].alternatives[0]["kwh_yr"] is None
