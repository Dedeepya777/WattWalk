"""Test index loading, lookup, and city normalization.

Owner: Person 1.
"""
from __future__ import annotations

import pytest
from wattwalk.data.index import IndexRow, load_index, lookup, same_building


def test_load_index_and_lookup() -> None:
    idx = load_index()
    assert len(idx) >= 5

    hero = lookup("fixtureUnitA")
    assert hero is not None
    assert isinstance(hero, IndexRow)
    assert hero.sid == "fixtureUnitA"
    assert hero.city == "Los Angeles"
    assert hero.costar_property_id == "illustrative-0001"

    matches = same_building("illustrative-0001")
    assert len(matches) == 1
    assert matches[0].sid == "fixtureUnitA"


def test_lookup_unknown_sid() -> None:
    assert lookup("nonexistent_sid_12345") is None
