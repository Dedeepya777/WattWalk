"""Shared test fixtures. Each test gets its own empty audits folder, so tests never touch real audits."""
from __future__ import annotations

import json
import os

# Tests must not depend on the developer's .env (live modes, Deep Agents, real keys would make them
# call Matterport or a model). config loads .env with load_dotenv, which never overrides variables
# that are already set, so pinning them here before importing wattwalk keeps every run offline.
_OFFLINE_ENV = {
    "WATTWALK_DATA_MODE": "fixture",
    "WATTWALK_VISION_MODE": "fixture",
    "WATTWALK_AGENT_MODE": "scripted",
    "WATTWALK_SMALL_VISION_MODEL_ID": "",
    "WATTWALK_LARGE_VISION_MODEL_ID": "",
    "WATTWALK_PLANNER_MODEL_ID": "",
    "MATTERPORT_API_KEY": "",
    "MATTERPORT_API_TOKEN": "",
    "VEXCEL_API_KEY": "",
    "GOOGLE_API_KEY": "",
    "COSTAR_KIT_ZIP": "",
}
os.environ.update(_OFFLINE_ENV)

import pytest  # noqa: E402

from wattwalk import config  # noqa: E402
from wattwalk.contracts import ModelGeometry, Observation  # noqa: E402
from wattwalk.vision import state as vision_state  # noqa: E402
from wattwalk.vision import walk  # noqa: E402


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
