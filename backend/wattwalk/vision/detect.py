"""Bedrock vision calls and output parsing (plan 8.3.2, 8.3.3, Appendix F.5). Owner: Person 2.

The vision model only labels images and reads visible attributes. Everything it returns is
validated against VOCAB; anything outside it is dropped or becomes "unknown".
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Literal

from .. import config
from ..contracts import BBox, ModelCall
from ..errors import UpstreamError
from .cache import cached_call
from .prompts import INT_ATTRS, MODEL_ATTRS, SECOND_LOOK_LABELS, VOCAB
from .types import RawDetection

MIN_BOX_PX = 12
IOU_DUPLICATE = 0.5
IOU_SAME_OBJECT = 0.9  # different labels on a near-identical box: one object, not two
MAX_TOKENS = 1200

_client = None
_client_lock = threading.Lock()


def set_client(client) -> None:
    """Inject a Bedrock runtime client (tests pass a fake with a converse() method)."""
    global _client
    _client = client


def _bedrock():
    global _client
    with _client_lock:
        if _client is None:
            import boto3
            from botocore.config import Config
            _client = boto3.client("bedrock-runtime", region_name=config.AWS_REGION,
                                   config=Config(read_timeout=config.TIMEOUTS_S["bedrock_vision"],
                                                 retries={"max_attempts": 3, "mode": "standard"}))
        return _client


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _converse(model_id: str, image: bytes, prompt: str) -> tuple[str, dict]:
    try:
        resp = _bedrock().converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [
                {"image": {"format": "jpeg", "source": {"bytes": image}}},
                {"text": prompt}]}],
            inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0})
    except Exception as exc:  # botocore ClientError, throttling, timeouts after retries
        status = getattr(exc, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
        raise UpstreamError("bedrock", status not in (401, 403), f"Bedrock call failed: {exc}", status) from exc
    text = resp["output"]["message"]["content"][0]["text"]
    usage = resp.get("usage", {}) or {}
    return text, {"inputTokens": usage.get("inputTokens"), "outputTokens": usage.get("outputTokens")}


# ---------- local development backend: Ollama ----------
# A model id of the form "ollama/<model>" (for example "ollama/qwen2.5vl:7b") sends the call to a
# local Ollama server instead of Bedrock. For free development only: the demo and the benchmark
# use Bedrock (decision D6). Everything else (prompts, parsing, cache, logging) is identical.
OLLAMA_PREFIX = "ollama/"
OLLAMA_URL = f"{config.OLLAMA_BASE_URL}/api/chat"
OLLAMA_TIMEOUT_S = 180  # local models on a laptop are slower than Bedrock


def _ollama(model_id: str, image: bytes, prompt: str) -> tuple[str, dict]:
    import base64
    import urllib.error
    import urllib.request

    body = json.dumps({
        "model": model_id.removeprefix(OLLAMA_PREFIX),
        "messages": [{"role": "user", "content": prompt, "images": [base64.b64encode(image).decode("ascii")]}],
        "stream": False,
        "format": "json",  # constrain the output to valid JSON
        "options": {"temperature": 0, "num_predict": MAX_TOKENS},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        name = model_id.removeprefix(OLLAMA_PREFIX)
        hint = f" Run: ollama pull {name}" if exc.code == 404 else ""
        raise UpstreamError("bedrock", False, f"Ollama returned {exc.code}: {detail}.{hint}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpstreamError("bedrock", True, f"Ollama not reachable at {OLLAMA_URL} (is 'ollama serve' running?): {exc}") from exc
    return data["message"]["content"], {"inputTokens": data.get("prompt_eval_count"), "outputTokens": data.get("eval_count")}


# ---------- free cloud backend: Google Gemini API ----------
# A model id of the form "gemini/<model>" (for example "gemini/gemini-2.5-flash") calls the Gemini
# API with GOOGLE_API_KEY. Free-tier keys are rate limited, so calls are spaced out process-wide and
# HTTP 429 answers are retried after the delay Google asks for.
GEMINI_PREFIX = "gemini/"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_TIMEOUT_S = 60
GEMINI_MAX_TOKENS = 8192   # some Gemini models spend output tokens on internal reasoning first
GEMINI_RETRIES = 3
_gemini_lock = threading.Lock()
_gemini_last = 0.0


def _gemini_wait() -> None:
    """Space calls at least GEMINI_MIN_INTERVAL_S apart (free tier requests-per-minute limit)."""
    global _gemini_last
    with _gemini_lock:
        delay = _gemini_last + config.GEMINI_MIN_INTERVAL_S - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _gemini_last = time.monotonic()


def _retry_after_s(body: str, default: float) -> float:
    """Gemini 429 bodies carry RetryInfo.retryDelay like "17s"."""
    import re
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body)
    return float(m.group(1)) + 1 if m else default


def _gemini(model_id: str, image: bytes, prompt: str) -> tuple[str, dict]:
    import base64
    import urllib.error
    import urllib.request

    if not config.GOOGLE_API_KEY:
        raise UpstreamError("bedrock", False, "GOOGLE_API_KEY is not set; add it to .env for gemini/ model ids")
    model = model_id.removeprefix(GEMINI_PREFIX)
    body = json.dumps({
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode("ascii")}},
            {"text": prompt}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": GEMINI_MAX_TOKENS,
                             "responseMimeType": "application/json"},
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "x-goog-api-key": config.GOOGLE_API_KEY}
    for attempt in range(GEMINI_RETRIES + 1):
        _gemini_wait()
        req = urllib.request.Request(GEMINI_URL.format(model=model), data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT_S) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code in (429, 500, 503) and attempt < GEMINI_RETRIES:
                time.sleep(_retry_after_s(detail, 10.0 * (attempt + 1)))
                continue
            short = detail[:300].replace(config.GOOGLE_API_KEY, "[key]")
            raise UpstreamError("bedrock", exc.code in (429, 500, 503),
                                f"Gemini returned {exc.code}: {short}", exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < GEMINI_RETRIES:
                time.sleep(5.0 * (attempt + 1))
                continue
            raise UpstreamError("bedrock", True, f"Gemini not reachable: {exc}") from exc
    candidates = data.get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text:
        reason = candidates[0].get("finishReason") if candidates else data.get("promptFeedback")
        raise UpstreamError("bedrock", True, f"Gemini returned no text ({reason})")
    usage = data.get("usageMetadata") or {}
    return text, {"inputTokens": usage.get("promptTokenCount"), "outputTokens": usage.get("candidatesTokenCount")}


DETECT_PX_BEDROCK = 768   # plan 8.2
DETECT_PX_GEMINI = 1000   # Gemini reports boxes on a 0-1000 grid; at 1000 px that grid equals pixels
DETECT_PX_OLLAMA = 1008   # measured: Qwen2.5-VL in Ollama upsamples smaller images and reports boxes
                          # in its own grid (factor 1.1 to 1.33); at 1008 px (36 x 28) the factor is 1.0


def detect_px(model_id: str) -> int:
    """Longest side of the image sent for detection."""
    if model_id.startswith(OLLAMA_PREFIX):
        return DETECT_PX_OLLAMA
    if model_id.startswith(GEMINI_PREFIX):
        return DETECT_PX_GEMINI
    return DETECT_PX_BEDROCK


def _call_model(model_id: str, image: bytes, prompt: str) -> tuple[str, dict]:
    if model_id.startswith(OLLAMA_PREFIX):
        return _ollama(model_id, image, prompt)
    if model_id.startswith(GEMINI_PREFIX):
        return _gemini(model_id, image, prompt)
    return _converse(model_id, image, prompt)


def extract_json(text: str) -> dict | None:
    """Substring from the first '{' to the last '}', parsed (plan 8.3.3 step 1)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def call_vision(model_id: str, image: bytes, prompt: str, sid: str, agent: str, kind: Literal["detect", "attr"],
                tier: Literal["small", "large"] = "small", image_px: int | None = None,
                use_cache: bool = True) -> tuple[dict | None, ModelCall, str]:
    """One Converse call (or cache hit). Returns (parsed JSON or None, ModelCall without a final id, raw text).

    The ModelCall id is a placeholder; walk.py assigns c-ids when logging.
    """
    if not model_id:
        raise UpstreamError("bedrock", False, f"no {tier} vision model id configured")
    t0 = time.monotonic()
    text, usage, hit = cached_call((model_id, prompt, image), lambda: _call_model(model_id, image, prompt), enabled=use_cache)
    call = ModelCall(id="c000", agent=agent, kind=kind, model_id=model_id, model_tier=tier,
                     tokens_in=usage.get("inputTokens"), tokens_out=usage.get("outputTokens"),
                     latency_ms=int((time.monotonic() - t0) * 1000), cache_hit=hit,
                     image_px=image_px, at=now_iso())
    return extract_json(text), call, text


