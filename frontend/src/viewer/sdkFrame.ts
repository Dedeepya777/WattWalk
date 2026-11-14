/**
 * Model API frame -> Showcase SDK frame, fitted per model at runtime (plan 9.7).
 *
 * Both frames know every panorama: the Model API gives `pano.position` (z up) and the SDK gives each
 * sweep's position (y up).  The two frames differ by an axis swap/flip and an offset, so we try all
 * 48 signed axis permutations and keep the fit with the smallest residual.
 *
 * Two correspondence strategies are supported:
 *  1. id matching: a Model API pano id matches one of a sweep's identifiers (key/id/sid/uuid);
 *  2. position matching: when fewer than three ids match, iteratively align the two point clouds
 *     for each candidate axis permutation (nearest sweep within 1 m, one-to-one, recentre).
 *
 * Pure functions: no React, no DOM and no SDK imports, so they run in Node under Vitest.
 */
import type { Vec3 } from "../contracts";

export const MAX_RESIDUAL_M = 0.1;
export const MIN_PAIRS = 3;
export const MIN_GEOMETRIC_PAIRS = 4;
export const MIN_COVERAGE = 0.8;
export const AMBIGUITY_RATIO = 2;
export const MAX_MATCH_DISTANCE_M = 1.0;
export const MAX_ITERATIONS = 20;
export const COLLINEAR_TOLERANCE_M = 0.05;

export interface FramePair {
  id: string;
  model: Vec3;
  sdk: Vec3;
}

export interface SdkFrameFit {
  /** Row-major 3x3: sdk = matrix * model + offset. */
  matrix: number[][];
  offset: Vec3;
  /** Root-mean-square distance between mapped and SDK panorama positions, metres. */
  residualM: number;
  /** Largest single panorama mismatch, metres. */
  maxErrorM: number;
  /** Number of panorama pairs used by the fit. */
  pairs: number;
}

export interface PanoLike {
  id: string;
  position: Vec3;
}

export type SdkIdField = "key" | "id" | "sid" | "uuid";

/** The subset of a Showcase sweep that frame fitting needs (structurally compatible with mpSdk). */
export interface SweepLike {
  ids: string[];
  /** Identifier values by source field, when the adapter knows them. */
  fields?: Partial<Record<SdkIdField, string>>;
  position: Vec3;
}

export interface IdMatchResult {
  pairs: FramePair[];
  /** Number of matched panoramas per SDK identifier field. */
  fields: Partial<Record<SdkIdField, number>>;
}

export type AlignmentStrategy = "id" | "position";

export type AlignmentFailureReason =
  | "not_enough_points"
  | "collinear"
  | "coverage"
  | "residual"
  | "ambiguous";

export interface AlignmentSuccess {
  ok: true;
  strategy: AlignmentStrategy;
  fit: SdkFrameFit;
  assigned: number;
  coverage: number;
  /** Second-best candidate residual divided by the best; Infinity when there is no runner-up. */
  secondBestRatio: number;
  /** Identifier-field counts for the id strategy. */
  fields?: Partial<Record<SdkIdField, number>>;
}

export interface AlignmentFailure {
  ok: false;
  strategy: AlignmentStrategy;
  reason: AlignmentFailureReason;
  message: string;
  fit: SdkFrameFit | null;
  assigned: number;
  coverage: number;
  secondBestRatio: number;
}

export type AlignmentResult = AlignmentSuccess | AlignmentFailure;

const PERMUTATIONS: [number, number, number][] = [
  [0, 1, 2],
  [0, 2, 1],
  [1, 0, 2],
  [1, 2, 0],
  [2, 0, 1],
  [2, 1, 0],
];

const ID_FIELDS: SdkIdField[] = ["key", "id", "sid", "uuid"];

function arr(v: Vec3): [number, number, number] {
  return [v.x, v.y, v.z];
}

