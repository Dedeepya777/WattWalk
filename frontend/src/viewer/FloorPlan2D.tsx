/**
 * 2D floor plan with pins and the optional room heat map (plan 11.3, 11.5).
 *
 * Model x, y map to SVG x, -y (SVG y points down).  Pins sit at the asset
 * anchor; when there is no anchor (or the user chooses the fallback) they sit
 * at the room centroid plus a deterministic small offset.  While the face basis
 * is unverified every anchor pin is drawn dashed and labelled approximate.
 */
import { useMemo, useState } from "react";
import faceBasisJson from "@spatial/face_basis.json";
import type { Asset, AssetLabel, HeatShare, Pano, Room, Vec2 } from "../contracts";
import { labelText, unknownAttrCount } from "../format";
import { buildScale, pinColor, toHex } from "./energyColor";
import { useAppDispatch, useAppState } from "../state";

const FACE_BASIS = faceBasisJson as { status?: string; residual_m?: number | null };
const BASIS_STATUS = FACE_BASIS.status ?? "unverified";

const PIN_TEXT: Record<AssetLabel, string> = {
  window: "Win",
  window_ac: "AC",
  mini_split: "Mini",
  supply_vent: "Vent",
  thermostat: "Therm",
  ceiling_light: "Light",
  lamp: "Lamp",
  refrigerator: "Fridge",
  range_gas: "Range",
  range_electric: "Range",
  dishwasher: "Dish",
  washer: "Washer",
  dryer: "Dryer",
  ceiling_fan: "Fan",
  water_heater: "WH",
};

type PinMode = "anchor" | "centroid";

interface Pin {
  asset: Asset;
  x: number;
  y: number;
  approximate: boolean;
  unknown: number;
  roomLabel: string;
}

function centroid(polygon: Vec2[]): Vec2 {
  if (polygon.length === 0) return { x: 0, y: 0 };
  let twiceArea = 0;
  let cx = 0;
  let cy = 0;
  for (let index = 0; index < polygon.length; index += 1) {
    const current = polygon[index];
    const next = polygon[(index + 1) % polygon.length];
    const cross = current.x * next.y - next.x * current.y;
    twiceArea += cross;
    cx += (current.x + next.x) * cross;
    cy += (current.y + next.y) * cross;
  }
  if (Math.abs(twiceArea) < 1e-9) {
    const mean = polygon.reduce(
      (acc, point) => ({ x: acc.x + point.x, y: acc.y + point.y }),
      { x: 0, y: 0 },
    );
    return { x: mean.x / polygon.length, y: mean.y / polygon.length };
  }
  return { x: cx / (3 * twiceArea), y: cy / (3 * twiceArea) };
}

