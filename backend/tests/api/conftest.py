"""Shared fixtures for Person 3's API and agent tests."""
from __future__ import annotations

import contextlib
import json
import socket
import threading
import time

import httpx
import pytest

from wattwalk import config

SID = config.FIXTURE_SID


@pytest.fixture
def env(tmp_path, monkeypatch):
    audits = tmp_path / "audits"
    monkeypatch.setattr(config, "AUDITS_DIR", audits)
    monkeypatch.setattr(config, "CACHE_DIR", audits / "cache")
    monkeypatch.setattr(config, "DEMO_DIR", tmp_path / "demo")
    monkeypatch.setitem(config.TIMEOUTS_S, "ask_user", 0.3)
    # Independent of the developer's local .env (which may be in live mode).
    monkeypatch.setattr(config, "DATA_MODE", "fixture")
    monkeypatch.setattr(config, "VISION_MODE", "fixture")
    monkeypatch.setattr(config, "AGENT_MODE", "scripted")
    from wattwalk import health_registry
    health_registry.clear()
    return tmp_path


@contextlib.contextmanager
def live_server(app):
    """Serve the app with real uvicorn in a background thread on a free local port.

    Starlette's TestClient does not stream responses in older versions (it runs the app to completion
    before returning, e.g. Starlette 0.36 used by fastapi 0.110), so SSE events emitted while a run
    waits on a question never reached the test. A real server streams on every version.
    """
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    t0 = time.monotonic()
    while not server.started:
        if not thread.is_alive() or time.monotonic() - t0 > 10:
            raise RuntimeError("test server did not start")
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def client(env):
    from wattwalk.api.app import app

    with live_server(app) as base_url, httpx.Client(base_url=base_url, timeout=30.0) as c:
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
