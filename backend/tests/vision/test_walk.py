"""End-to-end vision tests: the fixture walk and the live pipeline with a fake Bedrock (Person 2)."""
from __future__ import annotations

import json
from collections import Counter

import numpy as np
import pytest
from PIL import Image

from wattwalk import config, store
from wattwalk.contracts import Asset, Coverage, ModelCall, Observation, Question
from wattwalk.errors import UpstreamError
from wattwalk.inventory import build_inventory, compute_coverage
from wattwalk.vision import detect, walk
from tests.conftest import load_example

SID = "fixtureUnitA"


def _walk(sid, geometry, ask):
    actions = []
    for task in walk.plan_views(geometry):
        result = walk.inspect_view(sid, geometry, task.room_id, task.pano_id)
        store.append_observations(sid, result.observations)
    for oid in walk.pending_observation_ids(sid):
        while True:
            rr = walk.resolve(sid, geometry, oid, ask)
            store.apply_resolve(sid, rr)
            actions.append((oid, rr.action))
            if rr.final:
                break
    return actions


def test_fixture_walk_reproduces_examples(geometry):
    asked = []
    actions = _walk(SID, geometry, lambda q: asked.append(q) or None)
    observations = store.observations(SID)
    assert observations == [Observation.model_validate(o) for o in load_example("observations.json")]
    inventory = build_inventory(observations)
    assert inventory == [Asset.model_validate(a) for a in load_example("inventory.json")]
    reviewed, rejected, partial = walk.coverage_inputs(SID, geometry)
    coverage = compute_coverage(geometry, observations, inventory, reviewed, rejected, partial)
    assert coverage == Coverage.model_validate(load_example("coverage.json"))
    assert store.read(SID, "questions.json", list[Question]) == [Question.model_validate(q) for q in load_example("questions.json")]
    assert len(asked) == 1 and asked[0].status == "open"

    # router actions and call counts of plan 4.6.2: 27 detect, 4 high-res, 1 large, 1 question
    counts = Counter(a for _, a in actions)
    assert counts["hires_crop"] == 4 and counts["escalate_large"] == 1 and counts["ask_user"] == 1
    calls = store.read(SID, "model_calls.json", list[ModelCall])
    assert Counter((c.kind, c.model_tier) for c in calls) == {("detect", "small"): 27, ("attr", "small"): 4, ("attr", "large"): 1}
    assert max(Counter(oid for oid, _ in actions).values()) <= 5


def test_fixture_walk_with_answer(geometry):
    _walk(SID, geometry, lambda q: "led")
    o007 = next(o for o in store.observations(SID) if o.id == "o007")
    assert o007.attrs["bulb_type"].value == "led" and o007.attrs["bulb_type"].source == "provided_by_user"
    (q,) = store.read(SID, "questions.json", list[Question])
    assert q.status == "answered" and q.answer == "led"


def test_fixture_unknown_sid_raises(geometry):
    with pytest.raises(ValueError, match="no vision fixture for sid"):
        walk.inspect_view("noSuchSid", geometry, "r_living", "p01")


# ---------- live pipeline with a fake Bedrock ----------

class FakeBedrock:
    """Answers detection prompts with a fixed detection per face and attribute prompts per tier."""

    def __init__(self, small_attr="unknown", large_attr="led", fail=False, second_look="ceiling_light"):
        self.calls = []
        self.small_attr, self.large_attr, self.fail, self.second_look = small_attr, large_attr, fail, second_look

    def converse(self, modelId, messages, inferenceConfig):
        prompt = messages[0]["content"][1]["text"]
        kind = "verify" if "What is the main object" in prompt else ("attr" if "close crop" in prompt else "detect")
        self.calls.append((modelId, kind))
        if self.fail:
            raise RuntimeError("throttled")
        if kind == "verify":
            body = {"object": self.second_look}
        elif kind == "attr":
            value = self.large_attr if modelId == "large-id" else self.small_attr
            body = {"attrs": {"bulb_type": value, "bulb_count": 2}}
        else:
            body = {"image_ok": True, "detections": [
                {"label": "ceiling_light", "bbox": [280, 20, 330, 60], "attrs": {"bulb_type": "unknown", "bulb_count": 2}},
                {"label": "sofa", "bbox": [100, 400, 500, 700], "attrs": {}},
            ]}
        return {"output": {"message": {"content": [{"text": "Here you go: " + json.dumps(body)}]}},
                "usage": {"inputTokens": 1600, "outputTokens": 120}}


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(config, "VISION_MODE", "live")
    monkeypatch.setattr(config, "SMALL_VISION_MODEL_ID", "small-id")
    monkeypatch.setattr(config, "LARGE_VISION_MODEL_ID", "large-id")
    fake = FakeBedrock()
    detect.set_client(fake)
    yield fake
    detect.set_client(None)


def _faces(sid, pano, dark_faces=()):
    rng = np.random.default_rng(7)
    folder = config.CACHE_DIR / "faces" / sid
    folder.mkdir(parents=True, exist_ok=True)
    for face in (1, 2, 3, 4):
        lo, hi = (0, 30) if face in dark_faces else (60, 200)
        pixels = rng.integers(lo, hi, (2048, 2048)).astype(np.uint8)
        Image.fromarray(pixels, mode="L").save(folder / f"{pano}_{face}_2k.jpg")
        Image.fromarray(pixels, mode="L").resize((4096, 4096), Image.NEAREST).save(folder / f"{pano}_{face}_4k.jpg")


