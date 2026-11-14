/**
 * 3D readiness preflight (P4-5).
 *
 * `no_key`  - no VITE_MATTERPORT_SDK_KEY in this build; the 3D pin view is disabled.
 * `checking` - the key exists but this model has not connected yet in this session.
 * `ready`   - the SDK connected once for this model (cached in sessionStorage per sid).
 * `failed`  - the connection failed; the reason is shown and 2D stays the default.
 */
import { SDK_KEY } from "./sdkAdapter";

export type SdkReadiness =
  | { kind: "no_key" }
  | { kind: "checking" }
  | { kind: "ready" }
  | { kind: "failed"; reason: string };

const STORAGE_PREFIX = "wattwalk.sdk.ready.";

export function hasSdkKey(): boolean {
  return SDK_KEY.length > 0;
}

export function isSdkReadyFor(sid: string): boolean {
  try {
    return window.sessionStorage.getItem(`${STORAGE_PREFIX}${sid}`) === "1";
  } catch {
    // Private mode or a blocked storage API: treat it as not yet connected.
    return false;
  }
}

export function rememberSdkReady(sid: string): void {
  try {
    window.sessionStorage.setItem(`${STORAGE_PREFIX}${sid}`, "1");
  } catch {
    // Storage is an optimisation only; the viewer still works without it.
  }
}

export function forgetSdkReady(sid: string): void {
  try {
    window.sessionStorage.removeItem(`${STORAGE_PREFIX}${sid}`);
  } catch {
    // Ignore.
  }
}

export function initialSdkReadiness(sid: string): SdkReadiness {
  if (!hasSdkKey()) return { kind: "no_key" };
  if (sid && isSdkReadyFor(sid)) return { kind: "ready" };
  return { kind: "checking" };
}

export function sdkNoKeyTooltip(): string {
  return "3D pins need a Matterport SDK key (VITE_MATTERPORT_SDK_KEY)";
}
