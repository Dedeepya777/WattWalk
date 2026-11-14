"""Tests for health probes and adapter health recording (P1-6)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from wattwalk import config
from wattwalk.data import probes


@pytest.fixture(autouse=True)
def live_mode(monkeypatch):
    monkeypatch.setattr(config, "RUN_MODE_OVERRIDE", MagicMock(get=lambda: "live"))
    monkeypatch.setattr(config, "MATTERPORT_API_KEY", "dummy_key")
    monkeypatch.setattr(config, "MATTERPORT_API_TOKEN", "dummy_token")
    monkeypatch.setattr(config, "VEXCEL_API_KEY", "dummy_vexcel_key")


def test_probe_matterport_success_and_failure(monkeypatch):
    recorded = []
    fake_registry = MagicMock(record=lambda integration, ok, detail="": recorded.append((integration, ok, detail)))
    monkeypatch.setattr("wattwalk.health_registry", fake_registry, raising=False)

    # 1. Success
    resp_ok = MagicMock(status_code=200)
    monkeypatch.setattr(requests, "post", lambda *a, **kw: resp_ok)
    ok, detail = probes.probe_matterport()
    assert ok is True
    assert detail == "200"

    # 2. HTTP 401
    resp_401 = MagicMock(status_code=401)
    monkeypatch.setattr(requests, "post", lambda *a, **kw: resp_401)
    ok, detail = probes.probe_matterport()
    assert ok is False
    assert detail == "401"

    # 3. Exception never raises
    monkeypatch.setattr(requests, "post", MagicMock(side_effect=requests.exceptions.ConnectTimeout("timeout")))
    ok, detail = probes.probe_matterport()
    assert ok is False
    assert "ConnectTimeout" in detail


def test_probe_ebewe_success_and_failure(monkeypatch):
    resp_ok = MagicMock(status_code=200)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: resp_ok)
    ok, detail = probes.probe_ebewe()
    assert ok is True
    assert detail == "200"

    resp_500 = MagicMock(status_code=500)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: resp_500)
    ok, detail = probes.probe_ebewe()
    assert ok is False
    assert detail == "500"


def test_probe_costar_kit(tmp_path, monkeypatch):
    # Missing path
    monkeypatch.setattr(config, "COSTAR_KIT_ZIP", "")
    ok, detail = probes.probe_costar_kit()
    assert ok is False
    assert "not configured" in detail

    # Valid folder
    fake_dir = tmp_path / "costar_dir"
    fake_dir.mkdir()
    (fake_dir / "sample.csv").write_text("a,b\n1,2", encoding="utf-8")
    monkeypatch.setattr(config, "COSTAR_KIT_ZIP", str(fake_dir))
    ok, detail = probes.probe_costar_kit()
    assert ok is True
    assert "folder" in detail


def test_probe_vexcel(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")

    resp_ok = MagicMock(status_code=200, headers={"Content-Type": "image/jpeg"}, content=b"ortho")
    monkeypatch.setattr(requests, "post", lambda *a, **kw: resp_ok)
    ok, detail = probes.probe_vexcel()
    assert ok is True
    assert detail == "200"

    # Cached on second run
    ok2, detail2 = probes.probe_vexcel()
    assert ok2 is True
    assert detail2 == "cached"
