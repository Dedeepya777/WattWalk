/**
 * Thin wrapper over the Matterport Showcase SDK (embed flavour): load the loader script once,
 * connect to a tour iframe, read sweeps, and add/remove tags.  Feature-detects the newer `Tag`
 * namespace and falls back to the older `Mattertag` one.  The SDK object is untyped here on purpose:
 * we use a handful of calls and the published typings are a separate package.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import type { Vec3 } from "../contracts";

export const SDK_SCRIPT_URL = "https://static.matterport.com/showcase-sdk/latest.js";
export const SDK_KEY: string = (import.meta.env.VITE_MATTERPORT_SDK_KEY ?? "").trim();

export type MpSdk = any;

let scriptPromise: Promise<void> | null = null;

export function loadSdkScript(): Promise<void> {
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
export async function connectSdk(iframe: HTMLIFrameElement, key: string, timeoutMs = 45_000): Promise<MpSdk> {
  await loadSdkScript();
  const connect = (window as any).MP_SDK.connect(iframe, key, "") as Promise<MpSdk>;
  const sdk = await withTimeout(connect, timeoutMs, "The SDK did not answer (check the SDK key and its allowed domains).");
  if (sdk.App?.state?.waitUntil && sdk.App?.Phase) {
    await withTimeout(
      sdk.App.state.waitUntil((state: any) => state.phase === sdk.App.Phase.PLAYING),
      timeoutMs,
      "The tour did not finish loading.",
    );
  }
  return sdk;
}

export interface SdkSweep {
  ids: string[];
  position: Vec3;
}

/** Every sweep with all its identifiers (key, id, sid, uuid) so they can be matched to pano ids. */
export function readSweeps(sdk: MpSdk, timeoutMs = 20_000): Promise<SdkSweep[]> {
  return withTimeout(
    new Promise((resolve) => {
      let sub: any = null;
      sub = sdk.Sweep.data.subscribe({
        onCollectionUpdated(collection: Record<string, any>) {
          const sweeps = Object.entries(collection)
            .filter(([, s]) => s && s.position)
            .map(([key, s]) => ({
              ids: [key, s.id, s.sid, s.uuid].filter((v): v is string => typeof v === "string" && v !== ""),
              position: { x: Number(s.position.x), y: Number(s.position.y), z: Number(s.position.z) },
            }));
          if (sweeps.length > 0) {
            sub?.cancel?.();
            resolve(sweeps);
          }
        },
      });
    }),
    timeoutMs,
    "The SDK did not report any panoramas.",
  );
}

export interface TagSpec {
  label: string;
  description: string;
  anchorPosition: Vec3;
  stemVector: Vec3;
  color: { r: number; g: number; b: number };
}

export async function addTags(sdk: MpSdk, specs: TagSpec[]): Promise<string[]> {
  if (specs.length === 0) return [];
  if (sdk.Tag?.add) return (await sdk.Tag.add(...specs)) as string[];
  return (await sdk.Mattertag.add(specs)) as string[];
}

export async function removeTags(sdk: MpSdk, ids: string[]): Promise<void> {
  if (ids.length === 0) return;
  try {
    if (sdk.Tag?.remove) await sdk.Tag.remove(...ids);
    else await sdk.Mattertag.remove(ids);
  } catch {
    // The tour may already be gone (model switched); nothing to clean up.
  }
}

/** Call `onSelect(tagId)` when the user opens a tag. Returns an unsubscribe function. */
export function onTagSelected(sdk: MpSdk, onSelect: (tagId: string) => void): () => void {
  if (sdk.Tag?.openTags?.subscribe) {
    const sub = sdk.Tag.openTags.subscribe({
      onChanged(state: any) {
        const selected = state?.selected;
        const first = selected instanceof Set ? [...selected][0] : Array.isArray(selected) ? selected[0] : null;
        if (typeof first === "string") onSelect(first);
      },
    });
    return () => sub?.cancel?.();
  }
  if (sdk.Mattertag?.Event?.CLICK && sdk.on) {
    const handler = (tagId: string) => onSelect(tagId);
    sdk.on(sdk.Mattertag.Event.CLICK, handler);
    return () => sdk.off?.(sdk.Mattertag.Event.CLICK, handler);
  }
  return () => undefined;
}

/** Fly the camera to a tag (best effort). */
export async function goToTag(sdk: MpSdk, tagId: string): Promise<void> {
  try {
    if (sdk.Tag?.dock) await sdk.Tag.dock(tagId);
    else if (sdk.Mattertag?.navigateToTag) await sdk.Mattertag.navigateToTag(tagId, sdk.Mattertag.Transition?.FLY);
  } catch {
    // Navigation is a convenience; ignore failures (e.g. tag removed mid-flight).
  }
}

/** SDK errors embed the application key ("<key>@<page> - reason"); keep only the reason. */
export function sdkErrorText(error: unknown, key = SDK_KEY): string {
  let text = error instanceof Error ? error.message : String(error);
  if (key) text = text.split(key).join("[key]");
  const reason = text.split(" - ").pop()?.trim();
  if (/referrer mismatch/i.test(text)) {
    return `this SDK key is not allowed on ${window.location.host}. Add it to the key's allowed domains in Matterport (Settings > Developer Tools).`;
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
