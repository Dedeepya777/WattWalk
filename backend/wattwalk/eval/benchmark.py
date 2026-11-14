"""Adaptive-routing benchmark (plan 14). Owner: Person 2.

    python -m wattwalk.eval.benchmark --labels eval/labels.csv [--face-labels eval/face_labels.csv]
                                      [--labeled-by "Person 2"] [--out eval/results.json]

Compares small_only, large_only and adaptive (small first, large when the key attribute stays
unknown or the label is hard) on hand-labeled crops. The LLM cache is disabled for the measured run.
Labels must be written by a person, never by a model.

Inputs (crops and faces stay local and are never committed):
- eval/labels.csv: crop_id, sid, pano_id, face, label, bulb_type, thermostat_type, shading, notes
- eval/face_labels.csv: sid, pano_id, face, labels (semicolon list of ground-truth labels in that face)
- eval/crops/<crop_id>.jpg, and faces from Person 1's adapter or eval/faces/<sid>_<pano>_<face>.jpg
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .. import config
from ..contracts import Benchmark, BenchmarkDataset, BenchmarkMode, ModelCall
from ..vision.prompts import KEY_ATTR

EVAL_DIR = config.REPO_ROOT / "eval"
HARD_GAP = 0.15  # small-model attribute accuracy at least this much below large marks a label hard (8.4.1)


@dataclass(frozen=True)
class CropLabel:
    crop_id: str
    sid: str
    pano_id: str
    face: int
    label: str
    key_value: Optional[str]  # ground truth for the label's key attribute; None = "unknown" to a careful human

    @property
    def key_attr(self) -> Optional[str]:
        return KEY_ATTR.get(self.label)


def _norm(value: str | None) -> Optional[str]:
    v = (value or "").strip().lower()
    return None if v in ("", "unknown") else v


def load_labels(path: Path) -> list[CropLabel]:
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            label = r["label"].strip()
            key = KEY_ATTR.get(label)
            rows.append(CropLabel(r["crop_id"].strip(), r["sid"].strip(), r["pano_id"].strip(), int(r["face"]),
                                  label, _norm(r.get(key, "")) if key else None))
    return rows


def load_face_labels(path: Path) -> dict[tuple[str, str, int], list[str]]:
    faces = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            labels = [x.strip() for x in (r["labels"] or "").split(";") if x.strip()]
            faces[(r["sid"].strip(), r["pano_id"].strip(), int(r["face"]))] = labels
    return faces


# ---------- metrics (pure; unit tested) ----------

def detection_metrics(pred: dict[tuple, list[str]], truth: dict[tuple, list[str]]) -> tuple[float, float]:
    """Per-face multiset matching of labels, micro-averaged. Returns (precision, recall)."""
    correct = predicted = actual = 0
    for face, gt in truth.items():
        p, t = Counter(pred.get(face, [])), Counter(gt)
        correct += sum((p & t).values())
        predicted += sum(p.values())
        actual += sum(t.values())
    precision = correct / predicted if predicted else 0.0
    recall = correct / actual if actual else 0.0
    return round(precision, 3), round(recall, 3)


def attr_metrics(pairs: list[tuple[Optional[str], Optional[str]]]) -> tuple[float, int, int]:
    """pairs of (truth, prediction), None meaning unknown. Returns (accuracy, correct_abstentions, unsupported_claims)."""
    known = [(t, p) for t, p in pairs if t is not None]
    accuracy = sum(1 for t, p in known if p == t) / len(known) if known else 0.0
    abstentions = sum(1 for t, p in pairs if t is None and p is None)
    unsupported = sum(1 for t, p in pairs if t is None and p is not None)
    return round(accuracy, 3), abstentions, unsupported


def per_label_accuracy(crops: list[CropLabel], preds: dict[str, Optional[str]]) -> dict[str, float]:
    by_label: dict[str, list[tuple]] = {}
    for c in crops:
        if c.key_attr and c.key_value is not None:
            by_label.setdefault(c.label, []).append((c.key_value, preds.get(c.crop_id)))
    return {label: sum(1 for t, p in pairs if t == p) / len(pairs) for label, pairs in by_label.items()}


def hard_labels(small_acc: dict[str, float], large_acc: dict[str, float]) -> list[str]:
    return sorted(l for l in small_acc if l in large_acc and small_acc[l] <= large_acc[l] - HARD_GAP)


def summarize(mode: str, precision: float, recall: float, attr: tuple[float, int, int], escalations: int,
              n_attr: int, calls: list[ModelCall]) -> BenchmarkMode:
    tin = [c.tokens_in for c in calls if c.tokens_in is not None]
    tout = [c.tokens_out for c in calls if c.tokens_out is not None]
    return BenchmarkMode(
        mode=mode, detection_precision=precision, detection_recall=recall,
        attr_accuracy=attr[0], correct_abstentions=attr[1], unsupported_claims=attr[2],
        escalation_rate=round(escalations / n_attr, 3) if mode == "adaptive" and n_attr else 0.0,
        calls=len(calls), tokens_in=sum(tin) if tin else None, tokens_out=sum(tout) if tout else None,
        latency_ms_p50=int(statistics.median(c.latency_ms for c in calls)) if calls else 0,
        cache_hits=sum(1 for c in calls if c.cache_hit))


# ---------- running the three modes ----------

DetectFn = Callable[[str, tuple[str, str, int]], tuple[list[str], ModelCall]]
ReadFn = Callable[[str, CropLabel], tuple[Optional[str], ModelCall]]


def run_modes(crops: list[CropLabel], faces: dict[tuple, list[str]], detect: DetectFn, read: ReadFn,
              hard: set[str] = frozenset()) -> tuple[list[BenchmarkMode], dict[str, dict[str, Optional[str]]]]:
    """Run small_only, large_only and adaptive. detect(tier, face) and read(tier, crop) do the model calls."""
    attr_crops = [c for c in crops if c.key_attr]
    modes, preds_by_mode = [], {}
    for mode in ("small_only", "large_only", "adaptive"):
        calls: list[ModelCall] = []
        det_tier = "large" if mode == "large_only" else "small"
        pred_faces = {}
        for face in faces:
            labels, call = detect(det_tier, face)
            pred_faces[face] = labels
            calls.append(call)
        preds: dict[str, Optional[str]] = {}
        escalations = 0
        for c in attr_crops:
            value, call = read("large" if mode == "large_only" else "small", c)
            calls.append(call)
            if mode == "adaptive" and (value is None or c.label in hard):
                value, call = read("large", c)
                calls.append(call)
                escalations += 1
            preds[c.crop_id] = value
        precision, recall = detection_metrics(pred_faces, faces)
        attr = attr_metrics([(c.key_value, preds[c.crop_id]) for c in attr_crops])
        modes.append(summarize(mode, precision, recall, attr, escalations, len(attr_crops), calls))
        preds_by_mode[mode] = preds
    return modes, preds_by_mode


def _bedrock_fns():
    """Real model calls with the cache disabled."""
    from ..data.matterport import get_face_image
    from ..vision.detect import call_vision, detect_px, parse_attrs, parse_detections
    from ..vision.images import downscale
    from ..vision.prompts import attr_prompt, detect_prompt

    def model(tier: str) -> str:
        return config.SMALL_VISION_MODEL_ID if tier == "small" else config.LARGE_VISION_MODEL_ID

    def face_path(face: tuple[str, str, int]) -> Path:
        sid, pano, f = face
        local = EVAL_DIR / "faces" / f"{sid}_{pano}_{f}.jpg"
        return local if local.exists() else get_face_image(sid, pano, f, "2k")

    def detect(tier, face):
        px = detect_px(model(tier))
        image = downscale(face_path(face), px)
        raw, call, _ = call_vision(model(tier), image, detect_prompt(px, px), "benchmark", "benchmark", "detect",
                                   tier, image_px=px, use_cache=False)
        return [d.label for d in parse_detections(raw, px, 2048)], call

    def read(tier, crop: CropLabel):
        image = (EVAL_DIR / "crops" / f"{crop.crop_id}.jpg").read_bytes()
        raw, call, _ = call_vision(model(tier), image, attr_prompt(crop.label), "benchmark", "benchmark", "attr",
                                   tier, use_cache=False)
        return parse_attrs(raw, crop.label).get(crop.key_attr), call

    return detect, read


def run(labels_csv: Path, face_labels_csv: Path | None = None, labeled_by: str = "Person 2") -> Benchmark:
    crops = load_labels(labels_csv)
    faces = load_face_labels(face_labels_csv or EVAL_DIR / "face_labels.csv")
    detect, read = _bedrock_fns()
    modes, preds = run_modes(crops, faces, detect, read)
    hard = hard_labels(per_label_accuracy(crops, preds["small_only"]), per_label_accuracy(crops, preds["large_only"]))
    (EVAL_DIR / "hard_labels.json").write_text(json.dumps({"hard_labels": hard}, indent=2), encoding="utf-8")
    apartments = len({c.sid for c in crops})
    return Benchmark(
        status="measured",
        dataset=BenchmarkDataset(n_images=len(crops), labeled_by=labeled_by,
                                 created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        modes=modes,
        notes=[f"{len(crops)} hand-labeled crops from {apartments} apartments; {len(faces)} faces for detection.",
               "LLM cache disabled for this run.",
               "Adaptive used an empty HARD_LABELS set; labels marked hard by this run: " + (", ".join(hard) or "none") + ".",
               "Token counts are compute proxies, not energy measurements."])


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m wattwalk.eval.benchmark")
    p.add_argument("--labels", type=Path, default=EVAL_DIR / "labels.csv")
    p.add_argument("--face-labels", type=Path, default=EVAL_DIR / "face_labels.csv")
    p.add_argument("--labeled-by", default="Person 2")
    p.add_argument("--out", type=Path, default=EVAL_DIR / "results.json")
    args = p.parse_args(argv)
    result = run(args.labels, args.face_labels, args.labeled_by)
    args.out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    for m in result.modes:
        print(f"{m.mode:11} precision {m.detection_precision} recall {m.detection_recall} attr {m.attr_accuracy} "
              f"calls {m.calls} escalation {m.escalation_rate}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
