"""Shared test fixtures. Each test gets its own empty audits folder, so tests never touch real audits."""
from __future__ import annotations

import json

import pytest

from wattwalk import config
from wattwalk.contracts import ModelGeometry, Observation
from wattwalk.vision import state as vision_state
from wattwalk.vision import walk


@pytest.fixture(autouse=True)
def audits_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUDITS_DIR", tmp_path / "audits")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "audits" / "cache")
    monkeypatch.setattr(config, "VISION_MODE", "fixture")
    vision_state._reserved_obs.clear()
    monkeypatch.setattr(walk, "_hard_labels_cache", set())
    return tmp_path / "audits"


def load_example(name: str):
    return json.loads((config.EXAMPLES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def geometry() -> ModelGeometry:
    return ModelGeometry.model_validate(load_example("model_geometry.json"))


@pytest.fixture
def fixture_observations() -> list[Observation]:
    return [Observation.model_validate(o) for o in load_example("observations.json")]
