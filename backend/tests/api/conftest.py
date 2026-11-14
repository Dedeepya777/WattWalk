"""Shared fixtures for Person 3's API and agent tests."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from wattwalk import config

SID = config.FIXTURE_SID


@pytest.fixture
def env(tmp_path, monkeypatch):
    audits = tmp_path / "audits"
    monkeypatch.setattr(config, "AUDITS_DIR", audits)
    monkeypatch.setattr(config, "CACHE_DIR", audits / "cache")
    monkeypatch.setattr(config, "DEMO_DIR", tmp_path / "demo")
    monkeypatch.setitem(config.TIMEOUTS_S, "ask_user", 0.3)
    return tmp_path


@pytest.fixture
def client(env):
    from wattwalk.api.app import app

    with TestClient(app) as c:
        yield c


def example(name: str):
    return json.loads((config.EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def read_events(client, sid=SID, from_seq=0, until=None, timeout=20.0):
    """Read SSE events until done (or until `until(event)` is true)."""
    out = []
    t0 = time.monotonic()
    with client.stream("GET", f"/audits/{sid}/events", params={"from_seq": from_seq}) as s:
        assert s.status_code == 200
        assert s.headers["content-type"].startswith("text/event-stream")
        for line in s.iter_lines():
            if time.monotonic() - t0 > timeout:
                raise AssertionError("timed out reading events")
            if not line.startswith("data:"):
                continue
            ev = json.loads(line[5:])
            out.append(ev)
            if ev["type"] == "done" or (until and until(ev)):
                break
    return out


def run_fixture(client, sid=SID):
    r = client.post(f"/audits/{sid}", json={"mode": "fixture"})
    assert r.status_code == 202, r.text
    return read_events(client, sid)


def wait_status(client, sid, wanted, timeout=5.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = client.get(f"/audits/{sid}").json()["status"]
        if st["status"] == wanted:
            return st, time.monotonic() - t0
        time.sleep(0.02)
    raise AssertionError(f"status never became {wanted}")
