"""WattWalk settings. Owner: Person 3. Other modules read settings from here, never from os.environ directly."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is in requirements; this keeps check scripts usable without it
    load_dotenv = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if load_dotenv:
    load_dotenv(REPO_ROOT / ".env")


def _mode(name: str, default: str, allowed: set[str]) -> str:
    value = os.getenv(name, default) or default
    if value not in allowed:
        raise ValueError(f"{name}={value!r}; allowed: {sorted(allowed)}")
    return value


DATA_MODE = _mode("WATTWALK_DATA_MODE", "fixture", {"fixture", "live"})
VISION_MODE = _mode("WATTWALK_VISION_MODE", "fixture", {"fixture", "live"})
AGENT_MODE = _mode("WATTWALK_AGENT_MODE", "scripted", {"scripted", "deep_agents"})

# Per-run override. The agent run loop (Person 3) sets this for a run started with mode "fixture",
# so adapters use fixture data for that run regardless of the environment defaults.
import contextvars

RUN_MODE_OVERRIDE: contextvars.ContextVar[str | None] = contextvars.ContextVar("RUN_MODE_OVERRIDE", default=None)


def effective_data_mode() -> str:
    """Person 1 adapters call this instead of reading DATA_MODE directly."""
    return "fixture" if RUN_MODE_OVERRIDE.get() == "fixture" else DATA_MODE


def effective_vision_mode() -> str:
    """Person 2 vision calls this instead of reading VISION_MODE directly."""
    return "fixture" if RUN_MODE_OVERRIDE.get() == "fixture" else VISION_MODE

SHARED_DIR = REPO_ROOT / "shared"
CONTRACTS_DIR = SHARED_DIR / "contracts"
EXAMPLES_DIR = SHARED_DIR / "examples"
FIXTURES_DIR = REPO_ROOT / "fixtures"
DEMO_DIR = REPO_ROOT / "demo"
AUDITS_DIR = Path(os.getenv("WATTWALK_AUDITS_DIR") or (REPO_ROOT / "audits"))
CACHE_DIR = AUDITS_DIR / "cache"

FIXTURE_SID = "fixtureUnitA"

MATTERPORT_API_KEY = os.getenv("MATTERPORT_API_KEY", "")
MATTERPORT_API_TOKEN = os.getenv("MATTERPORT_API_TOKEN", "")
VEXCEL_API_KEY = os.getenv("VEXCEL_API_KEY", "")
COSTAR_KIT_ZIP = os.getenv("COSTAR_KIT_ZIP", "")
COSTAR_ZIP_PASSWORD = os.getenv("COSTAR_ZIP_PASSWORD", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SMALL_VISION_MODEL_ID = os.getenv("WATTWALK_SMALL_VISION_MODEL_ID", "")
LARGE_VISION_MODEL_ID = os.getenv("WATTWALK_LARGE_VISION_MODEL_ID", "")
PLANNER_MODEL_ID = os.getenv("WATTWALK_PLANNER_MODEL_ID", "")
# Local Ollama server for "ollama/..." model ids (vision and planner).
OLLAMA_BASE_URL = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
# Google Gemini API for "gemini/..." model ids (vision and planner). Free-tier keys are rate limited:
# vision calls are spaced at least this many seconds apart.
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MIN_INTERVAL_S = float(os.getenv("GEMINI_MIN_INTERVAL_S", "4"))

TIMEOUTS_S = {"matterport": 30, "vexcel": 20, "ebewe": 15, "bedrock_vision": 45, "explain": 15, "ask_user": 30}
