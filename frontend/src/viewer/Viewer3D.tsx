/**
 * 3D tour viewer with asset pins (plan 11.3, 13.6 and 9.7).
 *
 * Without VITE_MATTERPORT_SDK_KEY this is the plain public tour.  With a key it connects the
 * Showcase SDK, fits the Model API -> SDK frame on the audit's panoramas (sdkFrame.ts), and adds
 * one tag per anchored asset.  Clicking a tag opens the evidence card; selecting an asset elsewhere
 * flies the camera to its tag.  Pins are placed only when the panoramas line up (residual check).
 * The fit is per model at runtime, so the static sdk_frame.json (coords.ts) is not needed here.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { Asset } from "../contracts";
import { FIXTURE_SID } from "../fixtures";
import { labelText, unknownAttrCount } from "../format";
import { useAppDispatch, useAppState } from "../state";
import {
  SDK_KEY,
  addTags,
  connectSdk,
  goToTag,
  onTagSelected,
  readSweeps,
  removeTags,
  sdkErrorText,
  type MpSdk,
  type TagSpec,
} from "./mpSdk";
import {
  MAX_RESIDUAL_M,
  MIN_PAIRS,
  fitFrame,
  fitIsGood,
  modelDirToSdk,
  modelToSdk,
  type FramePair,
  type SdkFrameFit,
} from "./sdkFrame";

const TOUR_URL = "https://my.matterport.com/show/";
const CEILING_LABELS = new Set(["ceiling_light", "ceiling_fan", "supply_vent"]);
const STEM_M = 0.25;
const KNOWN = { r: 0.2, g: 0.83, b: 0.6 }; // matches the 2D plan's green pins
const UNKNOWN = { r: 0.96, g: 0.62, b: 0.04 }; // and amber pins

/** Matterport model ids are 11 characters of letters and digits. */
const isModelId = (sid: string): boolean => /^[A-Za-z0-9]{11}$/.test(sid);

export function tourUrl(sid: string, applicationKey = ""): string {
  // play=1 starts the tour without a click; qs=1 starts on the first panorama (quick start)
  const params = new URLSearchParams({ m: sid, play: "1", qs: "1" });
  if (applicationKey) params.set("applicationKey", applicationKey);
  return `${TOUR_URL}?${params.toString()}`;
}

type Phase =
  | { kind: "tour-only"; note: string }
  | { kind: "connecting" }
  | { kind: "aligning" }
  | { kind: "ready"; fit: SdkFrameFit; matched: number; total: number }
  | { kind: "misaligned"; detail: string }
  | { kind: "error"; message: string };

function tagSpec(asset: Asset, fit: SdkFrameFit, roomLabel: string): TagSpec | null {
  if (!asset.anchor) return null;
  const unknown = unknownAttrCount(asset.attrs);
  const down = CEILING_LABELS.has(asset.label);
  return {
    label: labelText(asset.label),
    description: `${roomLabel}${unknown > 0 ? ` · ${unknown} unknown detail${unknown === 1 ? "" : "s"}` : ""}`,
    anchorPosition: modelToSdk(fit, asset.anchor),
    stemVector: modelDirToSdk(fit, { x: 0, y: 0, z: down ? -STEM_M : STEM_M }),
    color: unknown > 0 ? UNKNOWN : KNOWN,
  };
}

