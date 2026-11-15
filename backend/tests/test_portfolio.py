"""Landlord buildings: forgiving address search (Los Angeles) and the saved list of buildings."""
import pytest

from wattwalk import config
from wattwalk import portfolio as p


@pytest.fixture(autouse=True)
def audits(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUDITS_DIR", tmp_path / "audits")


@pytest.mark.parametrize("text, expected", [
    ("1830 north cherokee avenue", "1830 N CHEROKEE AVE"),
    ("215 West 7th Street, Unit 301, Los Angeles", "215 W 7TH ST"),
    ("889 Francisco St #1206", "889 FRANCISCO ST"),
    ("819  santee st.", "819 SANTEE ST"),
])
def test_addresses_are_normalized(text, expected):
    assert p.normalize_street(text) == expected


def test_search_finds_a_building_and_its_units():
    found = p.search("1830 north cherokee avenue").buildings
    assert found[0].address == "1830 N Cherokee Ave, Los Angeles, CA"
    assert "2ibibwUGQAe" in {t.sid for t in found[0].tours}
    assert len(found[0].tours) >= 2


def test_search_is_los_angeles_only_and_handles_misses():
    assert p.search("181 Thatcher Rd").buildings == []
    assert p.search("ab").buildings == []
    assert all(b.city == "Los Angeles" for b in p.search("main").buildings)


def test_add_update_and_remove_a_building():
    bid = p.search("1830 N Cherokee Ave").buildings[0].building_id
    tours = [t.sid for t in p.search("1830 N Cherokee Ave").buildings[0].tours]
    first = p.add_building(bid, tours[:2])
    assert [b.sids for b in first.buildings] == [tours[:2]]
    again = p.add_building(bid, tours[:3])
    assert len(again.buildings) == 1 and again.buildings[0].sids == tours[:3]
    assert again.buildings[0].added_at == first.buildings[0].added_at
    assert p.load() == again  # saved
    with pytest.raises(ValueError):
        p.add_building(bid, ["notAUnitHere"])
    with pytest.raises(KeyError):
        p.add_building("no-such-building", tours[:1])
    assert p.remove_building(bid).buildings == []


def test_units_become_apartments_once():
    match = p.search("819 Santee St").buildings[0]
    p.add_building(match.building_id, [t.sid for t in match.tours[:2]])
    models = p.portfolio_models({"wYFF3KYdETV"})
    sids = [m.sid for m in models]
    assert "wYFF3KYdETV" not in sids  # already in the configured list
    assert all(m.address.startswith("819 Santee St, ") and m.note.startswith("Your building") for m in models)


def test_units_in_a_building_are_named():
    match = p.search("1830 N Cherokee Ave").buildings[0]
    p.add_building(match.building_id, [t.sid for t in match.tours])
    names = p.unit_addresses()
    unit = next(t for t in match.tours if t.sid == "2ibibwUGQAe")
    assert names["2ibibwUGQAe"] == f"1830 N Cherokee Ave, {unit.name}, Los Angeles, CA"
