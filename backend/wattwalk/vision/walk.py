"""Canonical vision entry points: plan_views, inspect_view, resolve (plan 7.13, 8, Appendix H.3). Owner: Person 2.

Person 3's agent calls these. Live mode calls Bedrock; fixture mode replays shared/examples
(see vision/fixture.py) with no model calls.
"""
from __future__ import annotations

import io
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from PIL import Image

from .. import config, store
from ..contracts import Attr, BBox, ModelCall, ModelGeometry, Observation, Pano, Room
from ..errors import UpstreamError
from ..inventory import THRESHOLD_M, same_object
from . import fixture
from .deps import anchor_from_bbox, get_face_image
from .detect import call_vision, detect_px, image_ok, now_iso, parse_attrs, parse_detections
from .images import BRIGHTNESS_MAX, BRIGHTNESS_MIN, crop, downscale, quality, rejection_reason
from .prompts import ATTR_ORDER, KEY_ATTR, NON_VISUAL, USER_ANSWERABLE, attr_prompt, detect_prompt
from .questions import apply_answer, make_question
from .router import key_unknown, next_action
from .state import load_state, lock, log_calls, next_observation_ids, next_question_id, save_state
from .types import (FINAL_ACTIONS, MAX_LARGE_CALLS_PER_AUDIT, AskFn, InspectResult, RawDetection, RejectedFace,
                    ResolveResult, RouterState, Signals)
from .views import face_toward, neighbor_pano, plan_views, room_for  # noqa: F401  (plan_views re-exported, canonical)

FACES = (1, 2, 3, 4)  # horizon faces only (decision D10)
DETECT_PX = 768  # fallback when a call did not report its image size
MAX_CONSECUTIVE_FAILURES = 3


def _fixture_mode() -> bool:
    return config.effective_vision_mode() == "fixture"


def _pano(geometry: ModelGeometry, pano_id: str) -> Pano:
    for p in geometry.panos:
        if p.id == pano_id:
            return p
    raise ValueError(f"unknown pano {pano_id!r}")


def _room(geometry: ModelGeometry, room_id: str | None) -> Room | None:
    return next((r for r in geometry.rooms if r.id == room_id), None)


def _summary(text: str) -> str:
    return text if len(text) <= 200 else text[:197] + "..."


def _px(image: bytes) -> int:
    with Image.open(io.BytesIO(image)) as im:
        return max(im.size)


def _log_error(sid: str, record: dict) -> None:
    path = store.audit_path(sid, "vision_errors.jsonl")
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ---------- observation building (8.3.4) ----------

def build_attrs(label: str, values: dict[str, Any], obs_id: str) -> dict[str, Attr]:
    attrs: dict[str, Attr] = {}
    for key in ATTR_ORDER.get(label, []):
        if (label, key) in NON_VISUAL:
            attrs[key] = Attr(value=None, source="needs_verification", note=NON_VISUAL[(label, key)], evidence_obs_ids=[obs_id])
        elif key == "area_m2":
            w, h = values.get("width_m"), values.get("height_m")
            attrs[key] = (Attr(value=round(w * h, 1), source="visible_in_scan", note="width_m x height_m", evidence_obs_ids=[obs_id])
                          if w is not None and h is not None else
                          Attr(value=None, source="needs_verification", note="width or height not visible", evidence_obs_ids=[obs_id]))
        elif values.get(key) is None:
            attrs[key] = Attr(value=None, source="needs_verification", note="not clearly visible in image", evidence_obs_ids=[obs_id])
        else:
            note = "estimated from image" if key in ("width_m", "height_m") else ""
            attrs[key] = Attr(value=values[key], source="visible_in_scan", note=note, evidence_obs_ids=[obs_id])
    return attrs


def _make_observation(sid: str, geometry: ModelGeometry, pano: Pano, face: int, det: RawDetection, obs_id: str,
                      face_path, q, model_id: str) -> Observation:
    room = _room(geometry, pano.room_id)
    walls = geometry.walls if room is None else [w for w in geometry.walls if w.floor_id == room.floor_id]
    anchor, method = anchor_from_bbox(pano, face, det.bbox, 2048, walls, room)
    crop_ref = f"crops/{obs_id}.jpg"
    store.audit_path(sid, "crops", f"{obs_id}.jpg").write_bytes(crop(face_path, det.bbox))
    return Observation(id=obs_id, pano_id=pano.id, face=face, resolution="2k", face_px=2048, bbox=det.bbox,
                       label=det.label, attrs=build_attrs(det.label, det.attrs, obs_id), model_id=model_id,
                       model_tier="small", escalated=False, crop_ref=crop_ref, anchor=anchor, anchor_method=method,
                       room_id=room_for(geometry, pano, anchor), quality=q, created_at=now_iso())