function apply(matrix: number[][], v: [number, number, number]): [number, number, number] {
  return [
    matrix[0][0] * v[0] + matrix[0][1] * v[1] + matrix[0][2] * v[2],
    matrix[1][0] * v[0] + matrix[1][1] * v[1] + matrix[1][2] * v[2],
    matrix[2][0] * v[0] + matrix[2][1] * v[1] + matrix[2][2] * v[2],
  ];
}

function det(m: number[][]): number {
  return (
    m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
    m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
    m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
  );
}

function distance(a: Vec3, b: Vec3): number {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}

function centroid(points: Vec3[]): [number, number, number] {
  const sum = points.reduce<[number, number, number]>(
    (acc, point) => [acc[0] + point.x, acc[1] + point.y, acc[2] + point.z],
    [0, 0, 0],
  );
  return [sum[0] / points.length, sum[1] / points.length, sum[2] / points.length];
}

/** Every signed axis permutation; `properOnly` keeps rotations (det +1) and drops mirror images. */
export function candidateMatrices(properOnly = false): number[][][] {
  const out: number[][][] = [];
  for (const perm of PERMUTATIONS) {
    for (let signs = 0; signs < 8; signs++) {
      const m = [0, 1, 2].map((row) => {
        const r = [0, 0, 0];
        r[perm[row]] = signs & (1 << row) ? -1 : 1;
        return r;
      });
      if (!properOnly || det(m) > 0) out.push(m);
    }
  }
  return out;
}

/** Trim, lowercase and drop dashes before comparing a pano id with a sweep identifier. */
export function normalizePanoId(value: string): string {
  return value.trim().toLowerCase().replace(/-/g, "");
}

/**
 * Match Model API panoramas to SDK sweeps through any of the sweep's identifiers.
 * Returns the matched pairs and which field produced each match.
 */
export function matchPanoramasById(
  panos: PanoLike[],
  sweeps: SweepLike[],
): IdMatchResult {
  const index = new Map<string, { sweep: SweepLike; field: SdkIdField }>();
  for (const sweep of sweeps) {
    const entries: Array<[SdkIdField, string | undefined]> = [];
    if (sweep.fields) {
      for (const field of ID_FIELDS) entries.push([field, sweep.fields[field]]);
    }
    // Keep raw ids as a fallback even when `fields` is present (older adapters only expose ids).
    for (const id of sweep.ids) entries.push(["key", id]);
    for (const [field, value] of entries) {
      if (!value) continue;
      const key = normalizePanoId(value);
      if (!index.has(key)) index.set(key, { sweep, field });
    }
  }

  const pairs: FramePair[] = [];
  const fields: Partial<Record<SdkIdField, number>> = {};
  for (const pano of panos) {
    const hit = index.get(normalizePanoId(pano.id));
    if (!hit) continue;
    pairs.push({ id: pano.id, model: pano.position, sdk: hit.sweep.position });
    fields[hit.field] = (fields[hit.field] ?? 0) + 1;
  }
  return { pairs, fields };
}

/** True when all points lie on one line (within `tolerance`), so orientation is ambiguous. */
export function pointsAreCollinear(
  points: Vec3[],
  tolerance = COLLINEAR_TOLERANCE_M,
): boolean {
  if (points.length < 3) return true;
  let a = points[0];
  let b = points[1];
  let longest = -1;
  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const d = distance(points[i], points[j]);
      if (d > longest) {
        longest = d;
        a = points[i];
        b = points[j];
      }
    }
  }
  if (longest <= tolerance) return true;
  const direction: Vec3 = { x: b.x - a.x, y: b.y - a.y, z: b.z - a.z };
  const length = Math.hypot(direction.x, direction.y, direction.z);
  if (length < 1e-9) return true;
  for (const point of points) {
    const v: Vec3 = { x: point.x - a.x, y: point.y - a.y, z: point.z - a.z };
    const crossX = v.y * direction.z - v.z * direction.y;
    const crossY = v.z * direction.x - v.x * direction.z;
    const crossZ = v.x * direction.y - v.y * direction.x;
    const offLine = Math.hypot(crossX, crossY, crossZ) / length;
    if (offLine > tolerance) return false;
  }
  return true;
}

