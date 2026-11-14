"""Health registry and GET /health (fix plan P3-4). Run: pytest backend/tests/api/test_health.py"""
from __future__ import annotations

import time

import pytest

from wattwalk import config, health_registry

from .conftest import client, env  # noqa: F401  (pytest fixtures)


# ----------------------------------------------------------------------------- registry
def test_registry_statuses(env, monkeypatch):
    assert health_registry.status("matterport", configured=True, mode_is_fixture=False) == "unavailable"  # never tested
    assert health_registry.status("matterport", configured=True, mode_is_fixture=True) == "fixture"
    health_registry.record("matterport", True, "ok")
    assert health_registry.status("matterport", configured=True, mode_is_fixture=False) == "live"
    assert health_registry.status("matterport", configured=False, mode_is_fixture=False) == "unavailable"
    health_registry.record("matterport", False, "HTTP 401")
    assert health_registry.status("matterport", configured=True, mode_is_fixture=False) == "unavailable"
    health_registry.record("vexcel", True)
    later = time.time() + 601
    monkeypatch.setattr(health_registry.time, "time", lambda: later)
    assert health_registry.status("vexcel", configured=True, mode_is_fixture=False) == "unavailable"  # stale
    with pytest.raises(ValueError):
        health_registry.record("bogus", True)


# ----------------------------------------------------------------------------- endpoint
def _go_live(monkeypatch):
    monkeypatch.setattr(config, "DATA_MODE", "live")
    monkeypatch.setattr(config, "VISION_MODE", "live")
    for name, value in [("MATTERPORT_API_KEY", "k"), ("MATTERPORT_API_TOKEN", "t"), ("VEXCEL_API_KEY", "v"),
                        ("COSTAR_KIT_ZIP", "kit.zip"), ("SMALL_VISION_MODEL_ID", "small"), ("LARGE_VISION_MODEL_ID", "large")]:
        monkeypatch.setattr(config, name, value)


def test_plain_get_never_calls_probes(client, monkeypatch):
    from wattwalk.api import app as app_mod

    _go_live(monkeypatch)
    monkeypatch.setattr(app_mod, "_probe_fn", lambda name: pytest.fail("plain GET /health must not probe"))
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert set(body["integrations"].values()) == {"unavailable"}  # configured but never tested


def test_probe_returns_probe_results(client, monkeypatch):
    from wattwalk.api import app as app_mod

    _go_live(monkeypatch)
    outcome = {"matterport": True, "vexcel": False, "costar_kit": True, "ebewe": True}
    called = []

    def fake_probe_fn(name):
        if name == "bedrock":
            return None  # vision probe not merged yet
        if name == "ebewe":
            def crash():
                called.append(name)
                raise RuntimeError("socket closed")
            return crash

        def probe():
            called.append(name)
            health_registry.record(name, outcome[name], "fake")
        return probe

    monkeypatch.setattr(app_mod, "_probe_fn", fake_probe_fn)
    body = client.get("/health", params={"probe": 1}).json()
    assert sorted(called) == ["costar_kit", "ebewe", "matterport", "vexcel"]
    assert body["integrations"] == {"matterport": "live", "vexcel": "unavailable", "costar_kit": "live",
                                    "ebewe": "unavailable", "bedrock": "unavailable"}
    assert body["status"] == "degraded"
    # the registry keeps the result for later plain GETs
    assert client.get("/health").json()["integrations"]["matterport"] == "live"


def test_probe_skips_fixture_and_unconfigured(client, monkeypatch):
    from wattwalk.api import app as app_mod

    monkeypatch.setattr(config, "DATA_MODE", "fixture")
    monkeypatch.setattr(config, "VISION_MODE", "live")
    monkeypatch.setattr(config, "SMALL_VISION_MODEL_ID", "")
    monkeypatch.setattr(config, "LARGE_VISION_MODEL_ID", "")
    monkeypatch.setattr(app_mod, "_probe_fn", lambda name: pytest.fail(f"{name} must not be probed"))
    body = client.get("/health", params={"probe": "1"}).json()
    assert body["integrations"] == {"matterport": "fixture", "vexcel": "fixture", "costar_kit": "fixture",
                                    "ebewe": "fixture", "bedrock": "unavailable"}


def test_probe_timeout_counts_as_failure(client, monkeypatch):
    import threading

    from wattwalk.api import app as app_mod

    _go_live(monkeypatch)
    monkeypatch.setattr(app_mod, "PROBE_TIMEOUT_S", 0.2)
    release = threading.Event()
    monkeypatch.setattr(app_mod, "_probe_fn", lambda name: (lambda: release.wait(5)) if name == "matterport" else None)
    try:
        body = client.get("/health", params={"probe": 1}).json()
    finally:
        release.set()
    assert body["integrations"]["matterport"] == "unavailable"
    assert "timed out" in health_registry.last("matterport")[1]