def _detect_face(sid: str, face_path, model_id: str) -> tuple[dict | None, ModelCall, str]:
    image = downscale(face_path, detect_px(model_id))
    side = _px(image)
    return call_vision(model_id, image, detect_prompt(side, side), sid, "walker", "detect", "small", image_px=side)


# ---------- inspect_view ----------

def inspect_view(sid: str, geometry: ModelGeometry, room_id: str | None, pano_id: str) -> InspectResult:
    if _fixture_mode():
        return fixture.inspect_view(sid, geometry, room_id, pano_id)
    pano = _pano(geometry, pano_id)
    model_id = config.SMALL_VISION_MODEL_ID
    state = load_state(sid)
    accepted: list[tuple[int, Any, Any]] = []
    rejected: list[int] = []

    def reject(face: int, reason: str) -> None:
        rejected.append(face)
        state.rejected_faces.append(RejectedFace(pano_id=pano_id, face=face, reason=reason))

    for face in FACES:
        try:
            path = get_face_image(sid, pano_id, face, "2k")
        except UpstreamError as exc:
            if exc.code == "upstream_auth":
                raise
            reject(face, "image unavailable")
            continue
        q = quality(path)
        if q.accepted:
            accepted.append((face, path, q))
        else:
            reject(face, rejection_reason(q))

    def work(item):
        face, path, _ = item
        try:
            return _detect_face(sid, path, model_id)
        except UpstreamError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(work, accepted))  # map keeps face order, so ids are deterministic

    calls: list[ModelCall] = []
    inspected: list[int] = []
    per_face: list[tuple[int, Any, Any, list[RawDetection]]] = []
    for (face, path, q), outcome in zip(accepted, outcomes):
        if isinstance(outcome, UpstreamError):
            state.consecutive_failures += 1
            reject(face, "vision model call failed")
            if state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                save_state(sid, state)
                log_calls(sid, calls)
                raise UpstreamError("bedrock", True, f"{MAX_CONSECUTIVE_FAILURES} consecutive vision calls failed: {outcome.message}")
            continue
        state.consecutive_failures = 0
        raw, call, text = outcome
        calls.append(call)
        inspected.append(face)
        if raw is None:
            _log_error(sid, {"pano_id": pano_id, "face": face, "error": "unparseable model output", "raw": text[:4000]})
            dets: list[RawDetection] = []
        elif not image_ok(raw):
            dets = []
        else:
            dets = parse_detections(raw, call.image_px or DETECT_PX, 2048)
        per_face.append((face, path, q, dets))

    total = sum(len(d) for *_, d in per_face)
    with lock(sid):
        ids = iter(next_observation_ids(sid, total))
        observations = [_make_observation(sid, geometry, pano, face, det, next(ids), path, q, model_id)
                        for face, path, q, dets in per_face for det in dets]
        state = _merge_state(sid, state, pano_id, inspected)
        save_state(sid, state)
    log_calls(sid, calls)
    return InspectResult(observations=observations, faces_inspected=inspected, faces_rejected=rejected, calls=len(calls))


def _merge_state(sid: str, local: RouterState, pano_id: str, inspected: list[int]) -> RouterState:
    """Re-read the stored state and add this inspection's bookkeeping (resolve may have saved meanwhile)."""
    stored = load_state(sid)
    known = {(r.pano_id, r.face) for r in stored.rejected_faces}
    stored.rejected_faces += [r for r in local.rejected_faces if (r.pano_id, r.face) not in known]
    stored.inspected[pano_id] = sorted(set(stored.inspected.get(pano_id, [])) | set(inspected))
    stored.consecutive_failures = local.consecutive_failures
    return stored


# ---------- resolve (router driver, Appendix H.3) ----------

_hard_labels_cache: set[str] | None = None


