/**
 * Showcase SDK frame conversion (plan 9.7 and A.7).
 *
 * The SDK uses its own coordinate convention.  Until `sdk_frame.json` has
 * status "calibrated" the 3D viewer is disabled and the 2D plan is the default.
 * Never send SDK coordinates to the backend.
 */
import type { Vec3 } from "../contracts";
import sdkFrame from "./sdk_frame.json";

interface SdkFrame {
  status: string;
  calibrated_on: string | null;
  residual_m: number | null;
  matrix: number[][];
}

const frame = sdkFrame as SdkFrame;

export function isSdkFrameCalibrated(): boolean {
  return frame.status === "calibrated";
}

export const sdkFrameStatus = frame.status;
export const sdkFrameResidual = frame.residual_m;

export function toSdk(v: Vec3): { x: number; y: number; z: number } {
  if (!isSdkFrameCalibrated()) {
    throw new Error(
      "Showcase SDK frame is not calibrated; use the 2D floor plan (plan 9.7).",
    );
  }
  const m = frame.matrix;
  return {
    x: m[0][0] * v.x + m[0][1] * v.y + m[0][2] * v.z,
    y: m[1][0] * v.x + m[1][1] * v.y + m[1][2] * v.z,
    z: m[2][0] * v.x + m[2][1] * v.y + m[2][2] * v.z,
  };
}
