"""Calls into other people's modules, with temporary stand-ins until they exist. Owner: Person 2.

Every stand-in keeps the final signature, so nothing else changes when the real module lands.
Search for "TEMPORARY" to find them; they are removed at M2.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from .. import config
from ..contracts import BBox, ModelGeometry, Pano, Room, Vec3, WallSegment
from ..errors import UpstreamError


def get_geometry(sid: str) -> ModelGeometry:
    try:
        from ..data.matterport import get_geometry as real  # Person 1
    except ImportError:
        real = None
    if real is not None:
        return real(sid)
    # TEMPORARY until Person 1 delivers: read the fixture geometry files.
    if sid == config.FIXTURE_SID:
        path = config.EXAMPLES_DIR / "model_geometry.json"
    else:
        path = config.FIXTURES_DIR / "live" / sid / "geometry.json"
    if not path.exists():
        raise ValueError(f"no geometry for sid {sid} (Person 1 adapter not installed and no fixture at {path})")
    return ModelGeometry.model_validate_json(path.read_text(encoding="utf-8"))


def get_face_image(sid: str, pano_id: str, face: int, resolution: Literal["2k", "4k"]) -> Path:
    # A locally cached face (downloaded by hand or by the adapter) wins in both modes.
    cached = Path(config.CACHE_DIR) / "faces" / sid / f"{pano_id}_{face}_{resolution}.jpg"
    if cached.exists():
        return cached
    try:
        from ..data.matterport import get_face_image as real  # Person 1
    except ImportError:
        real = None
    if real is not None:
        return real(sid, pano_id, face, resolution)
    # TEMPORARY until Person 1 delivers: faces downloaded by hand (for example with the quickstart
    # notebook) into audits/cache/faces/<sid>/<pano>_<face>_<res>.jpg. That folder is gitignored.
    raise UpstreamError("matterport", False, f"face image not found locally: {cached}")


def anchor_from_bbox(pano: Pano, face: int, bbox: BBox, face_px: int,
                     walls: list[WallSegment], room: Room | None,
                     label: str | None = None) -> tuple[Vec3 | None, str]:
    try:
        from ..spatial.geometry import anchor_from_bbox as real  # Person 4
    except ImportError:
        real = None
    if real is not None:
        return real(pano, face, bbox, face_px, walls, room, label=label)
    # TEMPORARY until Person 4 delivers: no anchor. Dedupe then relies on same-room rules only.
    return None, "none"


# Default (unverified) face basis from plan 9.2: the horizontal direction each horizon face looks
# along in the model frame. Person 4 owns the calibrated values in spatial/face_basis.json.
_DEFAULT_FORWARD = {1: (0.0, 1.0), 2: (1.0, 0.0), 3: (0.0, -1.0), 4: (-1.0, 0.0)}


def face_forward_xy() -> dict[int, tuple[float, float]]:
    try:
        from ..spatial.geometry import load_basis  # Person 4
        basis = load_basis()
        return {f: (float(basis.forward(f)[0]), float(basis.forward(f)[1])) for f in (1, 2, 3, 4)}
    except Exception:  # module missing or a different basis API: fall back to the documented default
        return dict(_DEFAULT_FORWARD)
