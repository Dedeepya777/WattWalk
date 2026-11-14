/**
 * 3D tour viewer with asset pins (plan 11.3, 13.6 and 9.7).
 *
 * The Showcase SDK needs VITE_MATTERPORT_SDK_KEY.  With a key this component connects the SDK,
 * aligns the Model API panorama frame to the SDK sweep frame (id matching first, then position
 * matching), and adds one tag per anchored asset.  Clicking a tag opens the evidence card;
 * selecting an asset elsewhere flies the camera to its tag.  Pins are placed only when the fit is
 * accepted (0.1 m RMS gate).  All SDK calls go through sdkAdapter.ts.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { Asset, AssetEnergy } from "../contracts";
import { FIXTURE_SID } from "../fixtures";
import { energySummary, labelText, unknownAttrCount } from "../format";
import { useAppDispatch, useAppState } from "../state";
import {
  SDK_CONNECT_TIMEOUT_MS,
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
} from "./sdkAdapter";
import {
  alignFrames,
  modelDirToSdk,
  modelToSdk,
  type AlignmentStrategy,
  type SdkFrameFit,
} from "./sdkFrame";
import {
  hasSdkKey,
  rememberSdkReady,
  type SdkReadiness,
} from "./sdkReadiness";

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
  | {
      kind: "ready";
      fit: SdkFrameFit;
      strategy: AlignmentStrategy;
      assigned: number;
      total: number;
      tags: number;
    }
  | { kind: "misaligned"; detail: string }
  | { kind: "error"; message: string };

export interface Viewer3DProps {
  readiness: SdkReadiness;
  /** Bumped by App when the user retries a failed connection. */
  attempt: number;
  onReady: (sid: string) => void;
  onFailed: (reason: string) => void;
  onRetry: () => void;
}

function tagSpec(asset: Asset, fit: SdkFrameFit, roomLabel: string, energy?: AssetEnergy): TagSpec | null {
  if (!asset.anchor) return null;
  const unknown = unknownAttrCount(asset.attrs);
  const down = CEILING_LABELS.has(asset.label);
  const energyText = energy ? energySummary(energy) : "";
  return {
    label: labelText(asset.label),
    description: `${roomLabel}${unknown > 0 ? ` \u00b7 ${unknown} unknown detail${unknown === 1 ? "" : "s"}` : ""}${energyText ? `\n${energyText}` : ""}`,
    anchorPosition: modelToSdk(fit, asset.anchor),
    stemVector: modelDirToSdk(fit, { x: 0, y: 0, z: down ? -STEM_M : STEM_M }),
    color: unknown > 0 ? UNKNOWN : KNOWN,
  };
}

