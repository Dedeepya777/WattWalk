"""CoStar kit join by Matterport model id. Uses a tiny synthetic kit (the real kit is licensed and never committed)."""
from __future__ import annotations

import json
import zipfile

import pytest

from wattwalk import config
from wattwalk.data import costar


def _write_kit(root):
    (root / "data").mkdir(parents=True)
    (root / "commercial-properties.csv").write_text(
        "PropertyId,MatterportModelId,Address,City,State\n6176169,cherokeeSid,1830 N Cherokee Ave,Los Angeles,CA\n")
    (root / "residential-listings.csv").write_text(
        "ListingId,ResidentialListingId,MatterportModelId,Address,City,State\n"
        "240475490,223415102,seventhSid,215 W 7th Street Unit 301,Los Angeles,CA\n"
        "111,222,rentalSid,1 Rental St,Los Angeles,CA\n")
    props = [{"id": 1, "propertyType": 5},
             {"id": 6176169, "propertyType": 11, "propertyApartment": {"totalNumUnits": 39},
              "constructionEvents": [{"eventType": 4, "year": 1990}, {"eventType": 2, "year": 1926}]}]
    (root / "data" / "commercial-property.jsonl").write_text("\n".join(json.dumps(p, separators=(",", ":")) for p in props))
    (root / "data" / "apartment-listing.jsonl").write_text(json.dumps(
        {"id": 9, "propertyId": 6176169, "yearBuilt": 1930, "minRent": 1799, "maxRent": 2350}, separators=(",", ":")))
    listings = [{"id": 240475490, "propertyId": 100010002523, "transactionType": 1, "currentPrice": 350000.0,
                 "property": {"yearBuilt": 1911, "unitsCount": 130, "propertyType": 4}},
                {"id": 111, "transactionType": 2, "currentPrice": 2400.0,
                 "property": {"yearBuilt": 1960, "propertyType": 1}}]
    (root / "data" / "residential-listings.jsonl").write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in listings))


@pytest.fixture
def kit(tmp_path, monkeypatch):
    _write_kit(tmp_path / "kit")
    monkeypatch.setattr(config, "DATA_MODE", "live")
    monkeypatch.setattr(config, "COSTAR_KIT_ZIP", str(tmp_path / "kit"))
    costar._SID_CACHE.clear()
    yield tmp_path / "kit"
    costar._SID_CACHE.clear()


def test_residential_for_sale(kit):
    r = costar.record_for_sid("seventhSid")
    assert (r["year_built"], r["units"], r["property_type"], r["costar_property_id"]) == (1911, 130, "Condo", "100010002523")
    assert r["list_price_usd"] == 350000.0 and "asking_rent_usd_month" not in r  # a sale price is not a rent


def test_residential_rental_price_is_rent(kit):
    r = costar.record_for_sid("rentalSid")
    assert r["asking_rent_usd_month"] == 2400.0 and r["property_type"] == "Detached house"


def test_commercial_with_apartment_listing(kit):
    r = costar.record_for_sid("cherokeeSid")
    assert (r["year_built"], r["units"], r["property_type"], r["costar_property_id"]) == (1926, 39, "Multifamily", "6176169")
    assert r["asking_rent_usd_month"] == 2074.5 and "$1,799 to $2,350" in r["notes"]["asking_rent_usd_month"]


def test_unknown_sid_and_fixture_mode(kit, monkeypatch):
    assert costar.record_for_sid("noSuchSid") is None
    costar._SID_CACHE.clear()
    monkeypatch.setattr(config, "DATA_MODE", "fixture")
    assert costar.record_for_sid("seventhSid") is None


def test_zip_kit(kit, tmp_path, monkeypatch):
    archive = tmp_path / "kit.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in kit.rglob("*"):
            if path.is_file():
                zf.write(path, "costar-hackathon-kit/" + str(path.relative_to(kit)))
    monkeypatch.setattr(config, "COSTAR_KIT_ZIP", str(archive))
    costar._SID_CACHE.clear()
    assert costar.record_for_sid("seventhSid")["year_built"] == 1911