def hard_labels() -> set[str]:
    """HARD_LABELS from eval/hard_labels.json, written by the benchmark. Empty until it runs."""
    global _hard_labels_cache
    if _hard_labels_cache is None:
        path = config.REPO_ROOT / "eval" / "hard_labels.json"
        try:
            _hard_labels_cache = set(json.loads(path.read_text(encoding="utf-8")).get("hard_labels", []))
        except (OSError, ValueError):
            _hard_labels_cache = set()
    return _hard_labels_cache


def _quality_issue(obs: Observation) -> bool:
    # quality.accepted applies the full rule from images.quality (low blur alone is not an issue:
    # sharp photos of plain walls score low), plus the brightness range.
    q = obs.quality
    return not q.accepted or not BRIGHTNESS_MIN <= q.brightness <= BRIGHTNESS_MAX


def _disagrees(obs: Observation, others: list[Observation]) -> bool:
    for other in others:
        if not same_object(obs, other):
            continue
        for key, attr in obs.attrs.items():
            theirs = other.attrs.get(key)
            if attr.value is not None and theirs is not None and theirs.value is not None and theirs.value != attr.value:
                return True
    return False


def compute_signals(obs: Observation, all_obs: list[Observation], state: RouterState, geometry: ModelGeometry) -> Signals:
    key = KEY_ATTR.get(obs.label)
    pair = [obs.label, key] if key else None
    return Signals(
        quality_issue=_quality_issue(obs),
        key_unknown=key_unknown(obs),
        disagreement=_disagrees(obs, [o for o in all_obs if o.id != obs.id]),
        hard_label=obs.label in hard_labels(),
        neighbor_exists=neighbor_pano(geometry, obs, set()) is not None,
        user_answerable=key in USER_ANSWERABLE,
        escalation_failed=pair in state.escalation_failed,
        asked=pair in state.asked,
        large_cap_reached=state.large_calls >= MAX_LARGE_CALLS_PER_AUDIT,
    )


def _update_attrs(obs: Observation, values: dict[str, Any], unknown_note: str) -> Observation:
    """Write non-null values from a re-read; leave the rest, noting why they are still unknown."""
    new = obs.model_copy(deep=True)
    for key, value in values.items():
        if value is not None:
            note = "estimated from image" if key in ("width_m", "height_m") else ""
            new.attrs[key] = Attr(value=value, source="visible_in_scan", note=note, evidence_obs_ids=[obs.id])
        elif key in new.attrs and new.attrs[key].value is None:
            new.attrs[key] = new.attrs[key].model_copy(update={"note": unknown_note})
    w, h = new.attrs.get("width_m"), new.attrs.get("height_m")
    if obs.label == "window" and w and h and w.value is not None and h.value is not None:
        new.attrs["area_m2"] = Attr(value=round(float(w.value) * float(h.value), 1), source="visible_in_scan",
                                    note="width_m x height_m", evidence_obs_ids=[obs.id])
    return new


def _bbox_4k(obs: Observation) -> BBox:
    if obs.face_px == 4096:
        return obs.bbox
    b = obs.bbox
    return BBox(x0=min(b.x0 * 2, 4095), y0=min(b.y0 * 2, 4095), x1=min(b.x1 * 2, 4096), y1=min(b.y1 * 2, 4096))


def _reread(sid: str, obs: Observation, tier: str) -> tuple[dict[str, Any], ModelCall, BBox, bytes]:
    """Attribute read on a 4k crop of the observation's box (plan 8.5)."""
    model_id = config.SMALL_VISION_MODEL_ID if tier == "small" else config.LARGE_VISION_MODEL_ID
    path = get_face_image(sid, obs.pano_id, obs.face, "4k")
    bbox = _bbox_4k(obs)
    image = crop(path, bbox)
    raw, call, text = call_vision(model_id, image, attr_prompt(obs.label), sid, "walker", "attr", tier, image_px=_px(image))
    if raw is None:
        _log_error(sid, {"observation_id": obs.id, "error": "unparseable attribute output", "raw": text[:4000]})
    return parse_attrs(raw, obs.label), call, bbox, image


def _do_hires(sid: str, obs: Observation) -> ResolveResult:
    values, call, bbox, image = _reread(sid, obs, "small")
    log_calls(sid, [call])
    new = _update_attrs(obs, values, "not clearly visible; high-res crop did not resolve")
    new = new.model_copy(update={"resolution": "4k", "face_px": 4096, "bbox": bbox})
    store.audit_path(sid, "crops", f"{obs.id}.jpg").write_bytes(image)  # sharper evidence crop
    key = KEY_ATTR.get(obs.label)
    outcome = "resolved" if key and new.attrs[key].value is not None else "still unknown"
    return ResolveResult(observation_id=obs.id, action="hires_crop", observation=new, final=False,
                         summary=_summary(f"{obs.id} high-res crop (small model): {key or 'attributes'} {outcome}"))


