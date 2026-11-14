"""Person 3 agent tests: verifier, Deep Agents wiring (offline), replay. Run: pytest backend/tests/agent"""
from __future__ import annotations

import asyncio
import json

import pytest

from wattwalk import config, store
from wattwalk.contracts import Asset

from ..api.conftest import SID, client, env, example, read_events, run_fixture  # noqa: F401  (pytest fixtures)


# ----------------------------------------------------------------------------- verifier
def test_verifier_passes_on_fixture(client):
    from wattwalk.agent.verify import verify_audit

    run_fixture(client)
    assert verify_audit(SID) == []


def test_verifier_detects_duplicate(client):
    from wattwalk.agent.verify import verify_audit

    run_fixture(client)
    inv = store.read(SID, "inventory.json", list[Asset])
    store.write(SID, "inventory.json", inv + [inv[0]])
    problems = verify_audit(SID)
    assert any("a_o001" in p for p in problems)
    assert any("coverage assets_unique" in p for p in problems)


def test_verifier_detects_injected_inconsistencies(client):
    from wattwalk.agent.verify import verify_audit

    run_fixture(client)
    d = config.AUDITS_DIR / SID
    plan = json.loads((d / "plan_default.json").read_text())
    plan["totals"]["kwh_saved_yr"] += 50
    plan["upgrades"][0]["asset_ids"].append("a_ghost")
    (d / "plan_default.json").write_text(json.dumps(plan))
    inv = json.loads((d / "inventory.json").read_text())
    inv[-1]["attrs"]["burners"] = {"value": None, "source": "visible_in_scan", "note": "", "evidence_obs_ids": []}
    (d / "inventory.json").write_text(json.dumps(inv))
    (d / "crops" / "o003.jpg").unlink()
    problems = " | ".join(verify_audit(SID))
    for fragment in ["differ from a fresh engine run", "line kWh sum", "a_ghost", "null-iff-needs_verification",
                     "a_o010 has unknown attributes but no next_step", "crop crops/o003.jpg"]:
        assert fragment in problems, fragment


# ----------------------------------------------------------------------------- deep agents (offline)
def test_deep_agents_delegates_to_all_subagents(env):
    pytest.importorskip("deepagents")
    from wattwalk.agent import context, deep
    from wattwalk.agent.context import RunContext
    from wattwalk.agent.events import EventBus
    from wattwalk.agent.run import _prepare_fixture

    from .fake_planner import RulePlanner

    _prepare_fixture(SID)
    (config.AUDITS_DIR / SID / "model_calls.json").unlink()
    ctx = RunContext(sid=SID, mode="fixture", bus=EventBus(SID))
    token = config.RUN_MODE_OVERRIDE.set("fixture")
    try:
        deep.run(ctx, model=RulePlanner())
    finally:
        config.RUN_MODE_OVERRIDE.reset(token)
        context.release(SID)

    events = ctx.bus.events
    delegated = [e.data["subagent"] for e in events if e.data.get("tool") == "task"]
    assert delegated == ["exterior_analyst", "walker", "retrofit_planner", "verifier"]
    by_agent = {e.agent for e in events if e.type in ("tool_call", "tool_result")}
    assert {"exterior_analyst", "walker", "retrofit_planner", "verifier", "planner"} <= by_agent
    assert any(e.type == "todo" and e.agent == "planner" for e in events)
    # same inventory and default plan as the scripted run
    assert store.read(SID, "inventory.json") == example("inventory.json")
    assert store.read(SID, "plan_default.json") == example("plan_response_owner_5000_max_bill.json")
    assert store.read(SID, "verify.json") == {"problems": []}
    # files: todo and report under agent/, report promoted; write outside /agent/ was refused
    assert (config.AUDITS_DIR / SID / "agent" / "todo.md").exists()
    assert store.read_text(SID, "report.md").startswith("# WattWalk audit (planner)")
    assert "1748.8 kWh/yr" in store.read_text(SID, "report.md")
    # planner calls logged with tier planner
    calls = store.read(SID, "model_calls.json")
    assert calls and all(c["model_tier"] == "planner" and c["tokens_in"] == 100 for c in calls)


# ----------------------------------------------------------------------------- replay
def test_replay_is_labeled_and_reproduces_inventory(client):
    from wattwalk.api import replay

    run_fixture(client)
    recorded = client.get(f"/audits/{SID}").json()
    with pytest.raises(SystemExit):
        replay.promote(SID)  # only completed live runs, unless forced
    replay.promote(SID, force=True)
    assert client.get("/models/test").json()[0]["has_replay"] is True
    client.delete(f"/audits/{SID}")

    r = client.post(f"/audits/{SID}", json={"mode": "replay"})
    assert r.status_code == 202
    st = r.json()
    assert st["mode"] == "replay" and st["replay_of"] == recorded["status"]["started_at"]
    events = read_events(client, timeout=30)
    assert events[0]["summary"].startswith(f"Replay of run recorded at {st['replay_of']}")
    assert events[-1]["data"] == {"status": "completed"}
    assert len(events) == len(store.read_text(SID, "events.jsonl").splitlines())
    got = client.get(f"/audits/{SID}").json()
    assert got["status"]["mode"] == "replay" and got["status"]["replay_of"] == st["replay_of"]
    assert got["inventory"] == recorded["inventory"]
    assert got["coverage"] == recorded["coverage"]
    # deterministic endpoints work on replayed data
    assert client.post(f"/audits/{SID}/plan", json={}).json() == example("plan_response_owner_5000_max_bill.json")
