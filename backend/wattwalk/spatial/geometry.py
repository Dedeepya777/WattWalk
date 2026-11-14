"""Pixel-to-3D anchoring in the Matterport Model API frame.

Owner: Person 4.  Algorithm: plan/plan.md sections 9.2 to 9.5 and Appendix A.5.
The canonical public function is :func:`anchor_from_bbox`.

Coordinates are metres with z up.  A panorama sits at ``pano.position``; the
camera is ``camera_height_m`` above the floor.  Skybox faces 1 to 4 look around
the horizon, 0 up and 5 down.  The face-to-direction mapping is a calibration
constant stored in ``face_basis.json``; until calibration passes it is labelled
``unverified``.

Real Model API panoramas also carry a per-pano ``rotation`` quaternion.  When
it is present, faces use the measured pano-local basis (``pano_local_faces``
in ``face_basis.json``) rotated by that quaternion; see :func:`basis_for_pano`.
Panos without a rotation (fixtures, synthetic tests) use ``faces`` unchanged.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from wattwalk.contracts import BBox, ModelGeometry, Observation, Pano, Quat, Room, Vec2, Vec3, WallSegment

FACE_BASIS_PATH = Path(__file__).resolve().with_name("face_basis.json")

DEFAULT_CAMERA_HEIGHT_M = 1.5
DEFAULT_ROOM_HEIGHT_M = 2.6
# Single-floor Model API scans put the floor at z = 0, so a pano at a plausible
# tripod height is its own camera height.  Outside this band (upper floors,
# odd data) fall back to the basis constant.
CAMERA_HEIGHT_BAND_M = (0.8, 2.0)

# Measured on 2ibibwUGQAe (2026-11-14): with these pano-local directions rotated
# by each pano's quaternion, three sight lines to the same window from three
# panos met within 0.03 m.  Face 1 looks along local +x, then clockwise.
_PANO_LOCAL_FORWARD = {1: (1.0, 0.0, 0.0), 2: (0.0, -1.0, 0.0), 3: (-1.0, 0.0, 0.0), 4: (0.0, 1.0, 0.0)}
WALL_CLEARANCE_M = 0.10
MAX_HIT_DISTANCE_M = 15.0

# Plan 9.3: ceiling fixtures anchor at the top-centre of the box, floor-standing
# appliances at the bottom-centre, everything else at the centre.
CEILING_LABELS = frozenset({"ceiling_light", "ceiling_fan", "supply_vent"})
FLOOR_LABELS = frozenset(
    {
        "refrigerator",
        "range_gas",
        "range_electric",
        "washer",
        "dryer",
        "dishwasher",
        "water_heater",
    }
)


@dataclass(frozen=True)
class FaceDirections:
    """Orthonormal image basis of one horizon skybox face."""

    forward: tuple[float, float, float]
    right: tuple[float, float, float]
    up: tuple[float, float, float]

    def forward_vec(self) -> np.ndarray:
        return np.asarray(self.forward, dtype=float)

    def right_vec(self) -> np.ndarray:
        return np.asarray(self.right, dtype=float)

    def up_vec(self) -> np.ndarray:
        return np.asarray(self.up, dtype=float)


@dataclass(frozen=True)
class FaceBasis:
    """Calibration constant for the six skybox faces of every panorama."""

    status: str
    camera_height_m: float
    faces: Mapping[int, FaceDirections]
    calibrated_on: str | None = None
    residual_m: float | None = None
    pano_local: Mapping[int, FaceDirections] | None = None

    @property
    def calibrated(self) -> bool:
        return self.status == "calibrated"

    def directions(self, face: int) -> FaceDirections:
        try:
            return self.faces[int(face)]
        except KeyError as exc:  # pragma: no cover - guarded by callers
            raise ValueError(f"face must be 1, 2, 3 or 4; got {face!r}") from exc


def load_basis(path: Path | None = None) -> FaceBasis:
    """Read ``face_basis.json`` (plan 9.2).  Missing file means default basis."""
    target = Path(path) if path is not None else FACE_BASIS_PATH
    if not target.exists():
        return _default_basis()
    raw = json.loads(target.read_text(encoding="utf-8"))
    faces: dict[int, FaceDirections] = {}
    for key, value in raw.get("faces", {}).items():
        faces[int(key)] = FaceDirections(
            forward=tuple(float(v) for v in value["forward"]),  # type: ignore[arg-type]
            right=tuple(float(v) for v in value["right"]),  # type: ignore[arg-type]
            up=tuple(float(v) for v in value["up"]),  # type: ignore[arg-type]
        )
    if set(faces) != {1, 2, 3, 4}:
        raise ValueError(f"{target} must define faces 1 to 4")
    pano_local = {int(k): _directions(v) for k, v in raw.get("pano_local_faces", {}).items()}
    if pano_local and set(pano_local) != {1, 2, 3, 4}:
        raise ValueError(f"{target} pano_local_faces must define faces 1 to 4")
    return FaceBasis(
        status=str(raw.get("status", "unverified")),
        camera_height_m=float(raw.get("camera_height_m", DEFAULT_CAMERA_HEIGHT_M)),
        faces=faces,
        calibrated_on=raw.get("calibrated_on"),
        residual_m=raw.get("residual_m"),
        pano_local=pano_local or _measured_pano_local(),
    )


def _directions(value: Mapping[str, Sequence[float]]) -> FaceDirections:
    return FaceDirections(
        forward=tuple(float(v) for v in value["forward"]),  # type: ignore[arg-type]
        right=tuple(float(v) for v in value["right"]),  # type: ignore[arg-type]
        up=tuple(float(v) for v in value["up"]),  # type: ignore[arg-type]
    )


def _measured_pano_local() -> dict[int, FaceDirections]:
    """Pano-local face directions: right = forward x up, up = +z."""
    up = np.array([0.0, 0.0, 1.0])
    faces: dict[int, FaceDirections] = {}
    for face, forward in _PANO_LOCAL_FORWARD.items():
        fw = np.asarray(forward)
        faces[face] = FaceDirections(forward, tuple(float(v) for v in np.cross(fw, up)), (0.0, 0.0, 1.0))  # type: ignore[arg-type]
    return faces


def quat_matrix(q: Quat) -> np.ndarray:
    """3x3 rotation matrix of a unit quaternion (normalised defensively)."""
    x, y, z, w = float(q.x), float(q.y), float(q.z), float(q.w)
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n < 1e-9:
        return np.eye(3)
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def basis_for_pano(basis: FaceBasis, pano: Pano) -> FaceBasis:
    """The face basis of one panorama in the model frame.

    With ``pano.rotation`` the pano-local directions are rotated by it; without
    one the global ``faces`` are returned unchanged (fixtures, synthetic data).
    """
    rotation = getattr(pano, "rotation", None)
    if rotation is None:
        return basis
    local = basis.pano_local or _measured_pano_local()
    r = quat_matrix(rotation)

    def turn(v: Sequence[float]) -> tuple[float, float, float]:
        out = r @ np.asarray(v, dtype=float)
        return (float(out[0]), float(out[1]), float(out[2]))

    faces = {f: FaceDirections(turn(d.forward), turn(d.right), turn(d.up)) for f, d in local.items()}
    return FaceBasis(
        status=basis.status,
        camera_height_m=basis.camera_height_m,
        faces=faces,
        calibrated_on=basis.calibrated_on,
        residual_m=basis.residual_m,
        pano_local=local,
    )


def camera_height(pano: Pano, basis: FaceBasis) -> float:
    """Camera height above the floor: ``pano.z`` inside the band, else the constant."""
    z = float(pano.position.z)
    low, high = CAMERA_HEIGHT_BAND_M
    return z if low <= z <= high else float(basis.camera_height_m)


def face_forward_xy(pano: Pano, basis: FaceBasis | None = None) -> dict[int, tuple[float, float]]:
    """Horizontal look direction of faces 1 to 4 of ``pano`` in the model frame."""
    active = basis_for_pano(basis or load_basis(), pano)
    return {f: (float(active.faces[f].forward[0]), float(active.faces[f].forward[1])) for f in (1, 2, 3, 4)}


def _default_basis() -> FaceBasis:
    """The planning default guess from plan 9.2, used if the JSON is missing."""
    return FaceBasis(
        status="unverified",
        camera_height_m=DEFAULT_CAMERA_HEIGHT_M,
        faces={
            1: FaceDirections((0, 1, 0), (1, 0, 0), (0, 0, 1)),
            2: FaceDirections((1, 0, 0), (0, -1, 0), (0, 0, 1)),
            3: FaceDirections((0, -1, 0), (-1, 0, 0), (0, 0, 1)),
            4: FaceDirections((-1, 0, 0), (0, 1, 0), (0, 0, 1)),
        },
        pano_local=_measured_pano_local(),
    )


def pixel_ray(
    basis: FaceBasis, face: int, u: float, v: float, n: int
) -> np.ndarray:
    """Unit ray through pixel centre ``(u + 0.5, v + 0.5)`` of an ``n x n`` face.

    Plan 9.3: ``a = 2(u + 0.5)/N - 1``, ``b = 1 - 2(v + 0.5)/N`` and
    ``d = normalize(forward + a*right + b*up)``.  The returned vector is in the
    model frame.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    directions = basis.directions(face)
    a = 2.0 * (float(u) + 0.5) / float(n) - 1.0
    b = 1.0 - 2.0 * (float(v) + 0.5) / float(n)
    d = directions.forward_vec() + a * directions.right_vec() + b * directions.up_vec()
    length = float(np.linalg.norm(d))
    if length < 1e-12:
        raise ValueError("degenerate pixel ray")
    return d / length


