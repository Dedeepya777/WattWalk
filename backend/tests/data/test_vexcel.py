"""Tests for Vexcel adapter and building roof integration (P1-1, P1-2, P1-3)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from wattwalk import config, store
from wattwalk.contracts import ModelGeometry
from wattwalk.data import building, vexcel
from wattwalk.errors import UpstreamError


@pytest.fixture(autouse=True)
def set_live_mode(monkeypatch):
    monkeypatch.setattr(config, "effective_data_mode", lambda: "live")
    monkeypatch.setattr(config, "VEXCEL_API_KEY", "test-vexcel-key")


def test_vexcel_ortho_request_body_and_polygon(tmp_path, monkeypatch):
    """The posted JSON has exactly the 7 keys; polygon is closed and contains (lon, lat)."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    lat, lon = 34.0522, -118.2437

    captured = {}

    def mock_post(url, headers=None, json=None, timeout=None):
        captured["headers"] = headers
        captured["json"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "image/jpeg"}
        resp.content = b"\xff\xd8\xff\xe0" + b"0" * 600
        return resp

    monkeypatch.setattr(requests, "post", mock_post)

    out = vexcel.ortho("test_sid", lat, lon, half_width_m=70.0)
    assert out is not None
    assert out.exists()

    body = captured["json"]
    assert set(body.keys()) == {
        "wkt",
        "srid",
        "layer",
        "crop",
        "image-format",
        "destination-dimensions",
        "attribution",
    }
    assert body["srid"] == 4326
    assert body["layer"] == "urban,urban-r,wide-area,urban-g"
    assert body["crop"] == "bounding_box"
    assert body["image-format"] == "jpeg"
    assert body["destination-dimensions"] == "1400,1400"
    assert body["attribution"] == "false"

    # Validate WKT polygon
    wkt = body["wkt"]
    assert wkt.startswith("POLYGON((") and wkt.endswith("))")
    coords_str = wkt[len("POLYGON(("):-2]
    pts = [list(map(float, p.strip().split())) for p in coords_str.split(",")]
    assert len(pts) == 5
    assert pts[0] == pts[-1]  # Closed polygon

    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    assert min(lons) < lon < max(lons)
    assert min(lats) < lat < max(lats)


def test_vexcel_403_raises_upstream_auth(tmp_path, monkeypatch):
    """A JSON error response with 403 raises UpstreamError with code upstream_auth."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")

    def mock_post(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = 403
        resp.headers = {"Content-Type": "application/json"}
        resp.json.return_value = {"message": "Forbidden access outside authorized bounds"}
        resp.text = json.dumps(resp.json.return_value)
        return resp

    monkeypatch.setattr(requests, "post", mock_post)

    with pytest.raises(UpstreamError) as exc_info:
        vexcel.ortho("test_sid", 30.0, -95.0)

    err = exc_info.value
    assert err.code == "upstream_auth"
    assert err.http_status == 403
    assert "Houston and Los Angeles" in str(err)


def test_vexcel_cache_avoids_repeated_post(tmp_path, monkeypatch):
    """A JPEG response is written to the cache path; a second call does not call requests.post."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    call_count = [0]

    def mock_post(*args, **kwargs):
        call_count[0] += 1
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "image/jpeg"}
        resp.content = b"fake-jpeg-bytes"
        return resp

    monkeypatch.setattr(requests, "post", mock_post)

    p1 = vexcel.ortho("test_sid", 34.0, -118.0)
    assert call_count[0] == 1
    assert p1.exists()

    p2 = vexcel.ortho("test_sid", 34.0, -118.0)
    assert call_count[0] == 1  # Not called again
    assert p1 == p2


def test_building_copies_ortho_to_audit_folder(tmp_path, monkeypatch):
    """With vexcel.ortho returning a temp JPEG: get_building returns roof.ortho_ref == 'vexcel/ortho.jpg'."""
    monkeypatch.setattr(config, "AUDITS_DIR", tmp_path / "audits")
    fake_cache = tmp_path / "cached_ortho.jpg"
    fake_cache.write_bytes(b"image data")

    monkeypatch.setattr(vexcel, "ortho", lambda *a, **kw: fake_cache)
    monkeypatch.setattr(vexcel, "roof_attributes", lambda *a, **kw: {"pitch": "flat"})

    geom = ModelGeometry(
        sid="test_sid",
        address="123 Test St, Los Angeles, CA",
        lat=34.05,
        lon=-118.25,
        rooms=[],
        panos=[],
        walls=[],
        status="live",
    )

    bld = building.get_building("test_sid", geom)
    assert bld.roof.status == "live"
    assert bld.roof.ortho_ref == "vexcel/ortho.jpg"
    assert bld.roof.attributes == {"pitch": "flat"}

    copied = store.audit_path("test_sid", "vexcel", "ortho.jpg")
    assert copied.exists()
    assert copied.read_bytes() == b"image data"


def test_building_ortho_failure_leaves_unavailable(tmp_path, monkeypatch):
    """With ortho raising: ortho_ref is None, status unavailable, other layers unaffected."""
    monkeypatch.setattr(config, "AUDITS_DIR", tmp_path / "audits")

    def mock_ortho(*a, **kw):
        raise UpstreamError("vexcel", False, "failed", 500)

    monkeypatch.setattr(vexcel, "ortho", mock_ortho)
    monkeypatch.setattr(vexcel, "roof_attributes", lambda *a, **kw: None)

    geom = ModelGeometry(
        sid="test_sid",
        address="123 Test St, Los Angeles, CA",
        lat=34.05,
        lon=-118.25,
        rooms=[],
        panos=[],
        walls=[],
        status="live",
    )

    bld = building.get_building("test_sid", geom)
    assert bld.roof.status == "unavailable"
    assert bld.roof.ortho_ref is None
    assert bld.roof.attributes == {}
    assert bld.layer_status.vexcel == "unavailable"
