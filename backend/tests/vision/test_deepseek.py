"""DeepSeek API backend for "deepseek/..." vision model ids (no network: urlopen is faked)."""
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


def _ok(content: str, reasoning: str = "") -> FakeResponse:
    return FakeResponse(json.dumps({
        "id": "mock-resp-id",
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content,
                "reasoning_content": reasoning,
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 150, "completion_tokens": 30, "total_tokens": 180},
    }).encode())


def _http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("url", code, "err", {}, io.BytesIO(body.encode()))


@pytest.fixture
def deepseek_env(monkeypatch):
    monkeypatch.setattr(detect.config, "DEEPSEEK_API_KEY", "sk-mock-key")
    monkeypatch.setattr(detect.config, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    calls = []
    return calls


def test_deepseek_request_and_parse(deepseek_env, monkeypatch):
    def fake_urlopen(req, timeout):
        deepseek_env.append(req)
        return _ok('{"image_ok": true, "detections": []}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    text, usage = detect._call_model("deepseek/deepseek-flash", b"\xff\xd8jpeg", "prompt")
    assert text == '{"image_ok": true, "detections": []}'
    assert usage == {"inputTokens": 150, "outputTokens": 30}
    assert len(deepseek_env) == 1
    req = deepseek_env[0]
    assert "chat/completions" in req.full_url
    assert req.get_header("Authorization") == "Bearer sk-mock-key"
    body = json.loads(req.data)
    assert body["model"] == "deepseek-flash"
    assert body["messages"][0]["content"][0]["text"] == "prompt"
    assert body["messages"][0]["content"][1]["type"] == "image_url"


def test_deepseek_alias_normalized(deepseek_env, monkeypatch):
    def fake_urlopen(req, timeout):
        deepseek_env.append(req)
        return _ok('{"image_ok": true, "detections": []}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    text, usage = detect._call_model("deepseek/DeepSeek-V4.1-Flash-1017", b"\xff\xd8jpeg", "prompt")
    assert len(deepseek_env) == 1
    body = json.loads(deepseek_env[0].data)
    assert body["model"] == "deepseek-flash"


def test_deepseek_detect_px():
    assert detect.detect_px("deepseek/deepseek-flash") == detect.DETECT_PX_DEEPSEEK == 1024
    assert detect.detect_px("deepseek/DeepSeek-V4.1-Flash-1017") == 1024


def test_deepseek_missing_api_key(monkeypatch):
    monkeypatch.setattr(detect.config, "DEEPSEEK_API_KEY", "")
    with pytest.raises(UpstreamError, match="DEEPSEEK_API_KEY is not set"):
        detect._call_model("deepseek/deepseek-flash", b"\xff\xd8jpeg", "prompt")


def test_deepseek_http_error(deepseek_env, monkeypatch):
    def fake_urlopen(req, timeout):
        raise _http_error(401, '{"error": {"message": "Invalid API key"}}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(UpstreamError) as exc:
        detect._call_model("deepseek/deepseek-flash", b"\xff\xd8jpeg", "prompt")
    assert exc.value.http_status == 401
    assert not exc.value.retryable
