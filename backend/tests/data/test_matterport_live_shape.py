"""Live Matterport parsing against the real Model API response shape (plan Appendix F.1, F.2).

Regression: the live queries asked for fields the API does not have (address.formattedAddress,
geolocation.latitude, floors.rooms, room.classification), so every live audit failed.
"""
from __future__ import annotations

import pytest

from wattwalk import config
from wattwalk.data import matterport as mp

GEOMETRY = {"model": {
    "id": "liveSid", "name": "Test",
    "address": {"address": "1 Test St, Los Angeles, CA", "locality": "Los Angeles"},
    "geolocation": {"lat": "34.1", "long": "-118.3"},
    "floors": [{"id": "f1", "label": "Floor 1",
                "vertices": [{"id": v, "position": {"x": x, "y": y}} for v, x, y in
                             [("a", 0, 0), ("b", 4, 0), ("c", 4, 3), ("d", 0, 3), ("e", 6, 0), ("f", 6, 3)]],
                "edges": [{"id": e, "type": t, "thickness": 0.1, "vertices": [{"id": p}, {"id": q}]} for e, t, p, q in
                          [("ab", "wall", "a", "b"), ("bc", "wall", "b", "c"), ("cd", "wall", "c", "d"),
                           ("da", "wall", "d", "a"), ("be", "wall", "b", "e"), ("ef", "wall", "e", "f"),
                           ("fc", "opening", "f", "c")]]}],
    "rooms": [
        # boundary edges deliberately out of order: the ring must still chain correctly
        {"id": "r1", "floor": {"id": "f1"}, "classifications": [{"label": "Other", "confidence": 0.2},
                                                               {"label": "Kitchen", "confidence": 0.9}],
         "boundary": {"edges": [{"id": "cd"}, {"id": "ab"}, {"id": "da"}, {"id": "bc"}]},
         "dimensions": {"areaFloor": 12.0, "height": 2.7}},
        {"id": "r2", "floor": {"id": "f1"}, "classifications": [],
         "boundary": {"edges": [{"id": "be"}, {"id": "ef"}, {"id": "fc"}, {"id": "bc"}]},
         "dimensions": {"areaFloor": None, "height": None}},
        {"id": "void", "floor": {"id": "f1"}, "classifications": [{"label": "Void", "confidence": 1.0}],
         "boundary": {"edges": [{"id": "ab"}, {"id": "bc"}, {"id": "cd"}]}, "dimensions": {}},
        {"id": "noBoundary", "floor": {"id": "f1"}, "classifications": [{"label": "Closet", "confidence": 1}],
         "boundary": None, "dimensions": {}},
    ],
    "panoLocations": [{"id": "p1", "label": "1", "position": {"x": 2, "y": 1.5, "z": 1.5}},
                      {"id": "p2", "label": "2", "position": {"x": 5, "y": 1.5, "z": 1.5}},
                      {"id": "p3", "label": "3", "position": {"x": 9, "y": 9, "z": 1.5}}]}}

SKYBOX = {"model": {"panoLocations": [
    {"id": "p1", "skybox": {"status": "available", "children": [f"https://cdn/x/{i}.jpg" for i in range(6)]}},
    {"id": "p2", "skybox": {"status": "unavailable", "children": []}}]}}


@pytest.fixture
def live(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_MODE", "live")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    mp._SKYBOX_CACHE.clear()
    queries = []

    def fake_graph(query, variables):
        queries.append(query)
        return SKYBOX if "skybox" in query else GEOMETRY

    monkeypatch.setattr(mp, "graph", fake_graph)
    return queries


def test_live_geometry_real_shape(live):
    g = mp.get_geometry("liveSid")
    assert g.status == "live" and g.address == "1 Test St, Los Angeles, CA" and (g.lat, g.lon) == (34.1, -118.3)
    assert [(r.id, r.label) for r in g.rooms] == [("r1", "Kitchen"), ("r2", "Unlabelled")]  # Void and no-boundary dropped
    kitchen, other = g.rooms
    assert {(p.x, p.y) for p in kitchen.polygon} == {(0, 0), (4, 0), (4, 3), (0, 3)}
    assert kitchen.height_m == 2.7 and other.height_m is None and other.area_m2 == 6.0  # area from the polygon
    assert len(g.walls) == 6  # the "opening" edge is not a wall
    assert [(p.id, p.room_id) for p in g.panos] == [("p1", "r1"), ("p2", "r2"), ("p3", None)]
    assert kitchen.pano_ids == ["p1"] and other.pano_ids == ["p2"]
    q = live[0]
    for bad in ("formattedAddress", "latitude", "classification\n"):
        assert bad not in q


def test_live_skybox_real_shape(live):
    urls = mp.skybox_urls("liveSid", "2k")
    assert urls["p1"][4] == "https://cdn/x/4.jpg" and urls["p2"] == []  # unavailable skybox: no faces
    assert 'skybox(resolution: "2k")' in live[0]
    with pytest.raises(ValueError):
        mp.skybox_urls("liveSid", "8k")
