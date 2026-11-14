"""WattWalk spatial anchoring (Person 4).

Turns a 2D detection (panorama, skybox face, bounding box) into a 3D point in
the Matterport Model API frame: metres, z up.  Public interface:
``anchor_from_bbox`` (canonical, shared/contracts/README.md section 5) and the
calibration CLI ``python -m wattwalk.spatial.calibrate``.
"""
from .geometry import (
    CEILING_LABELS,
    FLOOR_LABELS,
    FaceBasis,
    FaceDirections,
    anchor_from_bbox,
    anchor_observation,
    load_basis,
    pixel_ray,
    ray_wall_hit,
    room_centroid,
)

__all__ = [
    "CEILING_LABELS",
    "FLOOR_LABELS",
    "FaceBasis",
    "FaceDirections",
    "anchor_from_bbox",
    "anchor_observation",
    "load_basis",
    "pixel_ray",
    "ray_wall_hit",
    "room_centroid",
]
