"""AI alternatives: the model only suggests ideas; savings and payback come from the energy engine."""
import json

import pytest

from wattwalk import config
from wattwalk.contracts import Asset, Building
from wattwalk.engine import ai_alternatives as ai
from wattwalk.engine.asset_energy import inventory_energy

SID = "testsid01"


def _example(name):
    return json.loads((config.EXAMPLES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def building():
    return Building.model_validate(_example("building.json"))


@pytest.fixture
def inventory():
    return [Asset.model_validate(a) for a in _example("inventory.json")]


@pytest.fixture(autouse=True)
def audits(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUDITS_DIR", tmp_path / "audits")
    (tmp_path / "audits" / SID).mkdir(parents=True)


def _fake(reply, calls=None):
    def ask(prompt):
        if calls is not None:
            calls.append(prompt)
        return json.dumps(reply)
    return ask


IDEAS = {"today_kwh_yr": None, "ideas": [
    {"title": "Thermal blackout curtains", "why": "Block afternoon sun", "kwh_cut_pct": [10, 20],
     "cost_usd": [60, 150], "who": "tenant"},
    {"title": "Exterior shade screen", "why": "Stops heat outside the glass", "kwh_cut_pct": [200, 30],
     "cost_usd": [-5, 400], "who": "owner"},
    {"title": "", "kwh_cut_pct": [5, 10], "cost_usd": [1, 2]},           # no title: dropped
    {"title": "Thermal blackout curtains", "kwh_cut_pct": [1, 2], "cost_usd": [1, 2]},  # duplicate
]}


def _estimated(inventory, building, label):
    rows = inventory_energy(inventory, building)
    return next((a, r) for a, r in zip(inventory, rows) if a.label == label and r.estimated and r.kwh_yr)


def test_savings_are_computed_from_the_assets_energy(inventory, building):
    asset, row = _estimated(inventory, building, "window")
    out = ai.research(SID, asset.id, inventory, building, ask=_fake(IDEAS))
    assert [a.title for a in out.alternatives] == ["Thermal blackout curtains", "Exterior shade screen"]
    first, second = out.alternatives
    assert first.saves_kwh_yr == (round(row.kwh_yr[0] * 0.10, 1), round(row.kwh_yr[1] * 0.20, 1))
    assert first.upgrade_id.startswith("ai:") and "AI estimate" in first.basis
    for alt in out.alternatives:  # every range is (low, high)
        for r in (alt.kwh_yr, alt.usd_yr, alt.heat_kwh_yr, alt.saves_kwh_yr, alt.cost_usd, alt.payback_years):
            assert r is None or r[0] <= r[1]
    assert first.kwh_yr == (round(row.kwh_yr[0] * 0.80, 1), round(row.kwh_yr[1] * 0.90, 1))
    assert first.who == "the tenant can do it"
    # out-of-range numbers from the model are clamped and ordered
    assert second.cost_usd == (0, 400)
    assert "30-95%" in second.basis
    assert out.today_kwh_yr is None and out.cached is False


def test_the_answer_is_saved_and_reused(inventory, building):
    asset, _ = _estimated(inventory, building, "window")
    calls = []
    ai.research(SID, asset.id, inventory, building, ask=_fake(IDEAS, calls))
    again = ai.research(SID, asset.id, inventory, building, ask=_fake(IDEAS, calls))
    assert len(calls) == 1 and again.cached is True
    ai.research(SID, asset.id, inventory, building, ask=_fake(IDEAS, calls), refresh=True)
    assert len(calls) == 2


def test_an_item_without_an_estimate_uses_the_models_estimate_of_today(inventory, building):
    rows = inventory_energy(inventory, building)
    asset = next((a for a, r in zip(inventory, rows) if not r.estimated), None)
    if asset is None:
        pytest.skip("example inventory has no unestimated asset")
    reply = {"today_kwh_yr": [100, 200], "ideas": [
        {"title": "ENERGY STAR model", "kwh_cut_pct": [20, 40], "cost_usd": [300, 600], "who": "owner"}]}
    out = ai.research(SID, asset.id, inventory, building, ask=_fake(reply))
    assert out.today_kwh_yr == (100.0, 200.0)
    assert out.alternatives[0].saves_kwh_yr == (20.0, 80.0)


def test_unusable_answers_fail_clearly(inventory, building):
    asset, _ = _estimated(inventory, building, "window")
    with pytest.raises(ai.ResearchFailed):
        ai.research(SID, asset.id, inventory, building, ask=lambda p: "not json")
    with pytest.raises(ai.ResearchFailed):
        ai.research(SID, asset.id, inventory, building, ask=_fake({"ideas": []}))


def test_no_key_means_unavailable(inventory, building, monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    asset, _ = _estimated(inventory, building, "window")
    with pytest.raises(ai.ResearchUnavailable):
        ai.research(SID, asset.id, inventory, building)


def test_an_item_with_no_electricity_gets_a_note_not_an_error(inventory, building):
    rows = inventory_energy(inventory, building)
    asset = next((a for a, r in zip(inventory, rows) if not r.estimated), None)
    if asset is None:
        pytest.skip("example inventory has no unestimated asset")
    out = ai.research(SID, asset.id, inventory, building, ask=_fake({"today_kwh_yr": None, "ideas": []}))
    assert out.alternatives == [] and "does not use electricity" in out.note


def test_products_get_safe_amazon_links(inventory, building):
    from urllib.parse import parse_qs, urlparse

    asset, _ = _estimated(inventory, building, "window")
    reply = {"ideas": [{
        "title": "Insulated cellular shades", "why": "", "kwh_cut_pct": [10, 20], "cost_usd": [60, 150],
        "who": "tenant",
        "products": [
            {"name": "Bali Cordless Light-Filtering Cellular Shade 36 in", "approx_price_usd": 45, "why": "Cordless"},
            {"name": "https://evil.example/fake", "approx_price_usd": 1},      # a URL instead of a name: dropped
            {"name": "bali cordless light-filtering cellular shade 36 in"},    # duplicate: dropped
            {"name": "Chicology Cordless Blackout Cellular Shade", "approx_price_usd": -5},
            {"name": "Redi Shade Easy Lift Cellular Shade"},
            {"name": "One too many shade"},                                      # over the limit: dropped
        ],
    }]}
    out = ai.research(SID, asset.id, inventory, building, ask=_fake(reply))
    products = out.alternatives[0].products
    assert [p.name for p in products] == [
        "Bali Cordless Light-Filtering Cellular Shade 36 in",
        "Chicology Cordless Blackout Cellular Shade",
        "Redi Shade Easy Lift Cellular Shade",
    ]
    assert products[0].approx_price_usd == 45 and products[1].approx_price_usd is None
    query = parse_qs(urlparse(products[0].url).query)["q"][0]
    assert products[0].url.startswith("https://duckduckgo.com/?q=")
    assert query == "\\ site:amazon.com Bali Cordless Light-Filtering Cellular Shade 36 in"


def test_answers_saved_before_products_are_asked_again(inventory, building):
    asset, _ = _estimated(inventory, building, "window")
    calls = []
    ai.research(SID, asset.id, inventory, building, ask=_fake(IDEAS, calls))
    path = config.AUDITS_DIR / SID / ai.CACHE_FILE
    cache = json.loads(path.read_text())
    for alt in cache[asset.id]["alternatives"]:
        alt.pop("products")
    path.write_text(json.dumps(cache))
    ai.research(SID, asset.id, inventory, building, ask=_fake(IDEAS, calls))
    assert len(calls) == 2
