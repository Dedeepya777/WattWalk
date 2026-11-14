/**
 * Model API frame -> Showcase SDK frame, fitted per model at runtime (plan 9.7).
 *
 * Both frames know every panorama: the Model API gives `pano.position` (z up) and the SDK gives each
 * sweep's position (y up) under the same id.  The two frames differ by an axis swap/flip and an
 * offset, so we try all 48 signed axis permutations, take the offset as the mean difference, and
 * keep the fit with the smallest residual.  The residual is the acceptance test: pins are placed
 * only when the panoramas line up within MAX_RESIDUAL_M.
 *
 * Pure functions, no React or SDK imports.
 */
import type { Vec3 } from "../contracts";

export const MAX_RESIDUAL_M = 0.1;
export const MIN_PAIRS = 3;

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
  pairs: number;
}

const PERMUTATIONS: [number, number, number][] = [
  [0, 1, 2],
  [0, 2, 1],
  [1, 0, 2],
  [1, 2, 0],
  [2, 0, 1],
  [2, 1, 0],
];

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

/** Best fit, or null with fewer than MIN_PAIRS matched panoramas. */
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
