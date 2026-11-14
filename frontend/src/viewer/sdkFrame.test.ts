import { describe, expect, it } from "vitest";
import type { Vec3 } from "../contracts";
import {
  AMBIGUITY_RATIO,
  MAX_RESIDUAL_M,
  MIN_COVERAGE,
  alignFrames,
  candidateMatrices,
  fitFrame,
  fitIsGood,
  matchPanoramasById,
  normalizePanoId,
  pointsAreCollinear,
  type FramePair,
  type PanoLike,
  type SdkFrameFit,
  type SweepLike,
} from "./sdkFrame";

interface Transform {
  matrix: number[][];
  apply: (value: Vec3) => Vec3;
}

const OFFSET: Vec3 = { x: 12.5, y: -4.25, z: 2.75 };

const TRANSFORMS: Record<string, Transform> = {
  identity: {
    matrix: [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ],
    apply: (value) => ({ ...value }),
  },
  "z-up to y-up": {
    matrix: [
      [1, 0, 0],
      [0, 0, 1],
      [0, -1, 0],
    ],
    apply: (value) => ({ x: value.x, y: value.z, z: -value.y }),
  },
  "mirrored z": {
    matrix: [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, -1],
    ],
    apply: (value) => ({ x: value.x, y: value.y, z: -value.z }),
  },
  "quarter turn": {
    matrix: [
      [0, -1, 0],
      [1, 0, 0],
      [0, 0, 1],
    ],
    apply: (value) => ({ x: -value.y, y: value.x, z: value.z }),
  },
};

// Eight panoramas spread over a floor plan (Model API frame: z up, metres).
const MODEL_PANOS: Vec3[] = [
  { x: 0.0, y: 0.0, z: 1.5 },
  { x: 3.2, y: 0.4, z: 1.5 },
  { x: 6.1, y: 1.2, z: 1.4 },
  { x: 1.0, y: 4.5, z: 1.5 },
  { x: 5.4, y: 5.0, z: 1.6 },
  { x: 8.2, y: 3.3, z: 1.5 },
  { x: 2.1, y: 8.1, z: 1.4 },
  { x: 7.0, y: 8.4, z: 1.5 },
];

function add(a: Vec3, b: Vec3): Vec3 {
  return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z };
}

function makeRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x1_0000_0000;
  };
}