/** Best fit for known panorama correspondences, or null with fewer than MIN_PAIRS pairs. */
export function fitFrame(pairs: FramePair[]): SdkFrameFit | null {
  if (pairs.length < MIN_PAIRS) return null;
  let best: SdkFrameFit | null = null;
  for (const matrix of candidateMatrices()) {
    const mapped = pairs.map((p) => apply(matrix, arr(p.model)));
    const offset = [0, 1, 2].map(
      (k) => pairs.reduce((sum, p, i) => sum + (arr(p.sdk)[k] - mapped[i][k]), 0) / pairs.length,
    );
    let squares = 0;
    let maxError = 0;
    pairs.forEach((p, i) => {
      const s = arr(p.sdk);
      const e = Math.hypot(
        mapped[i][0] + offset[0] - s[0],
        mapped[i][1] + offset[1] - s[1],
        mapped[i][2] + offset[2] - s[2],
      );
      squares += e * e;
      maxError = Math.max(maxError, e);
    });
    const residualM = Math.sqrt(squares / pairs.length);
    if (best === null || residualM < best.residualM) {
      best = {
        matrix,
        offset: { x: offset[0], y: offset[1], z: offset[2] },
        residualM,
        maxErrorM: maxError,
        pairs: pairs.length,
      };
    }
  }
  return best;
}

export function fitIsGood(fit: SdkFrameFit | null): fit is SdkFrameFit {
  return fit !== null && fit.residualM <= MAX_RESIDUAL_M;
}

export function modelToSdk(fit: SdkFrameFit, v: Vec3): Vec3 {
  const m = apply(fit.matrix, arr(v));
  return { x: m[0] + fit.offset.x, y: m[1] + fit.offset.y, z: m[2] + fit.offset.z };
}

/** A model-frame direction (no offset), e.g. "up" for a tag stem. */
export function modelDirToSdk(fit: SdkFrameFit, v: Vec3): Vec3 {
  const m = apply(fit.matrix, arr(v));
  return { x: m[0], y: m[1], z: m[2] };
}

interface CandidateScore {
  matrix: number[][];
  offset: Vec3;
  residualM: number;
  maxErrorM: number;
  assigned: number;
  coverage: number;
}

/**
 * Iterative nearest-sweep alignment for one candidate axis permutation.
 *
 * Starts from the centroid difference, then assigns each mapped pano to its nearest sweep within
 * MAX_MATCH_DISTANCE_M (one-to-one, dropping the farther duplicate) and recentres on the assigned
 * pairs.  Stops when the assignment no longer changes or after MAX_ITERATIONS.
 */