export function Viewer3D({ readiness, attempt, onReady, onFailed, onRetry }: Viewer3DProps) {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const { selectedSid, audit, selectedAssetId } = state;
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const sdkRef = useRef<MpSdk | null>(null);
  const connectedSidRef = useRef<string | null>(null);
  const tagToAsset = useRef(new Map<string, string>());
  const assetToTag = useRef(new Map<string, string>());
  const [phase, setPhase] = useState<Phase>(
    hasSdkKey()
      ? { kind: "connecting" }
      : { kind: "tour-only", note: "No SDK key configured" },
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
  const energyById = useMemo(
    () => new Map((state.energy?.assets ?? []).map((row) => [row.asset_id, row])),
    [state.energy],
  );
  const energyKey = (state.energy?.assets ?? []).map((row) => `${row.asset_id}:${row.usd_yr}`).join("|");
  const sdkLive = phase.kind === "aligning" || phase.kind === "ready";

  // Clear the connection and tag maps when the selected scan changes (or the tab unmounts).
  useEffect(
    () => () => {
      sdkRef.current = null;
      connectedSidRef.current = null;
      tagToAsset.current.clear();
      assetToTag.current.clear();
    },
    [selectedSid],
  );

  // 1. Connect the SDK once the iframe for this model has loaded.  The connect call is capped at
  // 15 s (P4-5); `attempt` changes only when the user retries, so a successful connect is not
  // repeated when readiness flips from "checking" to "ready".
  useEffect(() => {
    if (!hasSdkKey() || !realModel || loadedSid !== selectedSid || !iframeRef.current) {
      return undefined;
    }
    if (readiness.kind === "no_key" || readiness.kind === "failed") return undefined;
    if (connectedSidRef.current === selectedSid && sdkRef.current) return undefined;

    let cancelled = false;
    setPhase({ kind: "connecting" });
    void connectSdk(iframeRef.current, SDK_KEY, SDK_CONNECT_TIMEOUT_MS).then((result) => {
      if (cancelled) return;
      if (!result.ok) {
        onFailed(result.error);
        setPhase({ kind: "error", message: result.error });
        return;
      }
      sdkRef.current = result.value;
      connectedSidRef.current = selectedSid;
      rememberSdkReady(selectedSid);
      onReady(selectedSid);
      setPhase({ kind: "aligning" });
    });
    return () => {
      cancelled = true;
    };
    // readiness.kind is read but deliberately not a dependency: a successful connect updates it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt, loadedSid, realModel, selectedSid]);

  // 1b. If the tour iframe never loads (for example an SDK key that is not allowed on this origin),
  // do not leave the tab on "Connecting" forever: surface the failure and offer 2D.
  useEffect(() => {
    if (!hasSdkKey() || !realModel) return undefined;
    if (readiness.kind === "failed" || readiness.kind === "no_key") return undefined;
    if (loadedSid === selectedSid) return undefined;
    const timer = window.setTimeout(() => {
      if (connectedSidRef.current === selectedSid) return;
      const message =
        "The Matterport tour did not load. Check the SDK key and its allowed domains.";
      onFailed(message);
      setPhase({ kind: "error", message });
    }, 20_000);
    return () => window.clearTimeout(timer);
  }, [loadedSid, onFailed, readiness.kind, realModel, selectedSid]);

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
        const sweepResult = await readSweeps(sdk);
        if (!sweepResult.ok) throw new Error(sweepResult.error);
        const sweeps = sweepResult.value;
        const alignment = alignFrames(panos, sweeps);
        if (cancelled) return;

        if (!alignment.ok) {
          console.warn(
            `[wattwalk:3d] frame fit failed (${alignment.reason}): ${alignment.message}`,
          );
          setPhase({ kind: "misaligned", detail: alignment.message });
          return;
        }

        const fields = alignment.fields
          ? Object.entries(alignment.fields)
              .map(([field, count]) => `${field}:${count}`)
              .join(", ")
          : "";
        console.info(
          `[wattwalk:3d] frame fit by ${alignment.strategy}${fields ? ` (${fields})` : ""}: ${alignment.assigned}/${panos.length} panoramas, RMS ${alignment.fit.residualM.toFixed(3)} m, coverage ${(alignment.coverage * 100).toFixed(0)}%`,
        );

        const removed = await removeTags(sdk, [...tagToAsset.current.keys()]);
        if (!removed.ok) throw new Error(removed.error);
        tagToAsset.current.clear();
        assetToTag.current.clear();

        const placed = inventory
          .map((asset) => ({
            asset,
            spec: tagSpec(asset, alignment.fit, roomLabels.get(asset.room_id ?? "") ?? "Unknown room",
              energyById.get(asset.id)),
          }))
          .filter((item): item is { asset: Asset; spec: TagSpec } => item.spec !== null);
        const added = await addTags(sdk, placed.map((item) => item.spec));
        if (!added.ok) throw new Error(added.error);
        const ids = added.value;
        if (cancelled) {
          await removeTags(sdk, ids);
          return;
        }
        ids.forEach((tagId, index) => {
          const asset = placed[index]?.asset;
          if (!asset) return;
          tagToAsset.current.set(tagId, asset.id);
          assetToTag.current.set(asset.id, tagId);
        });
        setTagCount(ids.length);
        setPhase({
          kind: "ready",
          fit: alignment.fit,
          strategy: alignment.strategy,
          assigned: alignment.assigned,
          total: panos.length,
          tags: ids.length,
        });
      } catch (error) {
        if (!cancelled) {
          const message = sdkErrorText(error);
          setPhase({ kind: "error", message });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // Keyed on sdkLive (not phase) so the "ready" update after placing tags does not re-run this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sdkLive, panoKey, inventoryKey, energyKey]);

  // 3. Clicking a tag opens the evidence card.
  useEffect(() => {
    const sdk = sdkRef.current;
    if (!sdk || phase.kind !== "ready") return undefined;
    const subscription = onTagSelected(sdk, (tagId) => {
      const assetId = tagToAsset.current.get(tagId);
      if (assetId) dispatch({ type: "selectAsset", assetId });
    });
    return subscription.ok ? subscription.value : undefined;
  }, [dispatch, phase.kind]);

  // 4. Selecting an asset elsewhere (inventory, 2D plan) flies to its tag.
  useEffect(() => {
    const sdk = sdkRef.current;
    const tagId = selectedAssetId ? assetToTag.current.get(selectedAssetId) : undefined;
    if (sdk && tagId && phase.kind === "ready") void goToTag(sdk, tagId);
  }, [phase.kind, selectedAssetId]);

  if (readiness.kind === "no_key") {
    return (
      <div className="viewer-empty" role="status">
        <div className="viewer-empty-icon" aria-hidden="true">
          3D
        </div>
        <h2>3D pins need an SDK key</h2>
        <p>
          Set VITE_MATTERPORT_SDK_KEY to show asset pins in the Matterport tour. The 2D floor
          plan shows the same pins without a key.
        </p>
        <button className="button" onClick={() => dispatch({ type: "view", view: "2d" })}>
          Use 2D floor plan
        </button>
      </div>
    );
  }

  if (readiness.kind === "failed") {
    return (
      <div className="viewer-empty" role="status">
        <div className="viewer-empty-icon" aria-hidden="true">
          3D
        </div>
        <h2>3D pins unavailable</h2>
        <p>{readiness.reason}</p>
        <p className="muted">
          The 2D floor plan is the fallback and stays the default view.
        </p>
        <div className="button-row">
          <button className="button" onClick={() => dispatch({ type: "view", view: "2d" })}>
            Use 2D floor plan
          </button>
          <button className="button" onClick={onRetry}>
            Try 3D again
          </button>
        </div>
      </div>
    );
  }

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
      {phase.kind === "misaligned" || phase.kind === "error" ? (
        <div className="button-row viewer-tour-actions">
          <button className="button small" onClick={() => dispatch({ type: "view", view: "2d" })}>
            Use 2D floor plan
          </button>
          {phase.kind === "error" ? (
            <button className="button small" onClick={onRetry}>
              Try 3D again
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function statusText(phase: Phase, tags: number, assets: number): string {
  switch (phase.kind) {
    case "tour-only":
      return `3D tour only. ${phase.note}; pins are on the 2D plan.`;
    case "connecting":
      return "Connecting to the Matterport SDK\u2026";
    case "aligning":
      return "Lining up the tour with the floor plan\u2026";
    case "ready": {
      const cm = (phase.fit.residualM * 100).toFixed(1);
      const missing = assets - tags;
      const panoramaText =
        phase.assigned === phase.total
          ? `aligned on ${phase.assigned} panoramas by ${phase.strategy}`
          : `aligned on ${phase.assigned} of ${phase.total} panoramas by ${phase.strategy}`;
      return `${tags} pin${tags === 1 ? "" : "s"} placed${
        missing > 0 ? ` (${missing} without a position)` : ""
      } \u00b7 ${panoramaText}, error ${cm} cm. Click a pin for its evidence.`;
    }
    case "misaligned":
      return `Pins not shown: the tour could not be lined up with the floor plan (${phase.detail}).`;
    case "error":
      return `3D tour only. SDK problem: ${phase.message}`;
  }
}