def _do_escalate(sid: str, obs: Observation, state: RouterState) -> ResolveResult:
    values, call, bbox, image = _reread(sid, obs, "large")
    log_calls(sid, [call])
    state.large_calls += 1
    new = _update_attrs(obs, values, "unresolved after high-res crop and large model")
    new = new.model_copy(update={"model_id": config.LARGE_VISION_MODEL_ID, "model_tier": "large", "escalated": True,
                                 "resolution": "4k", "face_px": 4096, "bbox": bbox})
    key = KEY_ATTR.get(obs.label)
    if key and new.attrs.get(key) is not None and new.attrs[key].value is None:
        if [obs.label, key] not in state.escalation_failed:
            state.escalation_failed.append([obs.label, key])
    outcome = "resolved" if key and new.attrs[key].value is not None else "still unknown"
    return ResolveResult(observation_id=obs.id, action="escalate_large", observation=new, final=False,
                         summary=_summary(f"{obs.id} escalated to large model: {key or 'attributes'} {outcome}"))


def _do_neighbor(sid: str, geometry: ModelGeometry, obs: Observation) -> ResolveResult:
    nb = neighbor_pano(geometry, obs, set())
    if nb is None:
        return ResolveResult(observation_id=obs.id, action="neighbor_view", final=False,
                             summary=_summary(f"{obs.id}: no neighbor panorama available"))
    target = obs.anchor or _pano(geometry, obs.pano_id).position
    face = face_toward(nb, target.x, target.y)
    path = get_face_image(sid, nb.id, face, "2k")
    q = quality(path)
    if not q.accepted:
        return ResolveResult(observation_id=obs.id, action="neighbor_view", final=False,
                             summary=_summary(f"{obs.id}: neighbor {nb.id} face {face} rejected ({rejection_reason(q)})"))
    raw, call, _ = _detect_face(sid, path, config.SMALL_VISION_MODEL_ID)
    log_calls(sid, [call])
    dets = [d for d in parse_detections(raw, call.image_px or DETECT_PX, 2048) if d.label == obs.label]
    best, best_d = None, None
    room = _room(geometry, nb.room_id)
    walls = geometry.walls if room is None else [w for w in geometry.walls if w.floor_id == room.floor_id]
    for det in dets:
        anchor, _method = anchor_from_bbox(nb, face, det.bbox, 2048, walls, room)
        if obs.anchor is not None and anchor is not None:
            d = ((anchor.x - obs.anchor.x) ** 2 + (anchor.y - obs.anchor.y) ** 2 + (anchor.z - obs.anchor.z) ** 2) ** 0.5
            if d >= THRESHOLD_M.get(obs.label, 0.5):
                continue
        else:
            d = 0.0  # no anchors to compare: same label in the neighbor's view is the best we can do
        if best_d is None or d < best_d:
            best, best_d = det, d
    if best is None:
        return ResolveResult(observation_id=obs.id, action="neighbor_view", final=False,
                             summary=_summary(f"{obs.id}: neighbor {nb.id} did not see the {obs.label.replace('_', ' ')}"))
    with lock(sid):
        (new_id,) = next_observation_ids(sid, 1)
        new_obs = _make_observation(sid, geometry, nb, face, best, new_id, path, q, config.SMALL_VISION_MODEL_ID)
    updated = obs.model_copy(deep=True)
    for key, attr in new_obs.attrs.items():
        mine = updated.attrs.get(key)
        if attr.value is not None and mine is not None and mine.value is None and (obs.label, key) not in NON_VISUAL:
            updated.attrs[key] = Attr(value=attr.value, source="visible_in_scan", note=f"from neighbor view {nb.id}",
                                      evidence_obs_ids=[obs.id, new_id])
    return ResolveResult(observation_id=obs.id, action="neighbor_view", observation=updated, new_observations=[new_obs],
                         final=False, summary=_summary(f"{obs.id}: neighbor view {nb.id} face {face} -> {new_id}"))


