"""Test index loading, lookup, and city normalization (P1-4).

Owner: Person 1.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from wattwalk import config
from wattwalk.data import index
from wattwalk.data.index import IndexRow, load_index, lookup, same_building


def test_load_index_and_lookup() -> None:
    idx = load_index()
    assert len(idx) > 14000

    r1 = lookup("r1NfhYW4TAr")
    assert r1 is not None
    assert "Los Angeles" in r1.city
    assert "7th" in r1.address

    h7 = lookup("H7CHGZ8m3Dg")
    assert h7 is not None
    assert "Los Angeles" in h7.city
    assert "Francisco" in h7.address

    hero = lookup("fixtureUnitA")
    assert hero is not None
    assert isinstance(hero, IndexRow)
    assert hero.sid == "fixtureUnitA"
    assert hero.city == "Los Angeles"
    assert hero.costar_property_id == "illustrative-0001"

    matches = same_building("illustrative-0001")
    assert len(matches) == 1
    assert matches[0].sid == "fixtureUnitA"


def test_sample_index_fallback(tmp_path, monkeypatch, caplog):
    sample_file = tmp_path / "models_index.sample.csv"
    sample_file.write_text(
        'sid,name,segment,lat,lon,address,city,costar_property_id,homes_listing_id,pano_count,room_count,splat\n'
        'fixtureUnitA,Fixture Unit A,residential,,,"100 Example St, Los Angeles, CA",Los Angeles,illustrative-0001,,7,6,False\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "FIXTURES_DIR", tmp_path)
    monkeypatch.setattr(index, "_INDEX_CACHE", {})

    with caplog.at_level(logging.INFO):
        idx = index.load_index()
    assert "sample index" in caplog.text
    assert "fixtureUnitA" in idx
    assert idx["fixtureUnitA"].city == "Los Angeles"


def test_lookup_unknown_sid() -> None:
    assert lookup("nonexistent_sid_12345") is None
