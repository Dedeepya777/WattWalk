"""Test LA EBEWE address normalization and Socrata live lookup.

Owner: Person 1.
See plan/plan.md section 13.3, 15.3, acceptance criteria G item 7.
"""
from __future__ import annotations

import pytest
from wattwalk.data.ebewe import lookup, normalize_address


def test_normalize_address() -> None:
    assert normalize_address("5600 Wilshire Blvd, Los Angeles, CA 90036") == "5600 WILSHIRE BLVD"
    assert normalize_address("1420 S. Figueroa Street, Apt 4B") == "1420 S FIGUEROA ST"
    assert normalize_address("870 Hilgard Avenue, Unit #12") == "870 HILGARD AVE"
    assert normalize_address("1830 N Cherokee Ave") == "1830 N CHEROKEE AVE"


def test_ebewe_lookup_hero_address() -> None:
    rec = lookup("5600 Wilshire Blvd", city="Los Angeles")
    assert rec is not None
    assert rec.year_built == 2008
    assert rec.site_eui_kbtu_ft2 > 20.0
    assert rec.program_year >= 2024
    assert rec.property_type == "Multifamily Housing"


def test_ebewe_lookup_four_test_buildings() -> None:
    """Acceptance criterion 7: EBEWE lookup for the four test addresses returns records."""
    addresses = [
        "5600 Wilshire Blvd",
        "1420 S Figueroa St",
        "870 Hilgard Ave",
        "1830 N Cherokee Ave",
    ]
    for addr in addresses:
        rec = lookup(addr, city="Los Angeles")
        assert rec is not None, f"Expected EBEWE record for {addr}"
        assert rec.site_eui_kbtu_ft2 > 0.0


def test_ebewe_lookup_houston_skipped() -> None:
    rec = lookup("1000 Main St", city="Houston")
    assert rec is None
