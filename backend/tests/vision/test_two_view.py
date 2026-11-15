"""Two-view anchors: objects with no wall to cast onto are placed where two sight lines cross."""
import numpy as np

from wattwalk.contracts import Vec3
from wattwalk.vision import triangulate as t


class Obs:
    """Just the fields anchor_unplaced uses."""
    def __init__(self, oid, pano, label="window", anchor=None):
        self.id, self.pano_id, self.label, self.anchor = oid, pano, label, anchor
        self.anchor_method = "none" if anchor is None else "wall_raycast"

    def model_copy(self, update):
        new = Obs(self.id, self.pano_id, self.label, update["anchor"])
        new.anchor_method, new.room_id = update["anchor_method"], update["room_id"]
        return new


def _rays(monkeypatch, rays):
    def fake_ray(geometry, obs):
        origin, target = rays[obs.id]
        o, d = np.array(origin, float), np.array(target, float) - np.array(origin, float)
        return obs.pano_id, o, d / np.linalg.norm(d)
    monkeypatch.setattr(t, "_ray", fake_ray)
    monkeypatch.setattr("wattwalk.vision.views.room_for", lambda g, p, a: None)


def test_two_sight_lines_place_a_window(monkeypatch):
    window = (3.0, 2.0, 1.5)
    _rays(monkeypatch, {"o1": ((0, 0, 1.5), window), "o2": ((4, -1, 1.5), window)})
    fixed = t.anchor_unplaced([Obs("o1", "p1"), Obs("o2", "p2")], geometry=None)
    assert set(fixed) == {"o1", "o2"}
    a = fixed["o1"].anchor
    assert (round(a.x, 2), round(a.y, 2), round(a.z, 2)) == window
    assert fixed["o1"].anchor_method == "two_view"


def test_no_crossing_or_bad_height_or_already_placed_changes_nothing(monkeypatch):
    _rays(monkeypatch, {
        "o1": ((0, 0, 1.5), (3, 2, 1.5)), "o2": ((0, 5, 1.5), (3, 9, 1.5)),        # lines never meet
        "o3": ((0, 0, 1.5), (3, 2, 9.0)), "o4": ((4, -1, 1.5), (3, 2, 9.0)),        # meet 9 m up
        "o5": ((0, 0, 1.5), (3, 2, 1.5)), "o6": ((4, -1, 1.5), (3, 2, 1.5)),        # o5 already placed
    })
    observations = [Obs("o1", "p1"), Obs("o2", "p2"), Obs("o3", "p1", "lamp"), Obs("o4", "p2", "lamp"),
                    Obs("o5", "p1", "fan", Vec3(x=0, y=0, z=0)), Obs("o6", "p2", "fan")]
    fixed = t.anchor_unplaced(observations, geometry=None)
    assert set(fixed) == {"o6"}  # only the unplaced fan, crossing the placed one's sight line