function gaussian(random: () => number): number {
  let u = 0;
  let v = 0;
  while (u === 0) u = random();
  while (v === 0) v = random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function noisy(value: Vec3, sigma: number, random: () => number): Vec3 {
  return {
    x: value.x + gaussian(random) * sigma,
    y: value.y + gaussian(random) * sigma,
    z: value.z + gaussian(random) * sigma,
  };
}

function makePairs(
  transform: Transform,
  sigma = 0,
  seed = 1,
): FramePair[] {
  const random = makeRandom(seed);
  return MODEL_PANOS.map((position, index) => ({
    id: `p${index}`,
    model: position,
    sdk:
      sigma > 0
        ? noisy(add(transform.apply(position), OFFSET), sigma, random)
        : add(transform.apply(position), OFFSET),
  }));
}

function asPanos(): PanoLike[] {
  return MODEL_PANOS.map((position, index) => ({ id: `p${index}`, position }));
}

function asSweeps(transform: Transform, ids: "shuffled" | "matching" = "shuffled"): SweepLike[] {
  return MODEL_PANOS.map((position, index) => ({
    ids: ids === "matching" ? [`p${index}`] : [`sweep-${index}`],
    fields: ids === "matching" ? { sid: `P-${index}` } : { id: `uuid-${index}` },
    position: add(transform.apply(position), OFFSET),
  }));
}

function determinant(m: number[][]): number {
  return (
    m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
    m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
    m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
  );
}

describe("fitFrame", () => {
  it.each(Object.entries(TRANSFORMS))(
    "recovers the %s transform and offset with no noise",
    (_name, transform) => {
      const fit = fitFrame(makePairs(transform));
      expect(fit).not.toBeNull();
      const result = fit as SdkFrameFit;
      expect(result.residualM).toBeLessThan(0.001);
      expect(result.matrix).toEqual(transform.matrix);
      expect(result.offset.x).toBeCloseTo(OFFSET.x, 6);
      expect(result.offset.y).toBeCloseTo(OFFSET.y, 6);
      expect(result.offset.z).toBeCloseTo(OFFSET.z, 6);
    },
  );

  it("still accepts 0.03 m Gaussian noise", () => {
    const fit = fitFrame(makePairs(TRANSFORMS["z-up to y-up"], 0.03));
    expect(fitIsGood(fit)).toBe(true);
    expect((fit as SdkFrameFit).residualM).toBeLessThan(MAX_RESIDUAL_M);
  });

  it("rejects 0.3 m Gaussian noise at the residual gate", () => {
    const fit = fitFrame(makePairs(TRANSFORMS["z-up to y-up"], 0.3, 7));
    expect(fit).not.toBeNull();
    expect(fitIsGood(fit)).toBe(false);
    expect((fit as SdkFrameFit).residualM).toBeGreaterThan(MAX_RESIDUAL_M);
  });

  it("returns null with fewer than three pairs and alignFrames never throws", () => {
    const pairs = makePairs(TRANSFORMS.identity).slice(0, 2);
    expect(fitFrame(pairs)).toBeNull();
    const result = alignFrames(
      asPanos().slice(0, 2),
      asSweeps(TRANSFORMS.identity).slice(0, 2),
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("not_enough_points");
  });
});

describe("alignment strategies", () => {
  it("uses id matching when enough normalised ids match", () => {
    const panos: PanoLike[] = [
      { id: "P-001", position: MODEL_PANOS[0] },
      { id: "P 002", position: MODEL_PANOS[1] },
      { id: "p003", position: MODEL_PANOS[2] },
    ];
    const sweeps: SweepLike[] = [
      { ids: ["sweep-a"], fields: { sid: "p001" }, position: MODEL_PANOS[0] },
      { ids: ["sweep-b"], fields: { key: "P 002" }, position: MODEL_PANOS[1] },
      { ids: ["sweep-c"], fields: { uuid: "p003" }, position: MODEL_PANOS[2] },
    ];
    expect(normalizePanoId(" P-001 ")).toBe("p001");
    const matched = matchPanoramasById(panos, sweeps);
    expect(matched.pairs).toHaveLength(3);
    expect(matched.fields.sid).toBe(1);

    const result = alignFrames(panos, sweeps);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.strategy).toBe("id");
      expect(result.assigned).toBe(3);
      expect(result.fit.residualM).toBeLessThan(0.001);
    }
  });

  it("recovers the transform by position when no ids match", () => {
    const result = alignFrames(asPanos(), asSweeps(TRANSFORMS["z-up to y-up"]));
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.strategy).toBe("position");
      expect(result.assigned).toBe(MODEL_PANOS.length);
      expect(result.coverage).toBe(1);
      expect(result.fit.residualM).toBeLessThan(0.001);
      expect(result.fit.matrix).toEqual(TRANSFORMS["z-up to y-up"].matrix);
      expect(result.secondBestRatio).toBeGreaterThanOrEqual(AMBIGUITY_RATIO);
    }
  });

  it("rejects a perfectly symmetric square as ambiguous", () => {
    const square: Vec3[] = [
      { x: 0, y: 0, z: 1.5 },
      { x: 4, y: 0, z: 1.5 },
      { x: 4, y: 4, z: 1.5 },
      { x: 0, y: 4, z: 1.5 },
    ];
    const panos = square.map((position, index) => ({ id: `p${index}`, position }));
    const sweeps = square.map((position, index) => ({
      ids: [`sweep-${index}`],
      position: add(position, OFFSET),
    }));
    const result = alignFrames(panos, sweeps);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toBe("ambiguous");
      expect(result.secondBestRatio).toBeLessThan(AMBIGUITY_RATIO);
    }
  });

  it("keeps 20% extra SDK sweeps and counts coverage against the smaller set", () => {
    const panos = asPanos();
    const sweeps: SweepLike[] = [
      ...asSweeps(TRANSFORMS.identity),
      // Two extra sweeps with no Model API counterpart, inside the same layout and frame.
      { ids: ["extra-1"], position: add({ x: 2.0, y: 2.0, z: 1.5 }, OFFSET) },
      { ids: ["extra-2"], position: add({ x: 6.0, y: 6.0, z: 1.5 }, OFFSET) },
    ];
    expect(sweeps.length).toBe(Math.round(panos.length * 1.2));

    const result = alignFrames(panos, sweeps);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.strategy).toBe("position");
      expect(result.assigned).toBe(panos.length);
      expect(result.coverage).toBeGreaterThanOrEqual(MIN_COVERAGE);
      expect(result.coverage).toBe(1);
    }
  });

  it("rejects collinear panoramas with a clear reason", () => {
    const line: Vec3[] = [
      { x: 0, y: 0, z: 1.5 },
      { x: 2, y: 0, z: 1.5 },
      { x: 4, y: 0, z: 1.5 },
      { x: 6, y: 0, z: 1.5 },
    ];
    expect(pointsAreCollinear(line)).toBe(true);
    const panos = line.map((position, index) => ({ id: `p${index}`, position }));
    const sweeps = line.map((position, index) => ({
      ids: [`p${index}`],
      position: add(position, OFFSET),
    }));
    const result = alignFrames(panos, sweeps);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toBe("collinear");
      expect(result.message).toMatch(/one line|cannot be determined/i);
    }
  });
});

describe("candidate matrices", () => {
  it("has 48 distinct signed axis permutations with determinant +1 or -1", () => {
    const matrices = candidateMatrices();
    expect(matrices).toHaveLength(48);
    const keys = new Set(matrices.map((matrix) => matrix.flat().join(",")));
    expect(keys.size).toBe(48);
    for (const matrix of matrices) {
      expect(Math.abs(determinant(matrix))).toBeCloseTo(1, 12);
    }
    expect(candidateMatrices(true)).toHaveLength(24);
  });
});
