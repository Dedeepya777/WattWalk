"""Vision unit tests: views, quality, parsing, router (plan Appendix B, Person 2)."""
from __future__ import annotations

import itertools
import random

import numpy as np
import pytest
from PIL import Image

from wattwalk.contracts import ModelGeometry
from wattwalk.vision.detect import extract_json, parse_attrs, parse_detections
from wattwalk.vision.images import quality
from wattwalk.vision.prompts import DETECT_PROMPT, VOCAB, attr_prompt, detect_prompt
from wattwalk.vision.router import next_action
from wattwalk.vision.types import RouterState, Signals
from wattwalk.vision.views import neighbor_pano, plan_views


# ---------- views ----------

def test_plan_views_fixture(geometry):
    tasks = plan_views(geometry)
    assert [t.pano_id for t in tasks] == ["p01", "p02", "p03", "p04", "p05", "p06", "p07"]
    assert [t.reason for t in tasks] == ["best_view", "second_view_large_room"] + ["best_view"] * 5
    assert tasks[0].room_id == tasks[1].room_id == "r_living"


def test_plan_views_no_rooms_fallback(geometry):
    panos = [geometry.panos[0].model_copy(update={"id": f"p{i:02d}", "room_id": None}) for i in range(30)]
    no_rooms = ModelGeometry.model_validate({**geometry.model_dump(), "rooms": [], "panos": [p.model_dump() for p in panos]})
    tasks = plan_views(no_rooms)
    assert len(tasks) == 20 and all(t.reason == "no_rooms_fallback" and t.room_id is None for t in tasks)
    assert len({t.pano_id for t in tasks}) == 20


def test_plan_views_skips_room_without_pano(geometry):
    rooms = [r.model_copy(update={"pano_ids": []}) if r.id == "r_closet" else r for r in geometry.rooms]
    tasks = plan_views(geometry.model_copy(update={"rooms": rooms}))
    assert "p07" not in [t.pano_id for t in tasks]


def test_neighbor_pano_same_room_first(geometry, fixture_observations):
    o001 = fixture_observations[0]  # living room, seen from p01
    assert neighbor_pano(geometry, o001, set()).id == "p02"
    o003 = fixture_observations[2]  # bedroom has one pano; nothing within 3 m of its window
    assert neighbor_pano(geometry, o003, set()) is None


# ---------- image quality ----------

def _save(tmp_path, name, array):
    path = tmp_path / name
    Image.fromarray(array.astype(np.uint8), mode="L").save(path)
    return path


def test_quality_thresholds(tmp_path):
    rng = np.random.default_rng(0)
    sharp = _save(tmp_path, "sharp.png", rng.integers(60, 200, (256, 256)))
    dark = _save(tmp_path, "dark.png", rng.integers(0, 40, (256, 256)))
    bright = _save(tmp_path, "bright.png", rng.integers(230, 256, (256, 256)))
    assert quality(sharp).accepted
    assert not quality(dark).accepted and quality(dark).brightness < 40
    assert not quality(bright).accepted


def _scene(blur_radius: float = 0):
    """Walls, a door and a window: real edges, like a room photo."""
    from PIL import ImageDraw, ImageFilter
    im = Image.new("L", (512, 512), 150)
    d = ImageDraw.Draw(im)
    d.rectangle([60, 80, 200, 470], fill=225)
    d.rectangle([280, 100, 460, 300], fill=70)
    for y in range(110, 300, 22):
        d.line([285, y, 455, y], fill=200, width=6)
    return im.filter(ImageFilter.GaussianBlur(blur_radius)) if blur_radius else im


def test_quality_rejects_blurred_scene(tmp_path):
    sharp, blurred = tmp_path / "scene.png", tmp_path / "scene_blur.png"
    _scene().save(sharp)
    _scene(4).save(blurred)
    assert quality(sharp).accepted
    q = quality(blurred)
    assert q.blur < 60 and not q.accepted


def test_quality_accepts_sharp_plain_wall(tmp_path):
    """Regression: sharp photos of plain walls and closet doors (hero scan 2ibibwUGQAe) were
    rejected as too blurry because they have few edges, wrongly marking rooms partial."""
    from PIL import ImageDraw
    wall = Image.new("L", (512, 512), 175)
    ImageDraw.Draw(wall).line([250, 0, 250, 512], fill=120, width=3)  # one crisp door edge
    path = tmp_path / "wall.png"
    wall.save(path)
    q = quality(path)
    assert q.blur < 60 and q.accepted
    blank = tmp_path / "blank.png"
    Image.new("L", (512, 512), 175).save(blank)
    assert quality(blank).accepted  # nothing to judge: the model simply finds nothing


