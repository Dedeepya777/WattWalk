"""Offline replay of real-scan vision fixtures (fixtures/live/<sid>/: observations + router trace).

For every sid with saved files, fixture inspect_view over its panoramas plus fixture resolve over every
observation reproduces the saved observations exactly, with no model calls and no network, and
build_inventory on them is deterministic.
"""
import json

import pytest

from wattwalk import config, store
from wattwalk.contracts import ModelGeometry, Observation
from wattwalk.inventory import build_inventory
from wattwalk.vision import fixture, walk

LIVE = config.FIXTURES_DIR / "live"
SIDS = sorted(p.name for p in LIVE.iterdir()
              if (p / "observations.json").exists() and (p / "router_trace.json").exists()) if LIVE.exists() else []


def _saved(sid):
    return [Observation.model_validate(o) for o in json.loads((LIVE / sid / "observations.json").read_text())]


def _geometry(sid):
    path = LIVE / sid / "geometry.json"
    src = path if path.exists() else config.EXAMPLES_DIR / "model_geometry.json"  # questions only need room labels
    return ModelGeometry.model_validate_json(src.read_text())


@pytest.mark.parametrize("sid", SIDS)
def test_traced_fixture_replays_exactly(sid):
    fixture._final_observations.cache_clear()
    fixture._trace.cache_clear()
    saved = _saved(sid)
    geometry = _geometry(sid)
    for pano_id in sorted({o.pano_id for o in saved}):
        result = walk.inspect_view(sid, geometry, None, pano_id)
        store.append_observations(sid, result.observations)
    for oid in walk.pending_observation_ids(sid):
        for _ in range(8):
            rr = walk.resolve(sid, geometry, oid, lambda q: None)  # questions expire, as when nobody answers
            store.apply_resolve(sid, rr)
            if rr.final:
                break
        else:
            pytest.fail(f"{oid} never finished")
    replayed = {o.id: o.model_dump(exclude={"created_at"}) for o in store.observations(sid)}
    expected = {o.id: o.model_dump(exclude={"created_at"}) for o in saved}
    assert replayed == expected
    first = [a.model_dump() for a in build_inventory(store.observations(sid))]
    assert first == [a.model_dump() for a in build_inventory(store.observations(sid))]


def test_trace_overrides_fixture_rules(tmp_path, monkeypatch):
    """A recorded neighbor_view step (not in the fixtureUnitA rules) replays and ends on the saved observation."""
    obs = Observation.model_validate(json.loads((config.EXAMPLES_DIR / "observations.json").read_text())[0])
    folder = tmp_path / "live" / "realSid0001"
    folder.mkdir(parents=True)
    (folder / "observations.json").write_text(json.dumps([obs.model_dump(mode="json")]))
    (folder / "router_trace.json").write_text(json.dumps({"observations": {obs.id: {"actions": ["neighbor_view", "accept"]}}}))
    monkeypatch.setattr(config, "FIXTURES_DIR", tmp_path)
    fixture._final_observations.cache_clear()
    fixture._trace.cache_clear()
    assert fixture.script(obs, "realSid0001") == ["neighbor_view", "accept"]
    geometry = ModelGeometry.model_validate_json((config.EXAMPLES_DIR / "model_geometry.json").read_text())
    store.append_observations("realSid0001", walk.inspect_view("realSid0001", geometry, None, obs.pano_id).observations)
    actions = []
    while True:
        rr = walk.resolve("realSid0001", geometry, obs.id, lambda q: None)
        store.apply_resolve("realSid0001", rr)
        actions.append(rr.action)
        if rr.final:
            break
    assert actions == ["neighbor_view", "accept"]
    assert store.observations("realSid0001")[0].model_dump(exclude={"created_at"}) == obs.model_dump(exclude={"created_at"})
