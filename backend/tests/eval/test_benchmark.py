"""Benchmark metric tests (plan 14.4). The model calls are faked; real numbers come from a labeled run."""
from __future__ import annotations

from wattwalk.contracts import Benchmark, ModelCall
from wattwalk.eval.benchmark import (CropLabel, attr_metrics, detection_metrics, hard_labels, load_labels,
                                     per_label_accuracy, run_modes)


def test_detection_metrics_multiset():
    truth = {"f1": ["window", "ceiling_light", "ceiling_light"], "f2": ["refrigerator"]}
    pred = {"f1": ["window", "ceiling_light", "lamp"], "f2": []}
    assert detection_metrics(pred, truth) == (round(2 / 3, 3), 0.5)


def test_attr_metrics_counts_abstentions_and_claims():
    pairs = [("led", "led"), ("led", None), ("cfl", "led"), (None, None), (None, "incandescent")]
    assert attr_metrics(pairs) == (round(1 / 3, 3), 1, 1)


def test_hard_labels_gap():
    assert hard_labels({"lamp": 0.5, "window": 0.9}, {"lamp": 0.7, "window": 0.95}) == ["lamp"]


def test_load_labels(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text("crop_id,sid,pano_id,face,label,bulb_type,thermostat_type,shading,notes\n"
                    "s_o001,s,p1,2,ceiling_light,unknown,,,\n"
                    "s_o002,s,p1,3,window,,,blinds,\n"
                    "s_o003,s,p1,3,range_gas,,,,\n")
    rows = load_labels(path)
    assert [(r.label, r.key_value) for r in rows] == [("ceiling_light", None), ("window", "blinds"), ("range_gas", None)]
    assert rows[2].key_attr is None


def _call(tier):
    return ModelCall(id="c000", agent="benchmark", kind="attr", model_id=tier, model_tier=tier,
                     tokens_in=100 if tier == "small" else 400, tokens_out=10, latency_ms=900 if tier == "small" else 3000,
                     cache_hit=False, at="2026-11-14T10:00:00Z")


def test_run_modes_adaptive_escalates_only_unknowns():
    crops = [CropLabel("a", "s", "p", 1, "ceiling_light", "led"), CropLabel("b", "s", "p", 1, "ceiling_light", "cfl"),
             CropLabel("c", "s", "p", 2, "window", "blinds")]
    faces = {("s", "p", 1): ["ceiling_light", "ceiling_light"], ("s", "p", 2): ["window"]}
    small = {"a": "led", "b": None, "c": "blinds"}
    large = {"a": "led", "b": "cfl", "c": "blinds"}

    def detect(tier, face):
        return list(faces[face]), _call(tier)

    def read(tier, crop):
        return (small if tier == "small" else large)[crop.crop_id], _call(tier)

    modes, preds = run_modes(crops, faces, detect, read)
    by = {m.mode: m for m in modes}
    assert by["small_only"].attr_accuracy == round(2 / 3, 3) and by["large_only"].attr_accuracy == 1.0
    assert by["adaptive"].attr_accuracy == 1.0 and by["adaptive"].escalation_rate == round(1 / 3, 3)
    assert by["adaptive"].calls == 2 + 3 + 1 and by["large_only"].calls == 5
    assert by["small_only"].escalation_rate == 0.0
    assert per_label_accuracy(crops, preds["small_only"]) == {"ceiling_light": 0.5, "window": 1.0}
    bench = Benchmark(status="measured", dataset={"n_images": 3, "labeled_by": "test"}, modes=modes, notes=[])
    assert bench.modes[2].mode == "adaptive"  # validates against the contract


def test_label_faces_writes_csv_and_copies_face(tmp_path, monkeypatch):
    import csv as _csv

    from PIL import Image

    from wattwalk import config
    from wattwalk.eval import label_tool

    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    face_dir = config.CACHE_DIR / "faces" / "sidA"
    face_dir.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(face_dir / "p1_2_2k.jpg")
    labels = tmp_path / "labels.csv"
    labels.write_text("crop_id,sid,pano_id,face,label,bulb_type,thermostat_type,shading,notes\n"
                      "sidA_o1,sidA,p1,2,window,,,blinds,\nsidA_o2,sidA,p1,2,lamp,led,,,\n")
    monkeypatch.setattr(Image.Image, "show", lambda self: None)
    answers = iter(["window; lamp ; sofa", "window;lamp"])  # first answer has a non-vocabulary label
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    out = tmp_path / "face_labels.csv"
    label_tool.label_faces(labels, out)
    rows = list(_csv.DictReader(out.open()))
    assert rows == [{"sid": "sidA", "pano_id": "p1", "face": "2", "labels": "window;lamp"}]  # one face, asked once
    assert (tmp_path / "eval" / "faces" / "sidA_p1_2.jpg").exists()


def test_benchmark_cli_accepts_plan_flags_and_model_overrides(monkeypatch):
    from wattwalk.eval import benchmark

    seen = {}

    def fake_run(labels, faces, labeled_by, small, large):
        seen.update(faces=faces.name, small=small, large=large)
        raise SystemExit(0)

    monkeypatch.setattr(benchmark, "run", fake_run)
    try:
        benchmark.main(["--labels", "eval/labels.csv", "--faces", "eval/face_labels.csv", "--no-cache",
                        "--small-model", "ollama/qwen2.5vl:3b", "--large-model", "ollama/qwen2.5vl:7b"])
    except SystemExit:
        pass
    assert seen == {"faces": "face_labels.csv", "small": "ollama/qwen2.5vl:3b", "large": "ollama/qwen2.5vl:7b"}