function scoreCandidate(
  matrix: number[][],
  panos: PanoLike[],
  sweeps: SweepLike[],
): CandidateScore {
  const mapped = panos.map((p) => apply(matrix, arr(p.position)));
  const modelCentre = centroid(mapped.map(([x, y, z]) => ({ x, y, z })));
  const sdkCentre = centroid(sweeps.map((sweep) => sweep.position));
  let offset: [number, number, number] = [
    sdkCentre[0] - modelCentre[0],
    sdkCentre[1] - modelCentre[1],
    sdkCentre[2] - modelCentre[2],
  ];

  let assignment = new Map<number, number>();
  let previousKey = "";
  for (let iteration = 0; iteration < MAX_ITERATIONS; iteration += 1) {
    const candidates: Array<{ model: number; sweep: number; d: number }> = [];
    for (let i = 0; i < mapped.length; i += 1) {
      for (let j = 0; j < sweeps.length; j += 1) {
        const s = sweeps[j].position;
        const d = Math.hypot(
          mapped[i][0] + offset[0] - s.x,
          mapped[i][1] + offset[1] - s.y,
          mapped[i][2] + offset[2] - s.z,
        );
        if (d <= MAX_MATCH_DISTANCE_M) candidates.push({ model: i, sweep: j, d });
      }
    }
    candidates.sort((a, b) => a.d - b.d);
    const usedModel = new Set<number>();
    const usedSweep = new Set<number>();
    const next = new Map<number, number>();
    for (const candidate of candidates) {
      if (usedModel.has(candidate.model) || usedSweep.has(candidate.sweep)) continue;
      usedModel.add(candidate.model);
      usedSweep.add(candidate.sweep);
      next.set(candidate.model, candidate.sweep);
    }

    const key = [...next.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([i, j]) => `${i}:${j}`)
      .join(",");
    assignment = next;

    if (next.size > 0) {
      const mean: [number, number, number] = [0, 0, 0];
      for (const [i, j] of next) {
        const s = sweeps[j].position;
        mean[0] += s.x - mapped[i][0];
        mean[1] += s.y - mapped[i][1];
        mean[2] += s.z - mapped[i][2];
      }
      offset = [mean[0] / next.size, mean[1] / next.size, mean[2] / next.size];
    }

    if (key === previousKey) break;
    previousKey = key;
  }

  let squares = 0;
  let maxError = 0;
  let assigned = 0;
  for (const [i, j] of assignment) {
    const s = sweeps[j].position;
    const e = Math.hypot(
      mapped[i][0] + offset[0] - s.x,
      mapped[i][1] + offset[1] - s.y,
      mapped[i][2] + offset[2] - s.z,
    );
    squares += e * e;
    maxError = Math.max(maxError, e);
    assigned += 1;
  }

  const denominator = Math.min(panos.length, sweeps.length);
  return {
    matrix,
    offset: { x: offset[0], y: offset[1], z: offset[2] },
    residualM: assigned > 0 ? Math.sqrt(squares / assigned) : Number.POSITIVE_INFINITY,
    maxErrorM: maxError,
    assigned,
    coverage: denominator > 0 ? assigned / denominator : 0,
  };
}

function ratio(best: number, second: number): number {
  if (!Number.isFinite(second)) return Number.POSITIVE_INFINITY;
  if (best <= 1e-9) return second <= 1e-9 ? 1 : Number.POSITIVE_INFINITY;
  return second / best;
}

function failure(
  strategy: AlignmentStrategy,
  reason: AlignmentFailureReason,
  message: string,
  fit: SdkFrameFit | null,
  assigned: number,
  coverage: number,
  secondBestRatio: number,
): AlignmentFailure {
  return { ok: false, strategy, reason, message, fit, assigned, coverage, secondBestRatio };
}

function fitFromScore(score: CandidateScore): SdkFrameFit {
  return {
    matrix: score.matrix,
    offset: score.offset,
    residualM: score.residualM,
    maxErrorM: score.maxErrorM,
    pairs: score.assigned,
  };
}