def _clean_value(label: str, attr: str, value: Any) -> Any:
    """Validate one attribute value. Returns None for "unknown" or anything out of range or set."""
    allowed = VOCAB[label][attr]
    if isinstance(allowed, list):
        v = str(value).strip().lower() if value is not None else ""
        return v if v in allowed else None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    lo, hi = allowed
    if not lo <= num <= hi:
        return None
    if attr in INT_ATTRS:
        return int(num) if num == int(num) else None
    return round(num, 2)


def clean_attrs(label: str, attrs: Any) -> dict[str, Any]:
    """Keep only model-reportable attributes for the label; every one of them is present (None if unknown)."""
    attrs = attrs if isinstance(attrs, dict) else {}
    return {a: _clean_value(label, a, attrs.get(a)) for a in MODEL_ATTRS.get(label, [])}


def _iou(a: BBox, b: BBox) -> float:
    ix = max(0, min(a.x1, b.x1) - max(a.x0, b.x0))
    iy = max(0, min(a.y1, b.y1) - max(a.y0, b.y0))
    inter = ix * iy
    union = (a.x1 - a.x0) * (a.y1 - a.y0) + (b.x1 - b.x0) * (b.y1 - b.y0) - inter
    return inter / union if union else 0.0


def _area(b: BBox) -> int:
    return (b.x1 - b.x0) * (b.y1 - b.y0)


