"""Hand-labeling tool for benchmark crops (plan 14.2). Owner: Person 2.

    python -m wattwalk.eval.label_tool --sid <sid>            # step 1: label crops, one apartment at a time
    python -m wattwalk.eval.label_tool --faces                # step 2: label the full faces those crops came from

Step 1 shows each unlabeled crop from audits/<sid>/crops/ and asks for its label and key attribute.
Appends to eval/labels.csv with crop_id "<sid>_<observation id>" and copies the crop to
eval/crops/<crop_id>.jpg (gitignored). The model's guess is hidden by default (seeing it biases the
labeler toward agreeing); --show-guess shows it.
Step 2 shows each full face referenced by labels.csv and asks for every vocabulary object visible in
it (semicolon list, empty for none). Appends to eval/face_labels.csv and copies the face to
eval/faces/ (gitignored) so the benchmark needs no network. A person must do this; never a model.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

from PIL import Image

from .. import config, store
from ..contracts import ASSET_LABELS
from ..vision.prompts import KEY_ATTR, VOCAB

COLUMNS = ["crop_id", "sid", "pano_id", "face", "label", "bulb_type", "thermostat_type", "shading", "notes"]


def _ask(prompt: str, allowed: list[str]) -> str:
    while True:
        value = input(f"{prompt} [{' | '.join(allowed)}]: ").strip().lower()
        if value in allowed:
            return value
        print("  not one of the allowed values")


FACE_COLUMNS = ["sid", "pano_id", "face", "labels"]


def _ask_labels(prompt: str) -> str:
    while True:
        raw = input(f"{prompt} (semicolon list from: {', '.join(ASSET_LABELS)}; empty for none): ").strip().lower()
        labels = [x.strip() for x in raw.split(";") if x.strip()]
        bad = [x for x in labels if x not in ASSET_LABELS]
        if not bad:
            return ";".join(labels)
        print(f"  not in the vocabulary: {', '.join(bad)}")


def label_faces(labels_csv: Path, out: Path) -> None:
    """Ground-truth labels for every full face that a labeled crop came from (plan 14.2)."""
    with labels_csv.open(newline="", encoding="utf-8") as f:
        faces = sorted({(r["sid"], r["pano_id"], r["face"]) for r in csv.DictReader(f) if r["pano_id"]})
    done = set()
    if out.exists():
        with out.open(newline="", encoding="utf-8") as f:
            done = {(r["sid"], r["pano_id"], r["face"]) for r in csv.DictReader(f)}
    eval_faces = config.REPO_ROOT / "eval" / "faces"
    eval_faces.mkdir(parents=True, exist_ok=True)
    new_file = not out.exists()
    with out.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FACE_COLUMNS)
        if new_file:
            writer.writeheader()
        for sid, pano, face in faces:
            if (sid, pano, face) in done:
                continue
            src = config.CACHE_DIR / "faces" / sid / f"{pano}_{face}_2k.jpg"
            if not src.exists():
                print(f"skip {sid} {pano} face {face}: no cached face at {src}")
                continue
            print(f"\n{sid} {pano} face {face}: list every object from the vocabulary you can see")
            Image.open(src).show()
            writer.writerow({"sid": sid, "pano_id": pano, "face": face, "labels": _ask_labels("labels")})
            shutil.copy(src, eval_faces / f"{sid}_{pano}_{face}.jpg")
            f.flush()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m wattwalk.eval.label_tool")
    p.add_argument("--sid", help="label the crops of this apartment's audit")
    p.add_argument("--faces", action="store_true", help="label the full faces referenced by labels.csv")
    p.add_argument("--show-guess", action="store_true", help="show the model's label (biases the labeler)")
    p.add_argument("--out", type=Path, default=config.REPO_ROOT / "eval" / "labels.csv")
    p.add_argument("--face-out", type=Path, default=config.REPO_ROOT / "eval" / "face_labels.csv")
    args = p.parse_args(argv)
    if args.faces:
        label_faces(args.out, args.face_out)
        return
    if not args.sid:
        p.error("give --sid <sid> to label crops, or --faces to label faces")

    done = set()
    if args.out.exists():
        with args.out.open(newline="", encoding="utf-8") as f:
            done = {r["crop_id"] for r in csv.DictReader(f)}
    obs = {o.id: o for o in store.observations(args.sid)}
    new_file = not args.out.exists()
    with args.out.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        eval_crops = config.REPO_ROOT / "eval" / "crops"
        eval_crops.mkdir(parents=True, exist_ok=True)
        for path in sorted(store.audit_path(args.sid, "crops", "x").parent.glob("*.jpg")):
            crop_id = f"{args.sid}_{path.stem}"
            if crop_id in done:
                continue
            o = obs.get(path.stem)
            print(f"\n{crop_id}" + (f" (model said {o.label})" if o and args.show_guess else ""))
            Image.open(path).show()
            label = _ask("label", list(ASSET_LABELS) + ["skip"])
            if label == "skip":
                continue
            row = {c: "" for c in COLUMNS}
            row.update(crop_id=crop_id, sid=args.sid, pano_id=o.pano_id if o else "", face=o.face if o else "", label=label)
            key = KEY_ATTR.get(label)
            if key:
                row[key] = _ask(key, list(VOCAB[label][key]) + ["unknown"])
            row["notes"] = input("notes (optional): ").strip()
            shutil.copy(path, eval_crops / f"{crop_id}.jpg")
            writer.writerow(row)
            f.flush()


if __name__ == "__main__":
    main()
