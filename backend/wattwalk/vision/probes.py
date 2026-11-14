"""Vision model health probe (fix plan P2-3). Owner: Person 2.

probe_vision() makes one tiny call to the small vision model: a 64 x 64 gray JPEG made in memory and a
one-line JSON prompt. It never raises and gives up after 15 s, so Person 3's GET /health?probe=1 can
call it safely. The result is recorded like any real call (detect.record_health). probe_bedrock is
the name the fix plan uses; it works for Bedrock, Ollama and any other provider detect.py supports.
"""
from __future__ import annotations

import io
import threading

from PIL import Image

from .. import config
from . import detect

PROBE_TIMEOUT_S = 15
PROBE_PROMPT = 'Reply with exactly this JSON and nothing else: {"ok": true}'


def _probe_image() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


def probe_vision(model_id: str | None = None, timeout_s: float = PROBE_TIMEOUT_S) -> tuple[bool, str]:
    model = model_id if model_id is not None else config.SMALL_VISION_MODEL_ID
    if not model:
        return False, "no small vision model id configured"
    outcome: dict[str, tuple[bool, str]] = {}

    def call() -> None:
        try:
            text, _usage = detect._call_model(model, _probe_image(), PROBE_PROMPT)  # records health itself
            outcome["r"] = (True, f"{model} answered") if text.strip() else (False, f"{model} returned no text")
        except Exception as exc:  # the probe must never raise
            outcome["r"] = (False, f"{type(exc).__name__}: {str(exc)[:160]}")

    worker = threading.Thread(target=call, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if "r" not in outcome:
        detect.record_health(False, f"timeout after {timeout_s:g} s")
        return False, f"{model} did not answer within {timeout_s:g} s"
    return outcome["r"]


probe_bedrock = probe_vision