def ray_wall_hit(
    origin_xy: Sequence[float] | Vec2 | np.ndarray,
    dir_xy: Sequence[float] | Vec2 | np.ndarray,
    walls: Iterable[WallSegment],
) -> float | None:
    """Distance along the horizontal direction to the nearest wall, or ``None``.

    Standard 2D ray/segment intersection.  ``t`` is in metres because the
    horizontal direction is normalised here.  Segments are ``WallSegment``
    values (plan 9.4); ``(a, b)`` tuples are also accepted for tests.
    """
    ox, oy = _xy(origin_xy)
    dx, dy = _xy(dir_xy)
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    hx, hy = dx / length, dy / length

    best: float | None = None
    for wall in walls:
        ax, ay, bx, by = _wall_points(wall)
        ex, ey = bx - ax, by - ay
        denom = hx * ey - hy * ex
        if abs(denom) < 1e-12:  # parallel
            continue
        rx, ry = ax - ox, ay - oy
        t = (rx * ey - ry * ex) / denom
        s = (rx * hy - ry * hx) / denom
        if t <= 1e-9 or s < -1e-9 or s > 1.0 + 1e-9:
            continue
        if best is None or t < best:
            best = t
    return best


def anchor_pixel(bbox: BBox, label: str | None = None) -> tuple[float, float]:
    """Pixel used for anchoring (plan 9.3): centre, top-centre or bottom-centre."""
    u = (float(bbox.x0) + float(bbox.x1)) / 2.0
    if label in CEILING_LABELS:
        v = float(bbox.y0)
    elif label in FLOOR_LABELS:
        v = float(bbox.y1)
    else:
        v = (float(bbox.y0) + float(bbox.y1)) / 2.0
    return u, v


