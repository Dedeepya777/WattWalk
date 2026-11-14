"""Face image quality check, downscale and crop (plan 8.2, 7.6, 8.5). Owner: Person 2.

Thresholds are initial values from plan 8.2; record any tuned values in vision/README.md.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

from ..contracts import BBox, Quality

BLUR_MIN = 60.0
BRIGHTNESS_MIN = 40.0
BRIGHTNESS_MAX = 220.0
SHARPNESS_MIN = 0.08      # tuned on 2ibibwUGQAe and 2YKpZqjy5bJ: sharp >= 0.13, blurred <= 0.028
EDGE_GRADIENT = 40.0      # Sobel magnitude that counts as an edge pixel
MIN_EDGE_PIXELS = 500
JPEG_QUALITY = 90


def _laplacian_var(gray: np.ndarray) -> float:
    try:
        import cv2
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except ImportError:
        # Same 3x3 kernel and BORDER_REFLECT_101 border as cv2.Laplacian with ksize=1.
        g = np.pad(gray.astype(np.float64), 1, mode="reflect")
        lap = g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4 * g[1:-1, 1:-1]
        return float(lap.var())


def edge_sharpness(gray: np.ndarray) -> float | None:
    """How crisp the edges that exist are: mean |Laplacian| / mean gradient magnitude on edge pixels.

    Independent of how much texture the image has, so a sharp photo of a plain wall scores like any
    sharp photo. Measured on hero scans: sharp faces 0.13 to 0.34, the same faces blurred (Gaussian
    radius 4) 0.020 to 0.028. None when the image has almost no edges (nothing to judge).
    """
    g = np.pad(gray.astype(np.float64), 1, mode="reflect")
    c = g[1:-1, 1:-1]
    lap = g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4 * c
    gx = (g[:-2, 2:] + 2 * g[1:-1, 2:] + g[2:, 2:]) - (g[:-2, :-2] + 2 * g[1:-1, :-2] + g[2:, :-2])
    gy = (g[2:, :-2] + 2 * g[2:, 1:-1] + g[2:, 2:]) - (g[:-2, :-2] + 2 * g[:-2, 1:-1] + g[:-2, 2:])
    mag = np.hypot(gx, gy)
    edges = mag > EDGE_GRADIENT
    if edges.sum() < MIN_EDGE_PIXELS:
        return None
    return float(np.abs(lap)[edges].mean() / mag[edges].mean())


def is_blurry(blur: float, sharpness: float | None) -> bool:
    """Low Laplacian variance alone also flags sharp photos of plain walls and doors, so a face is
    blurry only when the variance is low AND the edges it has are soft. A face with almost no edges
    (a blank wall) is not rejected: the model call simply finds nothing."""
    return blur < BLUR_MIN and sharpness is not None and sharpness < SHARPNESS_MIN


def quality(path: Path) -> Quality:
    with Image.open(path) as im:
        gray = np.asarray(im.convert("L"))
    blur = round(_laplacian_var(gray), 1)
    brightness = round(float(gray.mean()), 1)
    blurry = blur < BLUR_MIN and is_blurry(blur, edge_sharpness(gray))
    accepted = not blurry and BRIGHTNESS_MIN <= brightness <= BRIGHTNESS_MAX
    return Quality(blur=blur, brightness=brightness, accepted=accepted)


def rejection_reason(q: Quality) -> str:
    """Short reason for a rejected face, used in coverage notes."""
    if q.brightness < BRIGHTNESS_MIN:
        return f"too dark (brightness {round(q.brightness)})"
    if q.brightness > BRIGHTNESS_MAX:
        return f"too bright (brightness {round(q.brightness)})"
    return f"too blurry (blur {round(q.blur)})"


def _jpeg(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def _fit(im: Image.Image, longest: int) -> Image.Image:
    w, h = im.size
    scale = longest / max(w, h)
    if scale >= 1:
        return im
    return im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)


def downscale(path: Path, longest: int = 768) -> bytes:
    with Image.open(path) as im:
        return _jpeg(_fit(im, longest))


def padded_box(bbox: BBox, size: tuple[int, int], pad: float = 0.15) -> tuple[int, int, int, int]:
    w, h = size
    px, py = (bbox.x1 - bbox.x0) * pad, (bbox.y1 - bbox.y0) * pad
    x0 = min(max(0, int(bbox.x0 - px)), w - 1)
    y0 = min(max(0, int(bbox.y0 - py)), h - 1)
    # never an empty or inverted box, even if the bbox lies outside the image
    return x0, y0, max(x0 + 1, min(w, int(round(bbox.x1 + px)))), max(y0 + 1, min(h, int(round(bbox.y1 + py))))


def crop(path: Path, bbox: BBox, pad: float = 0.15, longest: int = 1024) -> bytes:
    """Crop padded 15% around the bbox, longest side at most 1024 px, JPEG quality 90 (plan 7.6)."""
    with Image.open(path) as im:
        return _jpeg(_fit(im.crop(padded_box(bbox, im.size, pad)), longest))


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size
