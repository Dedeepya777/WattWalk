"""Gemini API backend for "gemini/..." vision model ids (no network: urlopen is faked)."""
import io
import json
import urllib.error

import pytest

from wattwalk.errors import UpstreamError
from wattwalk.vision import detect


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _ok(text: str) -> FakeResponse:
    return FakeResponse(json.dumps({
        "candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 1290, "candidatesTokenCount": 42},
    }).encode())


def _http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("url", code, "err", {}, io.BytesIO(body.encode()))


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(detect.config, "GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(detect.config, "GEMINI_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(detect.time, "sleep", lambda s: None)
    calls = []
    return calls


def test_gemini_request_and_parse(gemini, monkeypatch):
    def fake_urlopen(req, timeout):
        gemini.append(req)
        return _ok('{"image_ok": true, "detections": []}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    text, usage = detect._call_model("gemini/gemini-2.5-flash", b"\xff\xd8jpeg", "prompt")
    assert text == '{"image_ok": true, "detections": []}'  # reasoning parts are skipped
    assert usage == {"inputTokens": 1290, "outputTokens": 42}
    req = gemini[0]
    assert "models/gemini-2.5-flash:generateContent" in req.full_url
    assert req.get_header("X-goog-api-key") == "test-key"
    body = json.loads(req.data)
    assert body["generationConfig"]["temperature"] == 0
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/jpeg"


def test_gemini_retries_429_then_succeeds(gemini, monkeypatch):
    answers = [_http_error(429, '{"details": [{"retryDelay": "3s"}]}'), _ok('{"attrs": {}}')]

    def fake_urlopen(req, timeout):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    text, _ = detect._call_model("gemini/m", b"x", "p")
    assert text == '{"attrs": {}}' and answers == []
    assert detect._retry_after_s('{"retryDelay": "17s"}', 5) == 18


def test_gemini_bad_key_is_not_retried_and_hides_key(gemini, monkeypatch):
    attempts = []

    def fake_urlopen(req, timeout):
        attempts.append(1)
        raise _http_error(400, "API key not valid: test-key")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(UpstreamError) as err:
        detect._call_model("gemini/m", b"x", "p")
    assert len(attempts) == 1 and "test-key" not in str(err.value) and "[key]" in str(err.value)


def test_gemini_needs_key(monkeypatch):
    monkeypatch.setattr(detect.config, "GOOGLE_API_KEY", "")
    with pytest.raises(UpstreamError, match="GOOGLE_API_KEY"):
        detect._call_model("gemini/m", b"x", "p")


def test_gemini_detection_size_is_1000():
    assert detect.detect_px("gemini/gemini-2.5-flash") == 1000
