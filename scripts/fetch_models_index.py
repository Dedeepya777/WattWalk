"""Fetch the full hackathon models index CSV from Matterport quickstart.

Owner: Person 1.
Usage:
    python scripts/fetch_models_index.py
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_INDEX_URL = "https://static.matterport.com/hackathon/26.15.35-main-35-g24e0220/assets/quickstart/models_index.csv"
OUTPUT_FILE = REPO_ROOT / "fixtures" / "models_index.csv"


def fetch_models_index(url: str = MODELS_INDEX_URL, out_path: Path = OUTPUT_FILE) -> int:
    """Download full models index CSV and save to fixtures/models_index.csv."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WattWalk/1.0"}
    print(f"Downloading models index from {url}...")
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()

    # Parse rows to count and validate CSV
    content = resp.text
    reader = csv.reader(io.StringIO(content))
    header = next(reader)
    rows = list(reader)
    row_count = len(rows)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"Saved {row_count} rows to {out_path}")
    return row_count


def main() -> None:
    try:
        count = fetch_models_index()
        print(f"Success! Models index updated with {count} rows.")
    except Exception as exc:
        print(f"Error fetching models index: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
