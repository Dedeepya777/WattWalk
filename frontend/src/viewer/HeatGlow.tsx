/**
 * Heat glow over the 3D tour (step 3b of the energy view).
 *
 * The embedded Showcase SDK has no Scene API (no custom 3D objects) and keeps tag icons small, so the
 * glow is drawn in the page on top of the tour: every frame the camera pose is read, each asset's 3D
 * position is projected to the screen with Conversion.worldToScreen, and a soft radial gradient is
 * drawn there. Its colour comes from the pin colour scale (blue low to red high, cyan for units that
 * move heat outside) and its size from the asset's heat or cost, shrinking with distance like real
 * perspective. Only assets in the room the camera stands in are drawn, so nothing glows through walls.
 * A small label at the centre of the larger glows shows the energy number.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { Asset, AssetEnergy, Pano } from "../contracts";
import { formatRange } from "../format";
import { pinColor, position, toHex, type EnergyScale } from "./energyColor";
import type { MpSdk } from "./sdkAdapter";
import { modelToSdk, type SdkFrameFit } from "./sdkFrame";

const MAX_DISTANCE_M = 12;
const FALLBACK_RADIUS_M = 8; // when the current room is unknown, only draw nearby assets
const NEARBY_M = 5; // also draw assets this close in another room (open-plan spaces, open doorways)
const LABEL_GAP_X = 80; // px: skip a label that would overlap one already placed
const LABEL_GAP_Y = 22;
const LABEL_FROM = 0.45; // label glows in the upper part of the scale only (avoids clutter)

interface Glow {
  id: string;
  x: number;
  y: number;
  r: number;
  color: string;
  label: string;
}

interface Pose {
  position: { x: number; y: number; z: number };
  rotation: { x: number; y: number };
  sweep?: string;
}

interface Props {
  sdk: MpSdk;
  fit: SdkFrameFit;
  frame: HTMLIFrameElement | null;
  inventory: Asset[];
  panos: Pano[];
  energyById: Map<string, AssetEnergy>;
  scale: EnergyScale;
}

/** Camera forward vector from the SDK pose rotation (degrees: x pitch, y yaw). */
function forward(rotation: { x: number; y: number }) {
  const rx = (rotation.x * Math.PI) / 180;
  const ry = (rotation.y * Math.PI) / 180;
  return { x: -Math.sin(ry) * Math.cos(rx), y: Math.sin(rx), z: -Math.cos(ry) * Math.cos(rx) };
}

function glowLabel(row: AssetEnergy, scale: EnergyScale): string {
  if (scale.mode === "cost") return row.usd_yr ? `${formatRange(row.usd_yr, "", true)}/yr` : "";
  if (row.heat_kwh_yr && row.heat_kwh_yr[0] < 0) return "removes heat";
  if (row.power_w) return formatRange(row.power_w, "W");
  return row.heat_kwh_yr ? `${formatRange(row.heat_kwh_yr, "kWh")}/yr` : "";
}

