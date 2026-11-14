"""Doorway rescue: a sight line stopped by a wall that is really an opening adopts a clean view's anchor."""
from wattwalk.contracts import BBox, Observation, Pano, Quality, Vec2, Vec3, WallSegment
from wattwalk.spatial.geometry import anchor_from_bbox
from wattwalk.vision.triangulate import rescue_blocked

AHEAD = BBox(x0=1000, y0=1000, x1=1048, y1=1048)  # centre pixel: straight along the face's forward


def _geometry(geometry, walls, panos):
    return geometry.model_copy(update={"walls": walls, "panos": panos, "rooms": geometry.rooms})


def _obs(oid, pano, face, geo, label="window"):
    anchor, method = anchor_from_bbox(pano, face, AHEAD, 2048, geo.walls, None, label=label)
    return Observation(id=oid, pano_id=pano.id, face=face, resolution="2k", face_px=2048, bbox=AHEAD,
                       label=label, attrs={}, model_id="m", model_tier="small", escalated=False,
                       crop_ref=f"crops/{oid}.jpg", anchor=anchor, anchor_method=method, room_id=None,
                       quality=Quality(blur=500, brightness=120, accepted=True), created_at="2026-11-14T00:00:00Z")


def _scene(geometry):
    # Fixture basis (no rotation): face 1 looks +y, face 2 looks +x.
    closet = Pano(id="pa", label="1", position=Vec3(x=0, y=0, z=1.3), room_id=None)
    clean = Pano(id="pb", label="2", position=Vec3(x=3.9, y=-3, z=1.3), room_id=None)
    walls = [
        WallSegment(a=Vec2(x=1, y=-1), b=Vec2(x=1, y=1), floor_id="f"),      # closet wall drawn over the door
        WallSegment(a=Vec2(x=3, y=0.1), b=Vec2(x=5, y=0.1), floor_id="f"),   # wall the window is on
    ]
    geo = _geometry(geometry, walls, [closet, clean])
    return geo, closet, clean


def test_blocked_view_adopts_clean_anchor(geometry):
    geo, closet, clean = _scene(geometry)
    blocked = _obs("o1", closet, 2, geo)
    good = _obs("o2", clean, 1, geo)
    assert blocked.anchor.x < 1.0  # stuck on the closet wall
    fixed = rescue_blocked([blocked, good], geo)
    assert set(fixed) == {"o1"}
    assert fixed["o1"].anchor == good.anchor


def test_no_rescue_for_other_labels_or_same_pano(geometry):
    geo, closet, clean = _scene(geometry)
    blocked = _obs("o1", closet, 2, geo)
    lamp = _obs("o2", clean, 1, geo, label="lamp")
    assert rescue_blocked([blocked, lamp], geo) == {}


def test_two_clean_views_are_left_alone(geometry):
    geo, _, clean = _scene(geometry)
    other = Pano(id="pc", label="3", position=Vec3(x=0, y=0, z=1.3), room_id=None)
    geo = _geometry(geometry, [w for w in geo.walls if w.a.x != 1], [other, clean])  # no closet wall
    a, b = _obs("o1", other, 2, geo), _obs("o2", clean, 1, geo)
    assert rescue_blocked([a, b], geo) == {}
