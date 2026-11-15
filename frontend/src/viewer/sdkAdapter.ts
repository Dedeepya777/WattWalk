/**
 * Adapter for every Matterport Showcase SDK call the 3D viewer makes.
 *
 * The SDK is loaded from a script tag and its object is intentionally untyped here.  Each adapter
 * function has one job, returns a typed result instead of throwing, and logs a single clear message
 * on failure.  A signature change in the SDK (for example a different `Tag.add` shape) only needs a
 * change in this file.
 *
 * API checked against the Matterport Showcase SDK reference (2026-11):
 *  - MP_SDK.connect(iframe, key, version): Promise<MpSdk>  (version is a string; we pass "")
 *  - Sweep.data.subscribe({ onCollectionUpdated })
 *  - Tag.add(...descriptors): Promise<string[]>
 *  - Tag.remove(...ids): Promise<string[]>
 *  - Tag.openTags.subscribe({ onChanged }): selected is a Set<string>
 *  - Mattertag.navigateToTag(id, transition): Promise<string>
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import type { Vec3 } from "../contracts";

export const SDK_SCRIPT_URL = "https://static.matterport.com/showcase-sdk/latest.js";
export const SDK_KEY: string = (import.meta.env.VITE_MATTERPORT_SDK_KEY ?? "").trim();
export const SDK_CONNECT_TIMEOUT_MS = 15_000;

export type MpSdk = any;

export type SdkResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: string };

function ok<T>(value: T): SdkResult<T> {
  return { ok: true, value };
}

function fail<T>(operation: string, error: unknown): SdkResult<T> {
  const message = sdkErrorText(error);
  // One log line per failed call; the key is scrubbed by sdkErrorText.
  console.error(`[wattwalk:3d] ${operation}: ${message}`);
  return { ok: false, error: message };
}

let scriptPromise: Promise<void> | null = null;

function loadSdkScript(): Promise<void> {
  if ((window as any).MP_SDK) return Promise.resolve();
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SDK_SCRIPT_URL;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        scriptPromise = null;
        reject(new Error("Could not load the Matterport SDK script."));
      };
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
}

/** Connect to the iframe and wait until the tour is playing. */
export async function connectSdk(
  iframe: HTMLIFrameElement,
  key: string,
  timeoutMs = SDK_CONNECT_TIMEOUT_MS,
): Promise<SdkResult<MpSdk>> {
  try {
    // Time the whole sequence, including loading the SDK script; a blocked script must not leave
    // the tab spinning forever.
    const sdk = await withTimeout(
      (async () => {
        await loadSdkScript();
        const value = await ((window as any).MP_SDK.connect(iframe, key, "") as Promise<MpSdk>);
        if (value.App?.state?.waitUntil && value.App?.Phase) {
          await value.App.state.waitUntil(
            (state: any) => state.phase === value.App.Phase.PLAYING,
          );
        }
        return value;
      })(),
      timeoutMs,
      "The SDK did not answer (check the SDK key and its allowed domains).",
    );
    return ok(sdk);
  } catch (error) {
    return fail("connect", error);
  }
}

export interface SdkSweep {
  ids: string[];
  fields: Partial<Record<"key" | "id" | "sid" | "uuid", string>>;
  position: Vec3;
}

/** Every sweep with all its identifiers (key, id, sid, uuid) so they can be matched to pano ids. */
export async function readSweeps(
  sdk: MpSdk,
  timeoutMs = 20_000,
): Promise<SdkResult<SdkSweep[]>> {
  try {
    if (!sdk.Sweep?.data?.subscribe) {
      throw new Error("This SDK version does not expose Sweep.data.subscribe.");
    }
    const sweeps = await withTimeout(
      new Promise<SdkSweep[]>((resolve) => {
        let sub: any = null;
        sub = sdk.Sweep.data.subscribe({
          onCollectionUpdated(collection: Record<string, any>) {
            const items = Object.entries(collection)
              .filter(([, sweep]) => sweep && sweep.position)
              .map(([key, sweep]) => {
                const fields: SdkSweep["fields"] = {};
                if (typeof key === "string" && key) fields.key = key;
                for (const field of ["id", "sid", "uuid"] as const) {
                  const value = sweep[field];
                  if (typeof value === "string" && value) fields[field] = value;
                }
                const ids = Object.values(fields).filter(
                  (value): value is string => typeof value === "string" && value !== "",
                );
                return {
                  ids,
                  fields,
                  position: {
                    x: Number(sweep.position.x),
                    y: Number(sweep.position.y),
                    z: Number(sweep.position.z),
                  },
                };
              });
            if (items.length > 0) {
              sub?.cancel?.();
              resolve(items);
            }
          },
        });
      }),
      timeoutMs,
      "The SDK did not report any panoramas.",
    );
    return ok(sweeps);
  } catch (error) {
    return fail("read sweeps", error);
  }
}

