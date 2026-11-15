"""Bird's-eye views: right Vexcel request, cached, clear errors (Vexcel is faked here)."""
import pytest

from wattwalk import birdseye as b
from wattwalk import config


class FakeResponse:
    def __init__(self, status=200, ctype="image/jpeg", content=b"\xff\xd8jpeg"):
        self.status_code, self.headers, self.content = status, {"Content-Type": ctype}, content


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "VEXCEL_API_KEY", "test-key")


def test_fetches_the_oblique_view_and_caches_it(monkeypatch):
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append((url, params))
        return FakeResponse()

    monkeypatch.setattr(b.requests, "get", fake_get)
    path = b.birdseye("wYFF3KYdETV", "west")  # 819 Santee St, in the models index
    assert path.read_bytes().startswith(b"\xff\xd8")
    url, params = calls[0]
    assert url.endswith("/v2/oriented/extract")
    assert params["product-type"] == "oblique-west" and params["wkt"].startswith("POINT(-118.25")
    assert params["attribution"] == "true"
    b.birdseye("wYFF3KYdETV", "west")
    assert len(calls) == 1  # second time from the cache


def test_errors_are_clear(monkeypatch):
    with pytest.raises(ValueError):
        b.birdseye("wYFF3KYdETV", "up")
    with pytest.raises(b.NoLocation):
        b.birdseye("notInTheIndex")
    monkeypatch.setattr(b.requests, "get", lambda *a, **k: FakeResponse(500, "application/json", b"{}"))
    with pytest.raises(b.Unavailable):
        b.birdseye("wYFF3KYdETV", "north")
    monkeypatch.setattr(config, "VEXCEL_API_KEY", "")
    with pytest.raises(b.NoKey):
        b.birdseye("wYFF3KYdETV", "south")