export function HeatGlow({ sdk, fit, frame, inventory, panos, energyById, scale }: Props) {
  const [glows, setGlows] = useState<Glow[]>([]);
  const [box, setBox] = useState({ left: 0, top: 0, width: 0, height: 0 });
  const poseRef = useRef<Pose | null>(null);
  const roomRef = useRef<string | null>(null);
  const frameRequest = useRef<number | null>(null);

  const roomOfPano = useMemo(() => new Map(panos.map((p) => [p.id, p.room_id ?? null])), [panos]);

  // Assets that can glow, with their tour position, colour, strength and label (recomputed on data change).
  const sources = useMemo(() => {
    return inventory.flatMap((asset) => {
      const row = energyById.get(asset.id);
      if (!asset.anchor || !row || !row.estimated) return [];
      const color = pinColor(row, scale);
      const range = scale.mode === "cost" ? row.usd_yr : row.heat_kwh_yr;
      if (!color || !range) return [];
      const value = (range[0] + range[1]) / 2;
      const t = value > 0 ? position(value, scale) : 0.6; // heat removed: a mid-sized cold haze
      return [{
        id: asset.id,
        room: asset.room_id ?? null,
        world: modelToSdk(fit, asset.anchor),
        color: toHex(color),
        strength: t,
        label: t >= LABEL_FROM || value < 0 ? glowLabel(row, scale) : "",
      }];
    });
  }, [energyById, fit, inventory, scale]);

  // Keep the overlay exactly over the tour frame.
  useEffect(() => {
    if (!frame) return undefined;
    const update = () => setBox({ left: frame.offsetLeft, top: frame.offsetTop, width: frame.clientWidth, height: frame.clientHeight });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(frame);
    return () => observer.disconnect();
  }, [frame]);

  // Follow the camera and the current panorama (the room it stands in).
  useEffect(() => {
    const draw = () => {
      frameRequest.current = null;
      const pose = poseRef.current;
      if (!pose || box.width === 0) return;
      const fwd = forward(pose.rotation);
      const size = { w: box.width, h: box.height };
      const room = roomRef.current;
      const next: Glow[] = [];
      for (const s of sources) {
        const d = { x: s.world.x - pose.position.x, y: s.world.y - pose.position.y, z: s.world.z - pose.position.z };
        const dist = Math.hypot(d.x, d.y, d.z);
        if (dist < 0.3 || dist > MAX_DISTANCE_M) continue;
        if (d.x * fwd.x + d.y * fwd.y + d.z * fwd.z <= 0) continue; // behind the camera
        if (room ? s.room !== room && dist > NEARBY_M : dist > FALLBACK_RADIUS_M) continue;
        let screen: { x: number; y: number } | null = null;
        try {
          screen = sdk.Conversion.worldToScreen(s.world, pose, size);
        } catch {
          screen = null;
        }
        if (!screen || screen.x < -200 || screen.y < -200 || screen.x > size.w + 200 || screen.y > size.h + 200) continue;
        const radiusM = 0.4 + 2.0 * s.strength;
        const r = Math.min(size.h * 0.7, Math.max(14, (radiusM * size.h * 0.9) / dist));
        next.push({ id: s.id, x: screen.x, y: screen.y, r, color: s.color, label: s.label });
      }
      // Draw big glows first so small ones stay visible on top; label the biggest first and skip a
      // label that would overlap one already placed.
      next.sort((a, b) => b.r - a.r);
      const placed: { x: number; y: number }[] = [];
      for (const g of next) {
        if (!g.label) continue;
        if (placed.some((p) => Math.abs(p.x - g.x) < LABEL_GAP_X && Math.abs(p.y - g.y) < LABEL_GAP_Y)) {
          g.label = "";
        } else {
          placed.push({ x: g.x, y: g.y });
        }
      }
      setGlows(next);
    };
    const schedule = () => {
      if (frameRequest.current === null) frameRequest.current = window.requestAnimationFrame(draw);
    };
    const subs: { cancel?: () => void }[] = [];
    try {
      subs.push(sdk.Camera.pose.subscribe((pose: Pose) => {
        poseRef.current = pose;
        schedule();
      }));
    } catch {
      // No camera pose: nothing to draw.
    }
    try {
      subs.push(sdk.Sweep.current.subscribe((sweep: { id?: string; sid?: string }) => {
        const id = sweep?.sid ?? sweep?.id ?? "";
        roomRef.current = roomOfPano.get(id) ?? roomOfPano.get(sweep?.id ?? "") ?? null;
        schedule();
      }));
    } catch {
      roomRef.current = null;
    }
    schedule();
    return () => {
      subs.forEach((sub) => sub?.cancel?.());
      if (frameRequest.current !== null) window.cancelAnimationFrame(frameRequest.current);
      frameRequest.current = null;
    };
  }, [box, roomOfPano, sdk, sources]);

  return (
    <div
      className="heat-glow-layer"
      aria-hidden="true"
      style={{ left: box.left, top: box.top, width: box.width, height: box.height }}
    >
      {glows.map((g, index) => (
        <div
          key={g.id}
          className="heat-glow"
          style={{
            left: g.x - g.r,
            top: g.y - g.r,
            width: g.r * 2,
            height: g.r * 2,
            background: `radial-gradient(circle, ${g.color}e6 0%, ${g.color}88 28%, ${g.color}33 52%, ${g.color}00 72%)`,
            animationDelay: `${(index % 7) * -0.45}s`,
          }}
        >
          {g.label ? <span className="heat-glow-label">{g.label}</span> : null}
        </div>
      ))}
    </div>
  );
}