# ---------- parsing ----------

def test_extract_json_tolerates_chatter():
    assert extract_json('Sure! {"image_ok": true, "detections": []} hope that helps') == {"image_ok": True, "detections": []}
    assert extract_json("no json here") is None
    assert extract_json('{"broken": ') is None


def test_parse_detections_rejects_bad_labels():
    raw = {"image_ok": True, "detections": [
        {"label": "sofa", "bbox": [10, 10, 200, 200], "attrs": {}},
        {"label": "window", "bbox": [10, 10, 200, 200], "attrs": {"shading": "blinds", "panes": "double", "color": "red"}},
    ]}
    dets = parse_detections(raw, 768, 2048)
    assert [d.label for d in dets] == ["window"]
    assert dets[0].attrs == {"shading": "blinds", "width_m": None, "height_m": None}  # panes and color dropped


def test_parse_detections_scales_bbox():
    raw = {"detections": [{"label": "ceiling_light", "bbox": [300, 15, 384, 60], "attrs": {"bulb_type": "led", "bulb_count": 2}}]}
    (det,) = parse_detections(raw, 768, 2048)
    assert (det.bbox.x0, det.bbox.y0, det.bbox.x1, det.bbox.y1) == (800, 40, 1024, 160)
    assert det.attrs == {"bulb_type": "led", "bulb_count": 2}


def test_parse_detections_drops_small_inverted_and_clamps():
    raw = {"detections": [
        {"label": "lamp", "bbox": [10, 10, 15, 15]},           # smaller than 12 x 12
        {"label": "lamp", "bbox": [100, 100, 50, 150]},        # x1 <= x0
        {"label": "lamp", "bbox": [700, 700, 900, 900]},       # clamped to 768
    ]}
    (det,) = parse_detections(raw, 768, 768)
    assert (det.bbox.x1, det.bbox.y1) == (768, 768)


def test_parse_detections_iou_keeps_larger():
    raw = {"detections": [
        {"label": "window", "bbox": [100, 100, 300, 300]},
        {"label": "window", "bbox": [110, 110, 300, 300]},
        {"label": "lamp", "bbox": [150, 150, 330, 330]},  # overlaps the window partly: a separate object
    ]}
    dets = parse_detections(raw, 768, 768)
    assert sorted((d.label, d.bbox.x0) for d in dets) == [("lamp", 150), ("window", 100)]


def test_values_outside_vocabulary_become_unknown():
    raw = {"detections": [{"label": "ceiling_light", "bbox": [0, 0, 100, 100],
                           "attrs": {"bulb_type": "halogen", "bulb_count": 2.5}}]}
    (det,) = parse_detections(raw, 768, 768)
    assert det.attrs == {"bulb_type": None, "bulb_count": None}
    assert parse_attrs({"attrs": {"bulb_type": "LED"}}, "lamp") == {"bulb_type": "led", "bulb_count": None}
    assert parse_attrs(None, "thermostat") == {"thermostat_type": None}


def test_prompts_match_vocabulary():
    p = detect_prompt(768, 768)
    assert "768 x 768" in p and '{"image_ok": true' in p and "{w}" in DETECT_PROMPT
    ap = attr_prompt("ceiling_light")
    assert '"incandescent"' in ap and "bulb_count (integer)" in ap and "{" in ap
    for label in ("window", "thermostat", "refrigerator"):
        for value in [v for vals in VOCAB[label].values() if isinstance(vals, list) for v in vals]:
            if label != "window" or value not in ("single", "double"):  # panes is never asked
                assert f'"{value}"' in DETECT_PROMPT


# ---------- router ----------

def _light(obs, oid="o005"):
    return obs.model_copy(update={"id": oid})