def image_ok(raw: dict | None) -> bool:
    return bool(raw) and raw.get("image_ok", True) is not False


def parse_detections(raw: dict | None, image_px: int, face_px: int) -> list[RawDetection]:
    """Validate a detection response (plan 8.3.3 steps 2 to 5)."""
    if not raw or not isinstance(raw.get("detections"), list):
        return []
    scale = face_px / image_px
    kept: list[RawDetection] = []
    for det in raw["detections"]:
        if not isinstance(det, dict) or det.get("label") not in VOCAB:
            continue
        box = det.get("bbox")
        if not (isinstance(box, (list, tuple)) and len(box) == 4):
            continue
        try:
            x0, y0, x1, y1 = (min(max(float(v), 0.0), float(image_px)) for v in box)
        except (TypeError, ValueError):
            continue
        if x1 <= x0 or y1 <= y0 or (x1 - x0) < MIN_BOX_PX or (y1 - y0) < MIN_BOX_PX:
            continue
        bbox = BBox(x0=round(x0 * scale), y0=round(y0 * scale), x1=round(x1 * scale), y1=round(y1 * scale))
        kept.append(RawDetection(label=det["label"], bbox=bbox, attrs=clean_attrs(det["label"], det.get("attrs"))))

    # One object given two labels (same box, different label; seen on real scans, for example a
    # window also reported as a lamp): keep the label the model reported first.
    distinct: list[RawDetection] = []
    for d in kept:
        if not any(r.label != d.label and _iou(r.bbox, d.bbox) > IOU_SAME_OBJECT for r in distinct):
            distinct.append(d)

    # Within one face, same label and IoU above 0.5: keep the larger box (plan 8.3.3 step 5).
    distinct.sort(key=lambda d: -_area(d.bbox))
    result: list[RawDetection] = []
    for d in distinct:
        if not any(r.label == d.label and _iou(r.bbox, d.bbox) > IOU_DUPLICATE for r in result):
            result.append(d)
    result.sort(key=lambda d: (d.bbox.y0, d.bbox.x0))  # deterministic reading order
    return result


def second_look_label(raw: dict | None, label: str) -> str | None:
    """The label a detection should have after the second look, or ``None`` to drop it.

    Same label: kept. Another label offered for this detection and in VOCAB: relabelled. Anything
    else (mirror, doorway, picture...): dropped. An unparseable answer keeps the detection: a
    formatting failure must not delete a real object."""
    if not raw or "object" not in raw:
        return label
    answer = str(raw["object"]).strip().lower().replace(" ", "_")
    if answer == label:
        return label
    if answer in VOCAB and answer in SECOND_LOOK_LABELS.get(label, []):
        return answer
    return None


def second_look_keeps(raw: dict | None, label: str) -> bool:
    """True when the second look keeps the detection (possibly under a new label)."""
    return second_look_label(raw, label) is not None


def parse_attrs(raw: dict | None, label: str) -> dict[str, Any]:
    """Validate an attribute-read response ({"attrs": {...}})."""
    return clean_attrs(label, raw.get("attrs") if raw else None)