def anchor_from_bbox(
    pano: Pano,
    face: int,
    bbox: BBox,
    face_px: int,
    walls: list[WallSegment],
    room: Room | None,
    label: str | None = None,
    basis: FaceBasis | None = None,
) -> tuple[Vec3 | None, str]:
    """Anchor one detection and return ``(point, method)``.

    ``method`` is ``wall_raycast``, ``ceiling_plane``, ``floor_plane`` or
    ``none``.  Coordinates are rounded to 3 decimals (plan 7.1).

    The canonical signature in shared/contracts/README.md section 5 has six
    arguments.  ``label`` and ``basis`` are optional, backwards-compatible
    extensions: Person 2 should pass ``label=observation.label`` so ceiling and
    floor-standing detections use the top/bottom of the box as plan 9.3
    requires.  Without ``label`` the box centre is used.
    """
    active_basis = basis_for_pano(basis or load_basis(), pano)
    u, v = anchor_pixel(bbox, label)
    direction = pixel_ray(active_basis, face, u, v, face_px)

    origin = np.asarray(
        [float(pano.position.x), float(pano.position.y), float(pano.position.z)],
        dtype=float,
    )
    dx, dy, dz = float(direction[0]), float(direction[1]), float(direction[2])
    horizontal_len = math.hypot(dx, dy)

    candidates: list[tuple[float, str, float]] = []

    # Wall raycast (plan 9.4).  Stop 0.10 m before the wall.
    if horizontal_len >= 1e-6:
        wall_t = ray_wall_hit((origin[0], origin[1]), (dx, dy), walls)
        if wall_t is not None:
            stopped = wall_t - WALL_CLEARANCE_M
            if 1e-9 < stopped <= MAX_HIT_DISTANCE_M:
                candidates.append((stopped, "wall_raycast", stopped / horizontal_len))

    # Ceiling and floor planes (plan 9.5).
    room_height = DEFAULT_ROOM_HEIGHT_M
    if room is not None and room.height_m is not None:
        room_height = float(room.height_m)
    floor_z = float(origin[2]) - camera_height(pano, active_basis)
    if dz > 1e-9:
        ceiling_z = floor_z + room_height
        delta_z = ceiling_z - float(origin[2])
        if delta_z > 1e-9:
            horizontal = delta_z / dz * horizontal_len
            if horizontal <= MAX_HIT_DISTANCE_M:
                candidates.append((horizontal, "ceiling_plane", delta_z / dz))
    elif dz < -1e-9:
        delta_z = floor_z - float(origin[2])
        if delta_z < -1e-9:
            horizontal = delta_z / dz * horizontal_len
            if horizontal <= MAX_HIT_DISTANCE_M:
                candidates.append((horizontal, "floor_plane", delta_z / dz))

    if not candidates:
        return None, "none"

    _, method, displacement = min(candidates, key=lambda item: item[0])
    point = origin + direction * displacement
    return (
        Vec3(
            x=round(float(point[0]), 3),
            y=round(float(point[1]), 3),
            z=round(float(point[2]), 3),
        ),
        method,
    )