function alignByPosition(panos: PanoLike[], sweeps: SweepLike[]): AlignmentResult {
  if (panos.length < MIN_GEOMETRIC_PAIRS || sweeps.length < MIN_GEOMETRIC_PAIRS) {
    return failure(
      "position",
      "not_enough_points",
      `Position matching needs at least ${MIN_GEOMETRIC_PAIRS} panoramas and sweeps; found ${panos.length} and ${sweeps.length}.`,
      null,
      0,
      0,
      1,
    );
  }
  if (pointsAreCollinear(panos.map((pano) => pano.position))) {
    return failure(
      "position",
      "collinear",
      "The panoramas lie on one line, so the rotation cannot be determined.",
      null,
      0,
      0,
      1,
    );
  }

  const scores = candidateMatrices()
    .map((matrix) => scoreCandidate(matrix, panos, sweeps))
    .sort((a, b) => a.residualM - b.residualM || b.coverage - a.coverage);

  // A wrong axis permutation can converge onto two or three nearby sweeps with a near-zero RMS.
  // Prefer candidates that explain at least MIN_GEOMETRIC_PAIRS of the smaller point set and
  // MIN_COVERAGE of it; only fall back to the raw best when nothing is viable (so the failure
  // reason still describes the best attempt).
  const viable = scores.filter(
    (score) =>
      Number.isFinite(score.residualM) &&
      score.assigned >= MIN_GEOMETRIC_PAIRS &&
      score.coverage >= MIN_COVERAGE,
  );
  const best = viable[0] ?? scores[0];
  const second = viable.length >= 2 ? viable[1] : undefined;
  const bestRatio = ratio(best.residualM, second?.residualM ?? Number.POSITIVE_INFINITY);
  const bestFit = best.assigned > 0 ? fitFromScore(best) : null;

  if (best.assigned < MIN_GEOMETRIC_PAIRS) {
    return failure(
      "position",
      "not_enough_points",
      `Only ${best.assigned} panoramas could be paired by position (need ${MIN_GEOMETRIC_PAIRS}).`,
      bestFit,
      best.assigned,
      best.coverage,
      bestRatio,
    );
  }
  if (best.coverage < MIN_COVERAGE) {
    return failure(
      "position",
      "coverage",
      `Position matching covered ${(best.coverage * 100).toFixed(0)}% of panoramas (need ${Math.round(MIN_COVERAGE * 100)}%).`,
      bestFit,
      best.assigned,
      best.coverage,
      bestRatio,
    );
  }
  if (best.residualM >= MAX_RESIDUAL_M) {
    return failure(
      "position",
      "residual",
      `Panoramas differ by ${best.residualM.toFixed(2)} m (limit ${MAX_RESIDUAL_M} m).`,
      bestFit,
      best.assigned,
      best.coverage,
      bestRatio,
    );
  }
  if (bestRatio < AMBIGUITY_RATIO) {
    return failure(
      "position",
      "ambiguous",
      `Several orientations fit equally well (second-best ${bestRatio.toFixed(1)}x); the layout is symmetric.`,
      bestFit,
      best.assigned,
      best.coverage,
      bestRatio,
    );
  }

  return {
    ok: true,
    strategy: "position",
    fit: bestFit as SdkFrameFit,
    assigned: best.assigned,
    coverage: best.coverage,
    secondBestRatio: bestRatio,
  };
}

/**
 * Align the Model API panorama frame to the SDK sweep frame for one model.
 *
 * Id matching is tried first.  When fewer than MIN_PAIRS panorama ids match, the correspondence-free
 * position matcher runs.  A fit is accepted only on a 0.1 m RMS residual; the position matcher also
 * requires 80% coverage, four pairs and a 2x margin over the second-best orientation.
 */
export function alignFrames(panos: PanoLike[], sweeps: SweepLike[]): AlignmentResult {
  const matched = matchPanoramasById(panos, sweeps);
  if (matched.pairs.length >= MIN_PAIRS) {
    if (pointsAreCollinear(matched.pairs.map((pair) => pair.model))) {
      return failure(
        "id",
        "collinear",
        "The matched panoramas lie on one line, so the rotation cannot be determined.",
        null,
        matched.pairs.length,
        matched.pairs.length / Math.max(1, Math.min(panos.length, sweeps.length)),
        1,
      );
    }
    const fit = fitFrame(matched.pairs);
    const assigned = matched.pairs.length;
    const coverage = assigned / Math.max(1, Math.min(panos.length, sweeps.length));
    if (fit !== null && fit.residualM <= MAX_RESIDUAL_M) {
      return {
        ok: true,
        strategy: "id",
        fit,
        assigned,
        coverage,
        secondBestRatio: Number.POSITIVE_INFINITY,
        fields: matched.fields,
      };
    }
    return failure(
      "id",
      "residual",
      fit === null
        ? `Only ${assigned} panorama ids matched the tour (need ${MIN_PAIRS}).`
        : `Matched panoramas differ by ${fit.residualM.toFixed(2)} m (limit ${MAX_RESIDUAL_M} m).`,
      fit,
      assigned,
      coverage,
      1,
    );
  }
  return alignByPosition(panos, sweeps);
}