def ask_and_apply(sid: str, geometry: ModelGeometry, obs: Observation, all_obs: list[Observation],
                  state: RouterState, ask: AskFn) -> ResolveResult:
    key = KEY_ATTR[obs.label]
    q = make_question(next_question_id(sid), obs, all_obs, geometry)
    if [obs.label, key] not in state.asked:
        state.asked.append([obs.label, key])
    save_state(sid, state)
    try:
        answer = ask(q)
    except Exception:  # a failing callback must not stall the audit; treat it as a timeout
        answer = None
    updated, q = apply_answer(obs, q, answer)
    word = f"answered '{q.answer}'" if q.status == "answered" else "expired without an answer"
    return ResolveResult(observation_id=obs.id, action="ask_user", observation=updated, question=q, final=False,
                         summary=_summary(f"Question {q.question_id} {word}"))


def resolve(sid: str, geometry: ModelGeometry, observation_id: str, ask: AskFn) -> ResolveResult:
    if _fixture_mode():
        return fixture.resolve(sid, geometry, observation_id, ask)
    with lock(sid):
        state = load_state(sid)
        all_obs = store.observations(sid)
        obs = next((o for o in all_obs if o.id == observation_id), None)
        if obs is None:
            raise ValueError(f"unknown observation {observation_id!r}")
        if obs.id in state.final:
            return ResolveResult(observation_id=obs.id, action="accept", final=True, summary=f"{obs.id} already final")
        action = next_action(obs, state, compute_signals(obs, all_obs, state, geometry))
        state.tried.setdefault(obs.id, []).append(action)
        save_state(sid, state)

    if action == "accept":
        result = ResolveResult(observation_id=obs.id, action=action, final=True, summary=f"{obs.id} accepted")
    elif action == "leave_unknown":
        key = KEY_ATTR.get(obs.label)
        result = ResolveResult(observation_id=obs.id, action=action, final=True,
                               summary=_summary(f"{obs.id} left unknown ({key or 'attributes'} needs verification)"))
    elif action == "hires_crop":
        result = _do_hires(sid, obs)
    elif action == "neighbor_view":
        result = _do_neighbor(sid, geometry, obs)
    elif action == "escalate_large":
        result = _do_escalate(sid, obs, state)
    else:  # ask_user
        result = ask_and_apply(sid, geometry, obs, all_obs, state, ask)

    with lock(sid):
        stored = load_state(sid)
        stored.large_calls = max(stored.large_calls, state.large_calls)
        for pair in state.escalation_failed:
            if pair not in stored.escalation_failed:
                stored.escalation_failed.append(pair)
        if action in FINAL_ACTIONS and obs.id not in stored.final:
            stored.final.append(obs.id)
        save_state(sid, stored)
    return result


# ---------- helpers for Person 3's agent ----------

def pending_observation_ids(sid: str) -> list[str]:
    """Observations that resolve has not finalized, lowest id first (what resolve_next walks)."""
    final = set(load_state(sid).final)
    from ..inventory import id_key
    return [o.id for o in sorted(store.observations(sid), key=lambda o: id_key(o.id)) if o.id not in final]


def coverage_inputs(sid: str, geometry: ModelGeometry) -> tuple[dict[str, list[str]], int, dict[str, str]]:
    """(reviewed, faces_rejected, partial_rooms) for inventory.compute_coverage, from router_state.json."""
    state = load_state(sid)
    touched = set(state.inspected) | {r.pano_id for r in state.rejected_faces}
    reviewed: dict[str, list[str]] = {}
    partial: dict[str, str] = {}
    for room in geometry.rooms:
        panos = [p for p in room.pano_ids if p in touched]
        if panos:
            reviewed[room.id] = panos
        rejected = [r for r in state.rejected_faces if r.pano_id in panos]
        if not rejected:
            continue
        clean = [p for p in panos if p not in {r.pano_id for r in rejected} and state.inspected.get(p)]
        if clean:
            continue  # another inspected panorama in the room covers it
        reasons = ", ".join(r.reason for r in rejected)
        n_faces = 4 * len({r.pano_id for r in rejected})
        tail = "no other panorama inside this room" if len(room.pano_ids) <= 1 else "no other inspected panorama in this room"
        partial[room.id] = f"{len(rejected)} of {n_faces} faces rejected as {reasons}; {tail}"
    return reviewed, len(state.rejected_faces), partial