def _run_ladder(obs, state, base: Signals, max_steps=10):
    actions = []
    for _ in range(max_steps):
        signals = base.model_copy(update={
            "escalation_failed": [obs.label, "bulb_type"] in state.escalation_failed,
            "asked": [obs.label, "bulb_type"] in state.asked})
        action = next_action(obs, state, signals)
        actions.append(action)
        state.tried.setdefault(obs.id, []).append(action)
        if action == "escalate_large":
            state.escalation_failed.append([obs.label, "bulb_type"])  # still unknown afterwards
        if action == "ask_user":
            state.asked.append([obs.label, "bulb_type"])
        if action in ("accept", "leave_unknown"):
            break
    return actions


def test_router_ladder(fixture_observations):
    state = RouterState()
    base = Signals(key_unknown=True, user_answerable=True)
    first = _run_ladder(_light(fixture_observations[4], "o005"), state, base)
    assert first == ["hires_crop", "escalate_large", "ask_user", "leave_unknown"]
    second = _run_ladder(_light(fixture_observations[5], "o006"), state, base)
    assert second == ["hires_crop", "leave_unknown"]  # R6: escalation already failed; R7: already asked


def test_router_accepts_known_and_respects_cap(fixture_observations):
    window = fixture_observations[0]
    assert next_action(window, RouterState(), Signals()) == "accept"
    light = fixture_observations[4]
    state = RouterState(tried={light.id: ["hires_crop"]})
    capped = Signals(key_unknown=True, hard_label=True, large_cap_reached=True)
    assert next_action(light, state, capped) == "leave_unknown"
    assert next_action(light, state, capped.model_copy(update={"large_cap_reached": False})) == "escalate_large"


def test_router_quality_issue_tries_neighbor_first(fixture_observations):
    light = fixture_observations[4]
    assert next_action(light, RouterState(), Signals(key_unknown=True, quality_issue=True, neighbor_exists=True)) == "neighbor_view"


def test_router_terminates(fixture_observations):
    light = fixture_observations[4]
    flags = list(Signals.model_fields)
    rng = random.Random(1)
    for combo in itertools.product([False, True], repeat=len(flags)):
        state = RouterState()
        steps = 0
        while True:
            signals = Signals(**dict(zip(flags, combo)))
            if rng.random() < 0.3:  # adversarial: signals flip between calls
                signals = Signals(**{f: rng.random() < 0.5 for f in flags})
            action = next_action(light, state, signals)
            state.tried.setdefault(light.id, []).append(action)
            steps += 1
            assert steps <= 5
            if action in ("accept", "leave_unknown"):
                break
        tried = state.tried[light.id]
        assert len(set(tried[:-1])) == len(tried[:-1])  # no action repeats before the final one


# ---------- local Ollama backend ----------