def test_live_inspect_view(geometry, live):
    _faces("liveA", "p05", dark_faces=(4,))
    result = walk.inspect_view("liveA", geometry, "r_bath", "p05")
    assert result.faces_inspected == [1, 2, 3] and result.faces_rejected == [4]
    assert result.calls == 6  # 3 detections + 3 second looks (one per ceiling light)
    assert [o.id for o in result.observations] == ["o001", "o002", "o003"]  # sofa dropped, one light per face
    o = result.observations[0]
    assert o.label == "ceiling_light" and o.attrs["bulb_type"].source == "needs_verification"
    assert o.attrs["bulb_count"].value == 2 and o.model_id == "small-id" and o.anchor_method == "ceiling_plane"
    assert (o.bbox.x0, o.bbox.y0) == (747, 53)  # scaled from 768 px to 2048 px face pixels
    assert store.audit_path("liveA", "crops", "o001.jpg").exists()
    calls = store.read("liveA", "model_calls.json", list[ModelCall])
    assert [c.id for c in calls] == [f"c{i:03d}" for i in range(1, 7)] and calls[0].tokens_in == 1600
    _, rejected, partial = walk.coverage_inputs("liveA", geometry)
    assert rejected == 1 and partial["r_bath"].startswith("1 of 4 faces rejected as too dark")


def test_live_resolve_ladder_and_cache(geometry, live):
    _faces("liveA", "p03")
    store.append_observations("liveA", walk.inspect_view("liveA", geometry, "r_bed", "p03").observations)
    seen = []
    while True:
        rr = walk.resolve("liveA", geometry, "o001", lambda q: None)
        store.apply_resolve("liveA", rr)
        seen.append(rr.action)
        if rr.final:
            break
    assert seen == ["hires_crop", "escalate_large", "accept"]  # large model read "led"
    o = next(x for x in store.observations("liveA") if x.id == "o001")
    assert o.attrs["bulb_type"].value == "led" and o.escalated and o.model_tier == "large" and o.face_px == 4096
    detects_before = sum(1 for _, k in live.calls if k == "detect")
    walk.inspect_view("liveA", geometry, "r_bed", "p03")  # identical images and prompt: served from the LLM cache
    assert sum(1 for _, k in live.calls if k == "detect") == detects_before
    assert store.read("liveA", "model_calls.json", list[ModelCall])[-1].cache_hit


def test_live_question_after_failed_escalation(geometry, live):
    live.large_attr = "unknown"
    _faces("liveA", "p03")
    store.append_observations("liveA", walk.inspect_view("liveA", geometry, "r_bed", "p03").observations)
    first = []
    while True:
        rr = walk.resolve("liveA", geometry, "o001", lambda q: "cfl")
        store.apply_resolve("liveA", rr)
        first.append(rr.action)
        if rr.final:
            break
    assert first == ["hires_crop", "escalate_large", "ask_user", "accept"]
    second = [walk.resolve("liveA", geometry, "o002", lambda q: "cfl") for _ in range(2)]
    assert [r.action for r in second] == ["hires_crop", "leave_unknown"]  # R6 and R7 skip the second light


def test_live_three_failures_fail_the_run(geometry, live):
    live.fail = True
    _faces("liveA", "p03")
    with pytest.raises(UpstreamError, match="consecutive"):
        walk.inspect_view("liveA", geometry, "r_bed", "p03")


def test_live_second_look_drops_unconfirmed(geometry, live):
    """The second look removes a detection the model does not confirm (a 'light' that is a smoke detector)."""
    live.second_look = "smoke_detector"
    _faces("liveA", "p03")
    result = walk.inspect_view("liveA", geometry, "r_bed", "p03")
    assert result.observations == [] and result.calls == 8  # 4 detections + 4 second looks, all rejected
    assert sum(1 for _, k in live.calls if k == "verify") == 4


def test_live_second_look_relabels_to_another_vocab_label(geometry, live, monkeypatch):
    """An answer that is another offered VOCAB label relabels the detection instead of dropping it."""
    monkeypatch.setitem(walk.SECOND_LOOK_LABELS, "ceiling_light", ["ceiling_light", "lamp", "other"])
    live.second_look = "lamp"
    _faces("liveA", "p03")
    result = walk.inspect_view("liveA", geometry, "r_bed", "p03")
    assert len(result.observations) == 4
    assert {o.label for o in result.observations} == {"lamp"}
    assert all(set(o.attrs) <= {"bulb_type", "bulb_count"} for o in result.observations)


def test_live_second_look_can_be_switched_off(geometry, live, monkeypatch):
    monkeypatch.setattr(walk, "SECOND_LOOK_LABELS", {})
    live.second_look = "smoke_detector"
    _faces("liveA", "p03")
    result = walk.inspect_view("liveA", geometry, "r_bed", "p03")
    assert len(result.observations) == 4 and result.calls == 4
