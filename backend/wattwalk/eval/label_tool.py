"""Hand-labeling tool for benchmark crops (plan 14.2). Owner: Person 2.

    python -m wattwalk.eval.label_tool --sid <sid>

Shows each unlabeled crop from audits/<sid>/crops/ and asks you to type its label and key
attribute. Appends to eval/labels.csv with crop_id "<sid>_<observation id>" and copies the crop to
eval/crops/<crop_id>.jpg (gitignored). A person must do this; never fill labels with a model.
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


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m wattwalk.eval.label_tool")
    p.add_argument("--sid", required=True)
    p.add_argument("--out", type=Path, default=config.REPO_ROOT / "eval" / "labels.csv")
    args = p.parse_args(argv)

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
            print(f"\n{crop_id}" + (f" (model said {o.label})" if o else ""))
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