function offsetFor(index: number): Vec2 {
  const ring = Math.floor(index / 6);
  const slot = index % 6;
  const radius = 0.25 + 0.22 * ring;
  const angle = (Math.PI * 2 * slot) / 6 + 0.4;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

function heatColor(share: number, max: number): string {
  const t = max > 0 ? Math.min(1, Math.max(0, share / max)) : 0;
  const hue = 212 - 182 * t;
  const lightness = 26 + 30 * t;
  return `hsl(${hue.toFixed(0)} 66% ${lightness.toFixed(0)}%)`;
}

export function FloorPlan2D() {
  const state = useAppState();
  const energyById = useMemo(
    () => new Map((state.energy?.assets ?? []).map((row) => [row.asset_id, row])),
    [state.energy],
  );
  const energyScale = useMemo(
    () => buildScale(state.energy?.assets ?? [], state.pinColorMode),
    [state.energy, state.pinColorMode],
  );
  const energyFill = (assetId: string): string | null => {
    const color = pinColor(energyById.get(assetId), energyScale);
    return color ? toHex(color) : null;
  };
  const dispatch = useAppDispatch();
  const [pinMode, setPinMode] = useState<PinMode>("anchor");

  const audit = state.audit;
  const rooms: Room[] = audit?.rooms ?? [];
  const panos: Pano[] = audit?.panos ?? [];
  const assets: Asset[] = audit?.inventory ?? [];
  const heat: HeatShare[] = audit?.heat_shares ?? [];
  const coverage = audit?.coverage;
  const showHeat = state.viewMode === "heat" && heat.length > 0;

  const layout = useMemo(() => {
    const roomById = new Map(rooms.map((room) => [room.id, room]));
    const roomCentroids = new Map(
      rooms.map((room) => [room.id, centroid(room.polygon)] as const),
    );
    const perRoomIndex = new Map<string, number>();

    const pins: Pin[] = assets.flatMap((asset) => {
      const room = asset.room_id ? roomById.get(asset.room_id) : undefined;
      const roomCenter = asset.room_id ? roomCentroids.get(asset.room_id) : undefined;
      const index = asset.room_id ? perRoomIndex.get(asset.room_id) ?? 0 : 0;
      if (asset.room_id) perRoomIndex.set(asset.room_id, index + 1);
      const offset = offsetFor(index);
      let x: number;
      let y: number;
      let approximate: boolean;
      if (pinMode === "anchor" && asset.anchor) {
        x = asset.anchor.x;
        y = asset.anchor.y;
        approximate = BASIS_STATUS !== "calibrated";
      } else if (roomCenter) {
        x = roomCenter.x + offset.x;
        y = roomCenter.y + offset.y;
        approximate = true;
      } else {
        return [];
      }
      return [
        {
          asset,
          x,
          y,
          approximate,
          unknown: unknownAttrCount(asset.attrs),
          roomLabel: room?.label ?? "Unassigned room",
        },
      ];
    });

    const xs: number[] = rooms.flatMap((room) => room.polygon.map((point) => point.x));
    const ys: number[] = rooms.flatMap((room) => room.polygon.map((point) => point.y));
    for (const pano of panos) {
      xs.push(pano.position.x);
      ys.push(pano.position.y);
    }
    for (const pin of pins) {
      xs.push(pin.x);
      ys.push(pin.y);
    }
    if (xs.length === 0 || ys.length === 0) {
      return null;
    }
    const pad = 0.6;
    const minX = Math.min(...xs) - pad;
    const maxX = Math.max(...xs) + pad;
    const minY = Math.min(...ys) - pad;
    const maxY = Math.max(...ys) + pad;
    const width = Math.max(0.1, maxX - minX);
    const height = Math.max(0.1, maxY - minY);

    const maxShare = heat.reduce((best, item) => Math.max(best, item.share), 0);
    const heatByRoom = new Map(heat.map((item) => [item.room_id, item] as const));

    return {
      pins,
      roomById,
      roomCentroids,
      heatByRoom,
      maxShare,
      viewBox: `${minX} ${-maxY} ${width} ${height}`,
      aspect: width / height,
    };
  }, [assets, heat, panos, pinMode, rooms]);

  if (rooms.length === 0 || layout === null) {
    const running = audit?.status.status === "running";
    return (
      <div className="viewer-empty" role="status">
        <div className="viewer-empty-icon" aria-hidden="true">
          2D
        </div>
        <h2>{running ? "Loading floor plan…" : "No geometry yet"}</h2>
        <p>
          {running
            ? "The walker is loading rooms and panoramas. Room polygons appear when geometry is ready."
            : "Start an audit to load the model geometry, or choose a model with a fixture."}
        </p>
        {running ? <div className="skeleton skeleton-viewer" /> : null}
      </div>
    );
  }

  const partialRooms =
    coverage?.rooms.filter((room) => room.status === "partial") ?? [];

  return (
    <div className="floorplan-wrap">
      <div className="viewer-toolbar">
        <div className="segmented" role="group" aria-label="Pin placement">
          <button
            type="button"
            className={pinMode === "anchor" ? "segmented-button active" : "segmented-button"}
            onClick={() => setPinMode("anchor")}
            aria-pressed={pinMode === "anchor"}
          >
            Anchors
          </button>
          <button
            type="button"
            className={pinMode === "centroid" ? "segmented-button active" : "segmented-button"}
            onClick={() => setPinMode("centroid")}
            aria-pressed={pinMode === "centroid"}
          >
            Room centroids
          </button>
        </div>
        {showHeat ? (
          <span className="legend-inline">
            Heat map: share of modelled heat weight
          </span>
        ) : null}
        <span className="pin-basis-note">
          {BASIS_STATUS === "calibrated"
            ? "Face basis calibrated"
            : "Pin positions unverified"}
        </span>
      </div>

      <svg
        className="floorplan"
        viewBox={layout.viewBox}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`Floor plan with ${layout.pins.length} assets in ${rooms.length} rooms`}
      >
        <g>
          {rooms.map((room) => {
            const share = layout.heatByRoom.get(room.id);
            const fill = showHeat && share ? heatColor(share.share, layout.maxShare) : "var(--room-fill)";
            return (
              <g key={room.id}>
                <polygon
                  className="room-polygon"
                  points={room.polygon.map((point) => `${point.x},${-point.y}`).join(" ")}
                  style={{ fill }}
                >
                  <title>
                    {room.label}: {room.area_m2.toFixed(1)} m²
                  </title>
                </polygon>
              </g>
            );
          })}
        </g>

        <g>
          {rooms.map((room) => {
            const point = layout.roomCentroids.get(room.id);
            if (!point) return null;
            return (
              <text
                key={`label-${room.id}`}
                className="room-label"
                x={point.x}
                y={-point.y}
                textAnchor="middle"
                aria-hidden="true"
              >
                {room.label}
              </text>
            );
          })}
        </g>

        <g>
          {panos.map((pano) => (
            <g key={pano.id}>
              <circle
                className="pano-dot"
                cx={pano.position.x}
                cy={-pano.position.y}
                r={0.1}
              >
                <title>
                  Panorama {pano.label} ({pano.id})
                </title>
              </circle>
              <text
                className="pano-label"
                x={pano.position.x + 0.14}
                y={-pano.position.y + 0.06}
                aria-hidden="true"
              >
                {pano.label}
              </text>
            </g>
          ))}
        </g>

        <g>
          {partialRooms.map((room) => {
            const point = layout.roomCentroids.get(room.room_id);
            if (!point) return null;
            return (
              <g key={`partial-${room.room_id}`}>
                <circle
                  className="rejected-marker"
                  cx={point.x}
                  cy={-point.y - 0.42}
                  r={0.16}
                >
                  <title>
                    Face rejected for quality in {room.room_label}.{" "}
                    {room.notes.join(" ")}
                  </title>
                </circle>
                <text
                  className="rejected-label"
                  x={point.x}
                  y={-point.y - 0.35}
                  textAnchor="middle"
                  aria-hidden="true"
                >
                  !
                </text>
              </g>
            );
          })}
        </g>

        <g>
          {layout.pins.map((pin) => {
            const selected = state.selectedAssetId === pin.asset.id;
            const className = [
              "pin",
              pin.approximate ? "pin-approximate" : pin.unknown > 0 ? "pin-unknown" : "pin-known",
              selected ? "selected" : "",
            ]
              .filter(Boolean)
              .join(" ");
            const aria = `${labelText(pin.asset.label)}, ${pin.roomLabel}, ${
              pin.unknown === 1 ? "1 unknown attribute" : `${pin.unknown} unknown attributes`
            }${pin.approximate ? ", approximate position" : ""}`;
            return (
              <g
                key={pin.asset.id}
                className={className}
                role="button"
                tabIndex={0}
                aria-label={aria}
                onClick={() => dispatch({ type: "selectAsset", assetId: pin.asset.id })}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    dispatch({ type: "selectAsset", assetId: pin.asset.id });
                  }
                }}
              >
                <title>{aria}</title>
                <circle
                  cx={pin.x}
                  cy={-pin.y}
                  r={0.2}
                  className="pin-dot"
                  style={energyFill(pin.asset.id) ? { fill: energyFill(pin.asset.id) ?? undefined } : undefined}
                />
                <text
                  className="pin-text"
                  x={pin.x}
                  y={-pin.y + 0.07}
                  textAnchor="middle"
                  aria-hidden="true"
                >
                  {PIN_TEXT[pin.asset.label]}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {showHeat ? (
        <div className="heat-legend" aria-label="Heat map legend">
          <h3>Heat shares</h3>
          <ul>
            {heat.map((item) => {
              const room = layout.roomById.get(item.room_id);
              return (
                <li key={item.room_id}>
                  <span
                    className="heat-swatch"
                    style={{ background: heatColor(item.share, layout.maxShare) }}
                    aria-hidden="true"
                  />
                  <span>{room?.label ?? item.room_id}</span>
                  <strong>{`${(item.share * 100).toFixed(1)}%`}</strong>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