export interface TagSpec {
  label: string;
  description: string;
  anchorPosition: Vec3;
  stemVector: Vec3;
  color: { r: number; g: number; b: number };
  /** 0 hides the pin's disc (the heat glow marks the item instead). */
  opacity?: number;
  /** false hides the pin's stem. */
  stemVisible?: boolean;
}

export async function addTags(
  sdk: MpSdk,
  specs: TagSpec[],
): Promise<SdkResult<string[]>> {
  if (specs.length === 0) return ok([]);
  try {
    let ids: unknown;
    // Tags 2.0: spread one descriptor per argument.  Mattertag fallback: one array argument.
    if (sdk.Tag?.add) ids = await sdk.Tag.add(...specs);
    else if (sdk.Mattertag?.add) ids = await sdk.Mattertag.add(specs);
    else throw new Error("This SDK version has neither Tag.add nor Mattertag.add.");
    if (!Array.isArray(ids) || ids.some((id) => typeof id !== "string")) {
      throw new Error("The SDK did not return the new tag ids.");
    }
    // Clicking a pin must not move or zoom the camera; only our pop-out opens.
    for (const id of ids as string[]) {
      try {
        void sdk.Tag?.allowAction?.(id, { navigating: false, docking: false });
      } catch {
        // older SDK: keep the default behaviour
      }
    }
    return ok(ids as string[]);
  } catch (error) {
    return fail("add tags", error);
  }
}

export async function removeTags(
  sdk: MpSdk,
  ids: string[],
): Promise<SdkResult<string[]>> {
  if (ids.length === 0) return ok([]);
  try {
    let removed: unknown;
    if (sdk.Tag?.remove) removed = await sdk.Tag.remove(...ids);
    else if (sdk.Mattertag?.remove) removed = await sdk.Mattertag.remove(ids);
    else return ok([]);
    return ok(Array.isArray(removed) ? (removed as string[]) : ids);
  } catch (error) {
    // The tour may already be gone (model switched); still report it once.
    return fail("remove tags", error);
  }
}

/** Call `onSelect(tagId)` when the user opens a tag. */
export function onTagSelected(
  sdk: MpSdk,
  onSelect: (tagId: string) => void,
): SdkResult<() => void> {
  try {
    if (sdk.Tag?.openTags?.subscribe) {
      const sub = sdk.Tag.openTags.subscribe({
        onChanged(state: any) {
          const selected = state?.selected;
          const first = selected instanceof Set
            ? [...selected][0]
            : Array.isArray(selected)
              ? selected[0]
              : null;
          if (typeof first === "string") onSelect(first);
        },
      });
      return ok(() => sub?.cancel?.());
    }
    if (sdk.Mattertag?.Event?.CLICK && sdk.on) {
      const handler = (tagId: string) => onSelect(tagId);
      sdk.on(sdk.Mattertag.Event.CLICK, handler);
      return ok(() => sdk.off?.(sdk.Mattertag.Event.CLICK, handler));
    }
    throw new Error("This SDK version has no tag click/open subscription.");
  } catch (error) {
    // Clicking is a convenience; the viewer still works without it.
    return fail<() => void>("subscribe to tag clicks", error);
  }
}

/**
 * Fly the camera to a tagged asset.
 *
 * Tags 2.0 has no navigation call, so continue to use Mattertag.navigateToTag (the documented
 * migration path); Tag.dock is only a fallback that opens the billboard.
 */
export async function goToTag(sdk: MpSdk, tagId: string): Promise<SdkResult<void>> {
  try {
    if (sdk.Mattertag?.navigateToTag) {
      const transition = sdk.Mattertag?.Transition?.FLY ?? sdk.Camera?.Transition?.FLY;
      await sdk.Mattertag.navigateToTag(tagId, transition);
      return ok(undefined);
    }
    if (sdk.Tag?.dock) {
      await sdk.Tag.dock(tagId);
      return ok(undefined);
    }
    throw new Error("This SDK version cannot navigate to a tag.");
  } catch (error) {
    return fail("navigate to tag", error);
  }
}

/** SDK errors embed the application key ("<key>@<page> - reason"); keep only the reason. */
export function sdkErrorText(error: unknown, key = SDK_KEY): string {
  let text = error instanceof Error ? error.message : String(error);
  if (key) text = text.split(key).join("[key]");
  const reason = text.split(" - ").pop()?.trim();
  if (/referrer mismatch/i.test(text)) {
    const origin = typeof window !== "undefined" ? window.location.origin : "this origin";
    return `This SDK key is not allowed for ${origin}. Add it in the Matterport key settings.`;
  }
  return reason || text;
}

function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error instanceof Error ? error : new Error(String(error)));
      },
    );
  });
}