def test_ollama_backend_routes_by_model_prefix(monkeypatch):
    import io
    import json as _json
    import urllib.request

    from wattwalk.vision import detect

    sent = {}

    def fake_urlopen(req, timeout):
        sent.update(_json.loads(req.data))
        reply = {"message": {"content": '{"image_ok": true, "detections": []}'}, "prompt_eval_count": 700, "eval_count": 20}
        return io.BytesIO(_json.dumps(reply).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(detect, "_converse", lambda *a: (_ for _ in ()).throw(AssertionError("Bedrock must not be called")))
    raw, call, _ = detect.call_vision("ollama/qwen2.5vl:7b", b"jpegbytes", "prompt", "s", "walker", "detect", image_px=768)
    assert raw == {"image_ok": True, "detections": []}
    assert sent["model"] == "qwen2.5vl:7b" and sent["format"] == "json" and sent["messages"][0]["images"]
    assert (call.tokens_in, call.tokens_out, call.model_id) == (700, 20, "ollama/qwen2.5vl:7b")


# ---------- regressions from the first real-scan walk (2ibibwUGQAe) ----------

def test_parse_one_object_two_labels_keeps_first():
    raw = {"detections": [
        {"label": "window", "bbox": [235, 425, 565, 627], "attrs": {"shading": "blinds"}},
        {"label": "lamp", "bbox": [235, 425, 565, 627], "attrs": {}},
        {"label": "lamp", "bbox": [30, 300, 80, 360], "attrs": {}},  # a different object: kept
    ]}
    dets = parse_detections(raw, 1024, 2048)
    assert sorted(d.label for d in dets) == ["lamp", "window"]
    assert next(d for d in dets if d.label == "lamp").bbox.x0 == 60


def test_room_for_object_seen_through_doorway(geometry):
    from wattwalk.contracts import Vec3
    from wattwalk.vision.views import room_for
    p05 = next(p for p in geometry.panos if p.id == "p05")  # bathroom pano
    assert room_for(geometry, p05, None) == "r_bath"                          # no anchor: pano's room
    assert room_for(geometry, p05, Vec3(x=5.0, y=6.0, z=1.5)) == "r_bath"    # inside its own room
    assert room_for(geometry, p05, Vec3(x=4.1, y=5.0, z=1.5)) == "r_bath"    # on the shared wall
    assert room_for(geometry, p05, Vec3(x=2.0, y=5.5, z=1.5)) == "r_kitchen" # through the doorway


def test_prompt_mentions_mirror_rule():
    assert "mirror" in DETECT_PROMPT and "exactly one label" in DETECT_PROMPT


def test_second_look_keeps_only_confirmed():
    from wattwalk.vision.detect import second_look_keeps
    from wattwalk.vision.prompts import verify_prompt
    assert second_look_keeps({"object": "Window"}, "window")
    assert not second_look_keeps({"object": "mirror"}, "window")
    assert second_look_keeps(None, "window")  # unparseable answer: keep the detection
    p = verify_prompt("ceiling_light")
    assert "ceiling_light" in p and "smoke_detector" in p and '{"object": "..."}' in p
    assert "detector thought" not in p  # neutral: showing the guess made the model repeat it


def test_second_look_relabels_only_to_offered_vocab_labels():
    from wattwalk.vision.detect import second_look_label
    assert second_look_label({"object": "mini split"}, "window_ac") == "mini_split"
    assert second_look_label({"object": "ceiling_light"}, "lamp") == "ceiling_light"
    assert second_look_label({"object": "doorway"}, "window") is None      # not an energy asset: drop
    assert second_look_label({"object": "refrigerator"}, "window") is None # in VOCAB but not offered
    assert second_look_label({"object": "lamp"}, "lamp") == "lamp"
    assert second_look_label({}, "lamp") == "lamp"


def test_no_silent_fallback(monkeypatch):
    """A broken dependency must crash the import with the real error, never fall back to fixture data."""
    import importlib
    import sys

    for name in [m for m in sys.modules if m.startswith("wattwalk.vision.") and m != "wattwalk.vision.types"]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "wattwalk.spatial.geometry", None)  # import now raises ImportError
    with pytest.raises(ImportError):
        importlib.import_module("wattwalk.vision.walk")


def test_no_temporary_markers_left():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "wattwalk"
    hits = [str(p) for d in ("vision", "inventory", "eval") for p in (root / d).rglob("*.py")
            if "TEMPORARY" in p.read_text(encoding="utf-8")]
    assert hits == []


def _fake_registry(monkeypatch):
    import sys
    import types

    recorded = []
    registry = types.ModuleType("wattwalk.health_registry")
    registry.record = lambda integration, ok, detail="": recorded.append((integration, ok, detail))
    monkeypatch.setitem(sys.modules, "wattwalk.health_registry", registry)
    return recorded


def test_records_health_on_success_and_failure(monkeypatch):
    from wattwalk.errors import UpstreamError
    from wattwalk.vision import detect

    recorded = _fake_registry(monkeypatch)
    monkeypatch.setattr(detect, "_converse", lambda m, i, p: ("{}", {}))
    detect._call_model("bedrock-model", b"x", "p")

    def fail(m, i, p):
        raise UpstreamError("bedrock", True, "throttled", 429)

    monkeypatch.setattr(detect, "_converse", fail)
    with pytest.raises(UpstreamError):
        detect._call_model("bedrock-model", b"x", "p")
    assert recorded == [("bedrock", True, ""), ("bedrock", False, "UpstreamError: HTTP 429")]


def test_probe_never_raises(monkeypatch):
    from wattwalk.vision import detect, probes

    recorded = _fake_registry(monkeypatch)

    def boom(m, i, p):
        raise RuntimeError("client exploded")

    monkeypatch.setattr(detect, "_converse", boom)
    ok, detail = probes.probe_bedrock("bedrock-model")
    assert ok is False and "client exploded" in detail
    assert probes.probe_vision("") == (False, "no small vision model id configured")
    monkeypatch.setattr(detect, "_converse", lambda m, i, p: ('{"ok": true}', {}))
    assert probes.probe_vision("bedrock-model")[0] is True
    assert recorded[-1] == ("bedrock", True, "")
