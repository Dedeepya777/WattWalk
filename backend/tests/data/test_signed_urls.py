"""Matterport signed skybox URLs expire after about 5 minutes: never reuse a stale one, refresh on 410."""
import time

import pytest

from wattwalk import config
from wattwalk.data import matterport as mp


def _url(expiry: int, tag: str = "a") -> str:
    return f"https://cdn-2.matterport.com/x/{tag}_skybox1.jpg?t=2-b922544bbc6d5cdf29-{expiry}-1&k=models%2Fx"


def test_url_expiry_is_read_from_the_signature():
    assert mp._url_expiry(_url(1794674137)) == 1794674137
    assert mp._url_expiry("https://example.com/no-signature.jpg") is None


def test_cache_reused_only_while_links_have_life_left():
    now = time.time()
    fresh = {"p": [_url(int(now) + 300)]}
    nearly_stale = {"p": [_url(int(now) + 30)]}
    assert mp._skybox_cache_valid(now, fresh, now)
    assert not mp._skybox_cache_valid(now, nearly_stale, now)
    assert mp._skybox_cache_valid(now - 100, {"p": ["https://x/y.jpg"]}, now)       # no expiry: fallback TTL
    assert not mp._skybox_cache_valid(now - 300, {"p": ["https://x/y.jpg"]}, now)


class _Resp:
    def __init__(self, status: int, content: bytes = b"jpeg"):
        self.status_code, self.content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} Client Error")


def test_face_download_refreshes_links_after_410(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_MODE", "live")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    mp._SKYBOX_CACHE.clear()
    now = int(time.time())
    batches = [{"p1": [_url(now + 300, f"old{i}") for i in range(6)]},
               {"p1": [_url(now + 300, f"new{i}") for i in range(6)]}]
    monkeypatch.setattr(mp, "graph", lambda q, v: {"model": {"panoLocations": [
        {"id": "p1", "skybox": {"status": "available", "children": batches.pop(0)["p1"]}}]}})
    got = []

    def fake_get(url, timeout):
        got.append(url)
        return _Resp(410) if "old" in url else _Resp(200)

    monkeypatch.setattr(mp.requests, "get", fake_get)
    path = mp.get_face_image("sid1", "p1", 2, "2k")
    assert path.read_bytes() == b"jpeg"
    assert "old2" in got[0] and "new2" in got[1] and len(got) == 2