def anchor_observation(
    observation: Observation,
    geometry: ModelGeometry,
    basis: FaceBasis | None = None,
) -> tuple[Vec3 | None, str]:
    """Convenience wrapper for Person 2: anchor a full ``Observation``.

    Looks up its panorama and room, then calls :func:`anchor_from_bbox` with the
    observation label so ceiling and floor-standing boxes use the correct pixel.
    """
    pano = next((item for item in geometry.panos if item.id == observation.pano_id), None)
    if pano is None:
        return None, "none"
    room = None
    if observation.room_id:
        room = next(
            (item for item in geometry.rooms if item.id == observation.room_id), None
        )
    return anchor_from_bbox(
        pano,
        observation.face,
        observation.bbox,
        observation.face_px,
        geometry.walls,
        room,
        label=observation.label,
        basis=basis,
    )


def room_centroid(room: Room) -> Vec2:
    """Area centroid of a room polygon; used for the 2D approximate fallback."""
    points = [(float(p.x), float(p.y)) for p in room.polygon]
    if len(points) < 3:
        return Vec2(x=0.0, y=0.0)
    twice_area = 0.0
    cx = 0.0
    cy = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(twice_area) < 1e-12:
        return Vec2(
            x=round(sum(x for x, _ in points) / len(points), 3),
            y=round(sum(y for _, y in points) / len(points), 3),
        )
    return Vec2(
        x=round(cx / (3.0 * twice_area), 3),
        y=round(cy / (3.0 * twice_area), 3),
    )


def _xy(value: Sequence[float] | Vec2 | np.ndarray) -> tuple[float, float]:
    if isinstance(value, Vec2):
        return float(value.x), float(value.y)
    if isinstance(value, np.ndarray):
        return float(value[0]), float(value[1])
    return float(value[0]), float(value[1])


def _wall_points(wall: WallSegment) -> tuple[float, float, float, float]:
    if isinstance(wall, WallSegment):
        return (
            float(wall.a.x),
            float(wall.a.y),
            float(wall.b.x),
            float(wall.b.y),
        )
    # Tolerate ((ax, ay), (bx, by)) in tests.
    (ax, ay), (bx, by) = wall  # type: ignore[misc]
    return float(ax), float(ay), float(bx), float(by)