export function Viewer3D() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const { selectedSid, audit, selectedAssetId } = state;
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const sdkRef = useRef<MpSdk | null>(null);
  const tagToAsset = useRef(new Map<string, string>());
  const assetToTag = useRef(new Map<string, string>());
  const [phase, setPhase] = useState<Phase>(
    SDK_KEY ? { kind: "connecting" } : { kind: "tour-only", note: "No SDK key configured" },
  );
  const [loadedSid, setLoadedSid] = useState<string | null>(null);
  const [tagCount, setTagCount] = useState(0);

  const realModel = selectedSid !== FIXTURE_SID && isModelId(selectedSid);
  const panos = useMemo(() => audit?.panos ?? [], [audit?.panos]);
  const inventory = useMemo(() => audit?.inventory ?? [], [audit?.inventory]);
  const roomLabels = useMemo(
    () => new Map((audit?.rooms ?? []).map((room) => [room.id, room.label])),
    [audit?.rooms],
  );
  const panoKey = panos.map((p) => p.id).join(",");
  const inventoryKey = inventory
    .map((a) => `${a.id}:${a.anchor?.x},${a.anchor?.y},${a.anchor?.z}:${unknownAttrCount(a.attrs)}`)
    .join("|");
  const sdkLive = phase.kind === "aligning" || phase.kind === "ready";

  // 1. Connect the SDK once the iframe for this model has loaded.
  useEffect(() => {
    if (!SDK_KEY || !realModel || loadedSid !== selectedSid || !iframeRef.current) return undefined;
    let cancelled = false;
    setPhase({ kind: "connecting" });
    connectSdk(iframeRef.current, SDK_KEY)
      .then((sdk) => {
        if (cancelled) return;
        sdkRef.current = sdk;
        setPhase({ kind: "aligning" });
      })
      .catch((error: unknown) => {
        if (!cancelled) setPhase({ kind: "error", message: sdkErrorText(error) });
      });
    return () => {
      cancelled = true;
      sdkRef.current = null;
      tagToAsset.current.clear();
      assetToTag.current.clear();
      setTagCount(0);
    };
  }, [loadedSid, realModel, selectedSid]);

  // 2. Fit the frame from the audit's panoramas, then (re)place the tags.
  useEffect(() => {
    const sdk = sdkRef.current;
    if (!sdk || !sdkLive) return undefined;
    if (panos.length === 0) {
      setPhase({ kind: "tour-only", note: "Run the audit to see asset pins in 3D" });
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const sweeps = await readSweeps(sdk);
        const byId = new Map<string, (typeof sweeps)[number]>();
        sweeps.forEach((s) => s.ids.forEach((id) => byId.set(id, s)));
        const pairs: FramePair[] = panos
          .filter((p) => byId.has(p.id))
          .map((p) => ({ id: p.id, model: p.position, sdk: byId.get(p.id)!.position }));
        const fit = fitFrame(pairs);
        if (cancelled) return;
        if (!fitIsGood(fit)) {
          const residual = fitFrame(pairs)?.residualM;
          setPhase({
            kind: "misaligned",
            detail:
              pairs.length < MIN_PAIRS || residual === undefined
                ? `only ${pairs.length} of ${panos.length} panoramas matched the tour`
                : `panoramas differ by ${residual.toFixed(2)} m (limit ${MAX_RESIDUAL_M} m)`,
          });
          return;
        }
        await removeTags(sdk, [...tagToAsset.current.keys()]);
        tagToAsset.current.clear();
        assetToTag.current.clear();
        const placed = inventory
          .map((asset) => ({
            asset,
            spec: tagSpec(asset, fit, roomLabels.get(asset.room_id ?? "") ?? "Unknown room"),
          }))
          .filter((item): item is { asset: Asset; spec: TagSpec } => item.spec !== null);
        const ids = await addTags(sdk, placed.map((item) => item.spec));
        if (cancelled) {
          await removeTags(sdk, ids);
          return;
        }
        ids.forEach((tagId, i) => {
          tagToAsset.current.set(tagId, placed[i].asset.id);
          assetToTag.current.set(placed[i].asset.id, tagId);
        });
        setTagCount(ids.length);
        setPhase({ kind: "ready", fit, matched: pairs.length, total: panos.length });
      } catch (error) {
        if (!cancelled) {
          setPhase({ kind: "error", message: sdkErrorText(error) });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // Keyed on sdkLive (not phase) so the "ready" update after placing tags does not re-run this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sdkLive, panoKey, inventoryKey]);

  // 3. Clicking a tag opens the evidence card.
  useEffect(() => {
    const sdk = sdkRef.current;
    if (!sdk || phase.kind !== "ready") return undefined;
    return onTagSelected(sdk, (tagId) => {
      const assetId = tagToAsset.current.get(tagId);
      if (assetId) dispatch({ type: "selectAsset", assetId });
    });
  }, [dispatch, phase.kind]);

  // 4. Selecting an asset elsewhere (inventory, 2D plan) flies to its tag.
  useEffect(() => {
    const sdk = sdkRef.current;
    const tagId = selectedAssetId ? assetToTag.current.get(selectedAssetId) : undefined;
    if (sdk && tagId && phase.kind === "ready") void goToTag(sdk, tagId);
  }, [phase.kind, selectedAssetId]);

  if (!realModel) {
    return (
      <div className="viewer-empty" role="status">
        <div className="viewer-empty-icon" aria-hidden="true">
          3D
        </div>
        <h2>No 3D tour for this apartment</h2>
        <p>
          {selectedSid === FIXTURE_SID
            ? "The fixture apartment is illustrative data, not a real Matterport scan."
            : "This model id is not a Matterport scan."}{" "}
          Pick a real apartment to see its tour.
        </p>
        <button className="button" onClick={() => dispatch({ type: "view", view: "2d" })}>
          Use 2D floor plan
        </button>
      </div>
    );
  }

  return (
    <div className="viewer-tour">
      <iframe
        key={selectedSid}
        ref={iframeRef}
        className="viewer-tour-frame"
        title={`Matterport 3D tour of ${selectedSid}`}
        src={tourUrl(selectedSid, SDK_KEY)}
        allow="fullscreen; xr-spatial-tracking"
        onLoad={() => setLoadedSid(selectedSid)}
      />
      <p className={`viewer-tour-note pins-${phase.kind}`} role="status">
        {statusText(phase, tagCount, inventory.length)}
      </p>
    </div>
  );
}

function statusText(phase: Phase, tags: number, assets: number): string {
  switch (phase.kind) {
    case "tour-only":
      return `3D tour only. ${phase.note}; pins are on the 2D plan.`;
    case "connecting":
      return "Connecting to the Matterport SDK…";
    case "aligning":
      return "Lining up the tour with the floor plan…";
    case "ready": {
      const cm = (phase.fit.residualM * 100).toFixed(1);
      const missing = assets - tags;
      return `${tags} pin${tags === 1 ? "" : "s"} placed${
        missing > 0 ? ` (${missing} without a position)` : ""
      } · aligned on ${phase.matched} of ${phase.total} panoramas, error ${cm} cm. Click a pin for its evidence.`;
    }
    case "misaligned":
      return `Pins not shown: the tour could not be lined up with the floor plan (${phase.detail}).`;
    case "error":
      return `3D tour only. SDK problem: ${phase.message}`;
  }
}
