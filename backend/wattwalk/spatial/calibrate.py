"""Face-basis calibration for WattWalk (Person 4).

Plan 9.6 and Appendix H.5.  The mapping from skybox face indices 1 to 4 to model
directions is not documented in the material we have, so it is a calibration
constant.  This module enumerates the eight candidate bases, scores each against
user-marked point correspondences by triangulation, and writes the winner into
``face_basis.json`` only when the acceptance test passes.

Usage::

    python -m wattwalk.spatial.calibrate --sid <sid> --pano-a p01 --pano-b p02
    # mark the same physical points in two faces, save as points.csv, then:
    python -m wattwalk.spatial.calibrate --sid <sid> --points points.csv

``points.csv`` columns: ``pano,face,u,v,point_id`` with exactly two rows per
point id.  Pixel coordinates refer to 2k (2048 px) face images.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from wattwalk.contracts import ModelGeometry, Pano, Room, Vec2
from wattwalk.spatial.geometry import (
    FACE_BASIS_PATH,
    FaceBasis,
    FaceDirections,
    load_basis,
    pixel_ray,
)

ACCEPT_MEAN_M = 0.30
ACCEPT_RATIO = 2.0
HORIZON_FACES = (1, 2, 3, 4)
DEFAULT_FACE_PX = 2048


@dataclass(frozen=True)
class Correspondence:
    """One marked pixel in one face of one panorama."""

    pano_id: str
    face: int
    u: float
    v: float
    point_id: str = ""


@dataclass(frozen=True)
class CandidateScore:
    """Triangulation score of one candidate basis (plan H.5)."""

    basis: FaceBasis
    mean: float
    inside_ratio: float
    n_pairs: int
    residuals: tuple[float, ...] = ()


def candidate_bases(camera_height_m: float = 1.5) -> list[FaceBasis]:
    """The eight candidate bases from plan 9.6.

    Face 1's forward is one of +x, -x, +y, -y; faces 2 to 4 continue clockwise
    or counterclockwise seen from above.  ``up`` is +z and ``right`` is the
    matching perpendicular, which also covers the mirrored convention.
    """
    starts = ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0))
    bases: list[FaceBasis] = []
    for start in starts:
        for turn in (-1, 1):
            faces: dict[int, FaceDirections] = {}
            for index in range(4):
                forward = _rotate_z(start, turn * index * 90.0)
                right = _rotate_z(forward, turn * 90.0)
                faces[index + 1] = FaceDirections(
                    forward=forward, right=right, up=(0.0, 0.0, 1.0)
                )
            bases.append(
                FaceBasis(
                    status="candidate",
                    camera_height_m=camera_height_m,
                    faces=faces,
                )
            )
    return bases


def score_candidate(
    basis: FaceBasis,
    correspondences: Sequence[Correspondence] | Sequence[tuple[Correspondence, Correspondence]],
    panos: Mapping[str, Pano] | Sequence[Pano],
    rooms: Sequence[Room] | Sequence[Sequence[Vec2] | Sequence[Sequence[float]]],
    face_px: int = DEFAULT_FACE_PX,
) -> CandidateScore:
    """Triangulate all correspondence pairs and score one candidate basis.

    Returns the mean closest-approach distance and the fraction of midpoints
    inside a room polygon.  A pair whose rays are parallel or point away from
    the camera contributes an infinite residual, so the candidate is rejected.
    """
    pairs = _as_pairs(correspondences)
    if not pairs:
        return CandidateScore(basis=basis, mean=math.inf, inside_ratio=0.0, n_pairs=0)

    residuals: list[float] = []
    inside = 0
    for first, second in pairs:
        origin_a = _pano_position(panos, first.pano_id)
        origin_b = _pano_position(panos, second.pano_id)
        if origin_a is None or origin_b is None:
            residuals.append(math.inf)
            continue
        direction_a = pixel_ray(basis, first.face, first.u, first.v, face_px)
        direction_b = pixel_ray(basis, second.face, second.u, second.v, face_px)
        point_a, point_b = _closest_points(origin_a, direction_a, origin_b, direction_b)
        if point_a is None or point_b is None:
            residuals.append(math.inf)
            continue
        distance = float(np.linalg.norm(point_a - point_b))
        residuals.append(distance)
        midpoint = (point_a + point_b) / 2.0
        if _inside_any(midpoint[0], midpoint[1], rooms):
            inside += 1

    finite = [value for value in residuals if math.isfinite(value)]
    mean = float(sum(finite) / len(finite)) if finite else math.inf
    return CandidateScore(
        basis=basis,
        mean=mean,
        inside_ratio=inside / len(pairs),
        n_pairs=len(pairs),
        residuals=tuple(residuals),
    )


def evaluate_candidates(
    correspondences: Sequence[Correspondence] | Sequence[tuple[Correspondence, Correspondence]],
    panos: Mapping[str, Pano] | Sequence[Pano],
    rooms: Sequence[Room] | Sequence[Sequence[Vec2] | Sequence[Sequence[float]]],
    face_px: int = DEFAULT_FACE_PX,
    camera_height_m: float = 1.5,
) -> list[CandidateScore]:
    """Score all eight candidate bases, best first (ties keep candidate order)."""
    scores = [
        score_candidate(basis, correspondences, panos, rooms, face_px=face_px)
        for basis in candidate_bases(camera_height_m=camera_height_m)
    ]
    return sorted(scores, key=lambda score: (score.mean, -score.inside_ratio))


def choose_basis(scores: Sequence[CandidateScore]) -> tuple[FaceBasis | None, str]:
    """Apply the plan 9.6 / H.5 acceptance test to scored candidates.

    The winner is the lowest-mean candidate whose triangulated midpoints are all
    inside the room.  It is accepted only when the mean is below 0.30 m and the
    next-best finite candidate is at least twice as far (the mirror check).
    """
    eligible = [score for score in scores if score.inside_ratio >= 1.0 - 1e-9]
    if not eligible:
        return None, "no candidate keeps every triangulated point inside the room polygon"
    eligible.sort(key=lambda score: score.mean)
    best = eligible[0]
    if not math.isfinite(best.mean):
        return None, "no candidate produced finite triangulations"
    if best.mean >= ACCEPT_MEAN_M:
        return (
            None,
            f"best mean residual {best.mean:.3f} m is not below {ACCEPT_MEAN_M:.2f} m",
        )
    if len(eligible) >= 2:
        second = eligible[1]
    else:
        # Only one candidate keeps every midpoint inside; use the best overall
        # runner-up as the mirror check.
        runners_up = sorted(
            (score for score in scores if score is not best and math.isfinite(score.mean)),
            key=lambda score: score.mean,
        )
        if not runners_up:
            return None, "there is no second candidate to compare against"
        second = runners_up[0]
    if best.mean <= 1e-9 and second.mean <= 1e-9:
        return None, "two candidates fit the correspondences equally well (ambiguous)"
    if second.mean < ACCEPT_RATIO * best.mean:
        return (
            None,
            f"second-best mean {second.mean:.3f} m is less than "
            f"{ACCEPT_RATIO:.0f}x the best {best.mean:.3f} m",
        )
    return best.basis, "accepted"


def read_points_csv(path: Path) -> list[tuple[Correspondence, Correspondence]]:
    """Read a points CSV grouped by ``point_id`` (exactly two rows per id)."""
    rows: dict[str, list[Correspondence]] = {}
    order: list[str] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"pano", "face", "u", "v", "point_id"}
        if reader.fieldnames is None or not required.issubset(
            {name.strip() for name in reader.fieldnames}
        ):
            raise ValueError(
                "points.csv must have columns pano,face,u,v,point_id"
            )
        for raw in reader:
            point_id = (raw.get("point_id") or "").strip()
            if not point_id:
                raise ValueError("every points.csv row needs a point_id")
            item = Correspondence(
                pano_id=(raw.get("pano") or "").strip(),
                face=int(str(raw.get("face") or "0").strip()),
                u=float(str(raw.get("u") or "nan").strip()),
                v=float(str(raw.get("v") or "nan").strip()),
                point_id=point_id,
            )
            if not point_id or not item.pano_id:
                raise ValueError("points.csv rows need a panorama id and point id")
            if not (1 <= item.face <= 4):
                raise ValueError(f"face must be 1 to 4 for point {point_id}")
            if point_id not in rows:
                rows[point_id] = []
                order.append(point_id)
            rows[point_id].append(item)
    pairs: list[tuple[Correspondence, Correspondence]] = []
    for point_id in order:
        group = rows[point_id]
        if len(group) != 2:
            raise ValueError(
                f"point {point_id} has {len(group)} rows; exactly two are required"
            )
        pairs.append((group[0], group[1]))
    if len(pairs) < 3:
        raise ValueError("at least 3 point correspondences are required")
    return pairs


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m wattwalk.spatial.calibrate",
        description="Calibrate the skybox face basis from point correspondences.",
    )
    parser.add_argument("--sid", required=True, help="Matterport model id (or fixtureUnitA)")
    parser.add_argument("--pano-a", help="first panorama id (saves its horizon faces)")
    parser.add_argument("--pano-b", help="second panorama id (saves its horizon faces)")
    parser.add_argument("--points", type=Path, help="CSV of point correspondences")
    parser.add_argument("--geometry", type=Path, help="ModelGeometry JSON to use")
    parser.add_argument("--face-px", type=int, default=DEFAULT_FACE_PX, choices=(2048, 4096))
    parser.add_argument("--out", type=Path, default=FACE_BASIS_PATH, help="face_basis.json to write")
    parser.add_argument("--faces-dir", type=Path, help="where to save horizon faces")
    parser.add_argument("--no-write", action="store_true", help="score only; never write a basis")
    parser.add_argument(
        "--json",
        action="store_true",
        help="also print the candidate table as JSON for tooling",
    )
    args = parser.parse_args(argv)

    geometry = _load_geometry(args.sid, args.geometry)
    panos = {pano.id: pano for pano in geometry.panos}
    rooms = list(geometry.rooms)

    faces_dir = args.faces_dir or _default_faces_dir(args.sid)
    if args.pano_a and args.pano_b and not args.points:
        _save_horizon_faces(args.sid, [args.pano_a, args.pano_b], faces_dir)
        print(
            "Saved horizon faces to "
            f"{faces_dir}.\n"
            "Mark at least 3 physical points that appear in two faces and save a CSV "
            "with columns pano,face,u,v,point_id (two rows per point id), then run:\n"
            f"  python -m wattwalk.spatial.calibrate --sid {args.sid} --points points.csv"
        )
        return 0

    if not args.points:
        parser.error("provide --points points.csv (or --pano-a and --pano-b to save faces)")

    pairs = read_points_csv(args.points)
    scores = evaluate_candidates(
        pairs, panos, rooms, face_px=args.face_px
    )

    print(f"{'candidate':>9}  {'mean_m':>8}  {'inside':>7}  basis")
    for index, score in enumerate(scores):
        print(
            f"{index:>9}  {score.mean:>8.3f}  {score.inside_ratio:>7.3f}  "
            f"{_basis_label(score.basis)}"
        )

    if args.json:
        payload = [
            {
                "candidate": index,
                "mean_m": None if not math.isfinite(score.mean) else round(score.mean, 4),
                "inside_ratio": round(score.inside_ratio, 4),
                "faces": {
                    str(face): {
                        "forward": list(directions.forward),
                        "right": list(directions.right),
                    }
                    for face, directions in sorted(score.basis.faces.items())
                },
            }
            for index, score in enumerate(scores)
        ]
        print(json.dumps(payload, indent=2))

    winner, verdict = choose_basis(scores)
    diagnostic = _write_diagnostic_png(args.sid, geometry, pairs, scores, args.face_px)
    if diagnostic is not None:
        print(f"Diagnostic floor plan: {diagnostic}")

    if winner is None:
        print(f"NOT ACCEPTED: {verdict}")
        print(
            "Keeping face_basis.json at status 'unverified'. Use the 2D "
            "room-centroid pin fallback (plan 9.6) and tell Person 2 that dedupe "
            "must use its same-room/same-label fallback."
        )
        return 1

    best = next(score for score in scores if score.basis is winner)
    if args.no_write:
        print(
            f"ACCEPTED (not written): mean residual {best.mean:.3f} m, second-best ratio "
            f"{_second_ratio(scores):.1f}x. face_basis.json was left unchanged."
        )
        return 0

    written = FaceBasis(
        status="calibrated",
        camera_height_m=winner.camera_height_m,
        faces=winner.faces,
        calibrated_on=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        residual_m=round(float(best.mean), 3),
    )
    _write_basis(written, args.out)
    print(
        f"ACCEPTED: mean residual {best.mean:.3f} m, second-best ratio "
        f"{_second_ratio(scores):.1f}x. Wrote {args.out} with status 'calibrated'."
    )
    return 0


def _write_basis(basis: FaceBasis, path: Path) -> None:
    payload = {
        "status": basis.status,
        "camera_height_m": basis.camera_height_m,
        "faces": {
            str(face): {
                "forward": list(directions.forward),
                "right": list(directions.right),
                "up": list(directions.up),
            }
            for face, directions in sorted(basis.faces.items())
        },
        "calibrated_on": basis.calibrated_on,
        "residual_m": basis.residual_m,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _load_geometry(sid: str, path: Path | None) -> ModelGeometry:
    if path is not None:
        return ModelGeometry.model_validate_json(Path(path).read_text(encoding="utf-8"))

    # Live adapter first when available (Person 1's module).
    try:  # pragma: no cover - depends on a live key and Person 1's module
        from wattwalk.data.matterport import get_geometry

        return get_geometry(sid)
    except Exception:
        pass

    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / "fixtures" / "live" / sid / "geometry.json",
        repo_root / "shared" / "examples" / "model_geometry.json",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        geometry = ModelGeometry.model_validate_json(candidate.read_text(encoding="utf-8"))
        if candidate.name == "model_geometry.json" and geometry.sid != sid:
            continue
        return geometry
    raise SystemExit(
        f"No geometry for sid {sid!r}. Pass --geometry, capture fixtures/live/{sid}/, "
        "or use --sid fixtureUnitA."
    )


def _save_horizon_faces(sid: str, pano_ids: Sequence[str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:  # pragma: no cover - needs Person 1's adapter and a live key
        from wattwalk.data.matterport import get_face_image
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "Saving faces needs backend/wattwalk/data/matterport.get_face_image "
            f"(Person 1) and live Matterport credentials: {exc}"
        ) from exc
    for pano_id in pano_ids:
        for face in HORIZON_FACES:
            source = Path(get_face_image(sid, pano_id, face, "2k"))
            destination = out_dir / f"{pano_id}_face{face}_2k.jpg"
            shutil.copyfile(source, destination)
            print(f"saved {destination}")


def _default_faces_dir(sid: str) -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "audits" / "cache" / "calibration" / sid / "faces"


def _write_diagnostic_png(
    sid: str,
    geometry: ModelGeometry,
    pairs: Sequence[tuple[Correspondence, Correspondence]],
    scores: Sequence[CandidateScore],
    face_px: int = DEFAULT_FACE_PX,
) -> Path | None:
    """Draw room polygons, panoramas and triangulated points with Pillow."""
    try:
        from PIL import Image, ImageDraw
    except Exception:  # pragma: no cover - Pillow is in requirements
        return None
    if not scores or not math.isfinite(scores[0].mean):
        return None
    best = scores[0]
    panos = {pano.id: pano for pano in geometry.panos}
    points: list[tuple[float, float]] = []
    for first, second in pairs:
        origin_a = _pano_position(panos, first.pano_id)
        origin_b = _pano_position(panos, second.pano_id)
        if origin_a is None or origin_b is None:
            continue
        point_a, point_b = _closest_points(
            origin_a,
            pixel_ray(best.basis, first.face, first.u, first.v, face_px),
            origin_b,
            pixel_ray(best.basis, second.face, second.u, second.v, face_px),
        )
        if point_a is not None and point_b is not None:
            midpoint = (point_a + point_b) / 2.0
            points.append((float(midpoint[0]), float(midpoint[1])))

    xs = [float(vertex.x) for room in geometry.rooms for vertex in room.polygon]
    ys = [float(vertex.y) for room in geometry.rooms for vertex in room.polygon]
    xs.extend(x for x, _ in points)
    ys.extend(y for _, y in points)
    if not xs or not ys:
        return None
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    scale = 760.0 / span
    margin = 60.0

    def screen(x: float, y: float) -> tuple[float, float]:
        return (margin + (x - min_x) * scale, 820.0 - margin - (y - min_y) * scale)

    image = Image.new("RGB", (880, 880), (22, 27, 34))
    draw = ImageDraw.Draw(image)
    for room in geometry.rooms:
        polygon = [screen(float(v.x), float(v.y)) for v in room.polygon]
        if len(polygon) >= 2:
            draw.line(polygon + [polygon[0]], fill=(94, 129, 172), width=2)
    for pano in geometry.panos:
        px, py = screen(float(pano.position.x), float(pano.position.y))
        draw.ellipse((px - 5, py - 5, px + 5, py + 5), fill=(136, 192, 208))
        draw.text((px + 7, py - 7), pano.id, fill=(216, 222, 233))
    for x, y in points:
        px, py = screen(x, y)
        draw.ellipse((px - 6, py - 6, px + 6, py + 6), outline=(191, 97, 106), width=3)
    draw.text(
        (16, 16),
        f"{sid}: best residual {best.mean:.3f} m, inside {best.inside_ratio:.2f}",
        fill=(236, 239, 244),
    )

    repo_root = Path(__file__).resolve().parents[3]
    target = repo_root / "audits" / "cache" / "calibration" / f"{sid}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    return target


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #


def _rotate_z(
    vector: tuple[float, float, float], degrees: float
) -> tuple[float, float, float]:
    radians = math.radians(degrees)
    cos, sin = math.cos(radians), math.sin(radians)
    x, y, z = vector
    return (_snap(x * cos - y * sin), _snap(x * sin + y * cos), _snap(z))


def _snap(value: float) -> float:
    """Drop trigonometric noise so quarter turns produce exact axes."""
    if abs(value) < 1e-12:
        return 0.0
    if abs(value - 1.0) < 1e-12:
        return 1.0
    if abs(value + 1.0) < 1e-12:
        return -1.0
    return value


def _basis_label(basis: FaceBasis) -> str:
    forward = basis.faces[1].forward
    right = basis.faces[1].right
    return f"f1=({forward[0]:.0f},{forward[1]:.0f}) r=({right[0]:.0f},{right[1]:.0f})"


def _second_ratio(scores: Sequence[CandidateScore]) -> float:
    eligible = sorted(
        (score for score in scores if score.inside_ratio >= 1.0 - 1e-9),
        key=lambda score: score.mean,
    )
    if len(eligible) >= 2:
        best, second = eligible[0], eligible[1]
    else:
        finite = sorted(
            (score for score in scores if math.isfinite(score.mean)),
            key=lambda score: score.mean,
        )
        if len(finite) < 2:
            return math.inf
        best, second = finite[0], finite[1]
    if best.mean <= 1e-12:
        return math.inf
    return second.mean / best.mean


def _as_pairs(
    correspondences: Sequence[Correspondence]
    | Sequence[tuple[Correspondence, Correspondence]],
) -> list[tuple[Correspondence, Correspondence]]:
    if not correspondences:
        return []
    first = correspondences[0]
    if isinstance(first, tuple) and len(first) == 2:
        return [(_to_corr(a), _to_corr(b)) for a, b in correspondences]  # type: ignore[misc]
    grouped: dict[str, list[Correspondence]] = {}
    order: list[str] = []
    for item in correspondences:  # type: ignore[assignment]
        corr = _to_corr(item)
        key = corr.point_id
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(corr)
    pairs: list[tuple[Correspondence, Correspondence]] = []
    for key in order:
        group = grouped[key]
        if len(group) >= 2:
            pairs.append((group[0], group[1]))
    return pairs


def _to_corr(value) -> Correspondence:
    if isinstance(value, Correspondence):
        return value
    if isinstance(value, (tuple, list)) and len(value) == 4:
        pano_id, face, u, v = value
        return Correspondence(str(pano_id), int(face), float(u), float(v))
    raise TypeError(f"cannot interpret correspondence {value!r}")


def _pano_position(
    panos: Mapping[str, Pano] | Sequence[Pano], pano_id: str
) -> np.ndarray | None:
    if isinstance(panos, Mapping):
        pano = panos.get(pano_id)
    else:
        pano = next((item for item in panos if item.id == pano_id), None)
    if pano is None:
        return None
    return np.asarray(
        [float(pano.position.x), float(pano.position.y), float(pano.position.z)]
    )


def _closest_points(
    origin_a: np.ndarray,
    direction_a: np.ndarray,
    origin_b: np.ndarray,
    direction_b: np.ndarray,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Closest approach of two rays; reject when either parameter is behind."""
    w0 = origin_a - origin_b
    b = float(np.dot(direction_a, direction_b))
    d = float(np.dot(direction_a, w0))
    e = float(np.dot(direction_b, w0))
    denominator = 1.0 - b * b
    if abs(denominator) < 1e-12:  # parallel
        return None, None
    sc = (b * e - d) / denominator
    tc = (e - b * d) / denominator
    if sc <= 0.0 or tc <= 0.0:
        return None, None
    point_a = origin_a + sc * direction_a
    point_b = origin_b + tc * direction_b
    return point_a, point_b


def _inside_any(
    x: float,
    y: float,
    rooms: Sequence[Room] | Sequence[Sequence[Vec2] | Sequence[Sequence[float]]],
) -> bool:
    for room in rooms:
        if isinstance(room, Room):
            polygon = [(float(v.x), float(v.y)) for v in room.polygon]
        else:
            polygon = []
            for vertex in room:  # type: ignore[union-attr]
                if isinstance(vertex, Vec2):
                    polygon.append((float(vertex.x), float(vertex.y)))
                else:
                    polygon.append((float(vertex[0]), float(vertex[1])))
        if _point_in_polygon(x, y, polygon):
            return True
    return False


def _point_in_polygon(x: float, y: float, polygon: Sequence[tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = (yi > y) != (yj > y) and x < (
            (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


if __name__ == "__main__":
    sys.exit(main())
