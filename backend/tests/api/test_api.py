"""Person 3 API tests (plan Appendix B, 15.5). Run: pytest backend/tests/api"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

from wattwalk import config

from .conftest import SID, example, read_events, run_fixture, wait_status

PLAN_SCENARIOS = ["owner_5000_max_bill", "owner_2000_max_bill", "tenant_2000_max_bill",
                  "owner_5000_conservative", "owner_0_boundary", "tenant_2000_stay1_boundary"]


def _hold_on_question(monkeypatch, seconds=30):
    monkeypatch.setitem(config.TIMEOUTS_S, "ask_user", seconds)


def test_check_contracts():
    r = subprocess.run([sys.executable, "scripts/check_contracts.py"], cwd=config.REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_api_fixture_audit(client):
    r = client.post(f"/audits/{SID}", json={"mode": "fixture"})
    assert r.status_code == 202
    assert r.json()["status"] == "running" and r.json()["mode"] == "fixture"
    events = read_events(client)
    assert [e["seq"] for e in events] == list(range(len(events)))
    assert events[0]["summary"] == "Audit started (mode fixture)"
    assert events[-1] == {**events[-1], "type": "done", "data": {"status": "completed"}}
    agents = {e["agent"] for e in events}
    assert {"exterior_analyst", "walker", "retrofit_planner", "verifier"} <= agents
    got, want = client.get(f"/audits/{SID}").json(), example("audit_response.json")
    for key in ("schema_version", "building", "rooms", "panos", "inventory", "coverage", "heat_shares",
                "model_call_summary", "questions"):
        assert got[key] == want[key], key
    assert sorted(got["observations"], key=lambda o: o["id"]) == want["observations"]
    st = got["status"]
    assert (st["status"], st["mode"], st["error"], st["replay_of"]) == ("completed", "fixture", None, None)
    assert st["started_at"] and st["finished_at"]
    assert got["report_md"].startswith("# WattWalk audit")
    assert client.get(f"/audits/{SID}/model_calls").json() == example("model_calls.json")


@pytest.mark.parametrize("scenario", PLAN_SCENARIOS)
def test_api_plan_examples(client, scenario):
    run_fixture(client)
    t0 = time.monotonic()
    r = client.post(f"/audits/{SID}/plan", json=example(f"plan_request_{scenario}.json"))
    assert time.monotonic() - t0 < 1.0
    assert r.status_code == 200, r.text
    assert r.json() == example(f"plan_response_{scenario}.json")


def test_api_plan_defaults_fill_in(client):
    run_fixture(client)
    r = client.post(f"/audits/{SID}/plan", json={})
    assert r.json() == example("plan_response_owner_5000_max_bill.json")


def test_api_errors(client, monkeypatch):
    # not found
    r = client.get("/audits/unknownSid01")
    assert (r.status_code, r.json()) == (404, example("error_not_found.json"))
    # invalid plan request
    run_fixture(client)
    r = client.post(f"/audits/{SID}/plan", json={"budget_usd": -10})
    assert (r.status_code, r.json()) == (422, example("error_invalid_plan_request.json"))
    r = client.post(f"/audits/{SID}/plan", json={"overrides": {"cooling_kwh_per_m2_yr": 1}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    r = client.post(f"/audits/{SID}/plan", json={"objective": "cheapest"})
    assert r.status_code == 422 and r.json()["error"]["details"]["field"] == "objective"
    # conflict: second start while running (the run waits on its question)
    client.delete(f"/audits/{SID}")
    _hold_on_question(monkeypatch)
    assert client.post(f"/audits/{SID}", json={"mode": "fixture"}).status_code == 202
    read_events(client, until=lambda e: e["type"] == "question")
    r = client.post(f"/audits/{SID}", json={"mode": "fixture"})
    assert (r.status_code, r.json()) == (409, example("error_conflict.json"))
    r = client.delete(f"/audits/{SID}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    client.post(f"/audits/{SID}/cancel")
    wait_status(client, SID, "cancelled")
    # fixture or replay without data
    assert client.post("/audits/2YKpZqjy5bJ", json={"mode": "fixture"}).status_code == 404
    assert client.post(f"/audits/{SID}", json={"mode": "replay"}).status_code == 404
    assert client.post(f"/audits/{SID}", json={"mode": "bogus"}).status_code == 422
    # no inventory yet
    assert client.post("/audits/nothingHere/plan", json={}).status_code == 404


def test_api_upstream_failure_fails_run(client, monkeypatch):
    from wattwalk.agent import providers
    from wattwalk.errors import UpstreamError

    def boom(sid):
        raise UpstreamError("matterport", False, "Matterport rejected the API key (HTTP 401).", http_status=401)

    monkeypatch.setattr(providers, "get_geometry", boom)
    events = run_fixture(client)
    assert events[-2]["type"] == "error" and events[-2]["data"] == {"code": "upstream_auth", "integration": "matterport"}
    assert events[-1]["summary"] == "Audit failed: upstream_auth" and events[-1]["data"] == {"status": "failed"}
    st = client.get(f"/audits/{SID}").json()["status"]
    want = example("audit_status_failed.json")
    assert st["status"] == "failed" and st["error"] == want["error"]


def test_api_cancel(client, monkeypatch):
    _hold_on_question(monkeypatch)
    client.post(f"/audits/{SID}", json={"mode": "fixture"})
    read_events(client, until=lambda e: e["type"] == "question")
    t0 = time.monotonic()
    r = client.post(f"/audits/{SID}/cancel")
    assert r.status_code == 200
    st, _ = wait_status(client, SID, "cancelled", timeout=2.0)
    assert time.monotonic() - t0 < 2.0
    events = read_events(client)
    assert events[-1]["type"] == "done" and events[-1]["data"] == {"status": "cancelled"}
    # partial files stay readable
    assert len(client.get(f"/audits/{SID}").json()["observations"]) == 10
    assert client.post("/audits/neverStarted/cancel").status_code == 404


def test_reset_keeps_cache(client):
    run_fixture(client)
    cache_file = config.CACHE_DIR / "faces" / "x.jpg"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"cached")
    r = client.delete(f"/audits/{SID}")
    assert r.status_code == 200 and r.json()["status"] == "idle"
    assert client.get(f"/audits/{SID}").status_code == 404
    assert cache_file.read_bytes() == b"cached"
    # a second run after reset works and gives the same inventory
    run_fixture(client)
    assert client.get(f"/audits/{SID}").json()["inventory"] == example("inventory.json")


def test_sse_from_seq(client):
    run_fixture(client)
    events = read_events(client, from_seq=10)
    assert events[0]["seq"] == 10 and events[-1]["type"] == "done"


def test_question_answer_updates_asset(client, monkeypatch):
    _hold_on_question(monkeypatch, 10)
    client.post(f"/audits/{SID}", json={"mode": "fixture"})
    q = read_events(client, until=lambda e: e["type"] == "question")[-1]
    assert q["data"]["question_id"] == "q001" and q["data"]["timeout_s"] == 10
    assert q["data"]["choices"] == ["led", "cfl", "incandescent", "unknown"]
    t0 = time.monotonic()
    r = client.post(f"/audits/{SID}/answer", json=example("answer_request.json"))
    assert r.status_code == 200 and r.json()["status"] == "answered" and r.json()["answer"] == "incandescent"
    events = read_events(client)
    assert time.monotonic() - t0 < 5 and events[-1]["data"] == {"status": "completed"}
    audit = client.get(f"/audits/{SID}").json()
    asset = next(a for a in audit["inventory"] if a["id"] == "a_o007")
    assert asset["attrs"]["bulb_type"]["value"] == "incandescent"
    assert asset["attrs"]["bulb_type"]["source"] == "provided_by_user"
    assert audit["questions"][0]["status"] == "answered"
    assert json.loads((config.AUDITS_DIR / SID / "verify.json").read_text())["problems"] == []
    assert client.post(f"/audits/{SID}/answer", json=example("answer_request.json")).status_code == 409
    assert client.post(f"/audits/{SID}/answer", json={"question_id": "q999", "answer": "led"}).status_code == 404


def test_question_expires(client):
    run_fixture(client)  # ask timeout is 0.3 s in tests; 30 s by default
    assert client.get(f"/audits/{SID}").json()["questions"] == example("questions.json")


def test_default_question_timeout_is_30s():
    import importlib

    import wattwalk.config as cfg
    assert importlib.reload(cfg).TIMEOUTS_S["ask_user"] == 30


def test_corrections_example(client):
    run_fixture(client)
    r = client.post(f"/audits/{SID}/corrections", json=example("correction_request.json"))
    assert r.status_code == 200, r.text
    assert r.json() == example("correction_response.json")
    # persisted, and the plan endpoint now reflects the corrected inventory
    assert client.get(f"/audits/{SID}").json()["inventory"] == example("correction_response.json")["inventory"]
    r = client.post(f"/audits/{SID}/plan", json={})
    assert r.json() == example("correction_response.json")["plan"]
    bad = example("correction_request.json") | {"asset_id": "a_nope"}
    assert client.post(f"/audits/{SID}/corrections", json=bad).status_code == 404
    bad = example("correction_request.json") | {"field": "colour"}
    assert client.post(f"/audits/{SID}/corrections", json=bad).status_code == 422


def test_explain_example(client):
    run_fixture(client)
    r = client.post(f"/audits/{SID}/explain", json=example("explain_request.json"))
    assert (r.status_code, r.json()) == (200, example("explain_response.json"))
    r = client.post(f"/audits/{SID}/explain", json=example("explain_request.json") | {"upgrade_id": "thermostat"})
    assert r.status_code == 404


def test_files_endpoint(client):
    run_fixture(client)
    r = client.get(f"/audits/{SID}/files/crops/o001.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get(f"/audits/{SID}/files/vexcel/ortho.jpg").status_code == 200
    for bad in ["inventory.json", "crops/../inventory.json", "crops/%2E%2E/status.json", "crops/missing.jpg"]:
        assert client.get(f"/audits/{SID}/files/{bad}").status_code == 404, bad


def test_meta_endpoints(client):
    assert client.get("/health").json() == example("health_fixture.json")
    assert client.get("/models/test").json() == example("test_models.json")
    assert client.get("/benchmark").json() == example("benchmark_not_run.json")


def test_running_audit_response_shape(client, monkeypatch):
    _hold_on_question(monkeypatch)
    r = client.post(f"/audits/{SID}", json={"mode": "fixture"})
    assert r.json()["status"] == "running"
    read_events(client, until=lambda e: e["type"] == "question")
    audit = client.get(f"/audits/{SID}").json()
    assert audit["status"]["status"] == "running" and audit["inventory"] == [] and audit["coverage"] is None
    client.post(f"/audits/{SID}/cancel")
    wait_status(client, SID, "cancelled")


def test_models_flags_computed_from_files(client, env, monkeypatch):
    """has_fixture needs both geometry.json and observations.json; has_replay needs a recording."""
    monkeypatch.setattr(config, "FIXTURES_DIR", env / "fixtures")
    hero = "r1NfhYW4TAr"

    def flags():
        return {m["sid"]: (m["has_fixture"], m["has_replay"]) for m in client.get("/models/test").json()}

    sids = [m["sid"] for m in client.get("/models/test").json()]
    assert sids[0] == hero and sids[-1] == SID
    assert flags()[hero] == (False, False) and flags()[SID] == (True, False)
    live = env / "fixtures" / "live" / hero
    live.mkdir(parents=True)
    (live / "geometry.json").write_text("{}")
    assert flags()[hero] == (False, False)  # observations.json still missing
    (live / "observations.json").write_text("[]")
    assert flags()[hero] == (True, False)
    rec = config.DEMO_DIR / "replays" / hero
    rec.mkdir(parents=True)
    (rec / "events.jsonl").write_text("")
    assert flags()[hero] == (True, True)


def test_asset_energy_endpoint(client):
    r = client.get(f"/audits/{SID}/energy")
    assert r.status_code == 404  # no audit yet
    run_fixture(client)
    r = client.get(f"/audits/{SID}/energy")
    assert r.status_code == 200
    assert r.json() == example("asset_energy_response.json")
    got = r.json()
    assert {a["asset_id"] for a in got["assets"]} == {a["id"] for a in client.get(f"/audits/{SID}").json()["inventory"]}


def test_research_alternatives_endpoint(client, monkeypatch):
    from wattwalk.engine import ai_alternatives as ai

    run_fixture(client)
    window = next(a for a in client.get(f"/audits/{SID}").json()["inventory"] if a["label"] == "window")
    url = f"/audits/{SID}/assets/{window['id']}/alternatives/research"
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    r = client.post(url)
    assert r.status_code == 503 and "DEEPSEEK_API_KEY" in r.json()["error"]["message"]
    assert client.post(f"/audits/{SID}/assets/nope/alternatives/research").status_code == 404

    reply = {"ideas": [{"title": "Thermal curtains", "why": "", "kwh_cut_pct": [10, 20],
                        "cost_usd": [60, 150], "who": "tenant"}]}
    monkeypatch.setattr(ai, "_ask_deepseek", lambda model_id: (lambda prompt: json.dumps(reply)))
    r = client.post(url)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["asset_id"] == window["id"] and body["cached"] is False
    assert [a["title"] for a in body["alternatives"]] == ["Thermal curtains"]
    assert client.post(url).json()["cached"] is True
