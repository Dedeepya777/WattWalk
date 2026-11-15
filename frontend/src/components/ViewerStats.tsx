/**
 * The selected apartment at a glance, above the heat map: yearly energy cost, heat added to the rooms,
 * items found and rooms. Big numbers, short labels.
 */
import { useAppState } from "../state";
import { LEGEND_CSS } from "../viewer/energyColor";

function money(n: number): string {
  return n >= 1000 ? `$${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : `$${Math.round(n)}`;
}

function kwh(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : `${Math.round(n)}`;
}

const mid = (r: [number, number] | null | undefined) => (r ? (r[0] + r[1]) / 2 : 0);

export function ViewerStats() {
  const state = useAppState();
  const rows = state.energy?.assets ?? [];
  const items = state.audit?.inventory.length ?? 0;
  const rooms = state.audit?.rooms.length ?? 0;
  const cost = state.energy ? mid(state.energy.total_usd_yr) : null;
  const heat = rows.reduce((sum, row) => sum + Math.max(0, mid(row.heat_kwh_yr)), 0);

  const tiles = [
    { value: cost === null ? "–" : money(cost), unit: "/yr", label: "energy cost" },
    { value: rows.length ? kwh(heat) : "–", unit: " kWh", label: "heat into rooms / yr" },
    { value: String(items), unit: "", label: "items found" },
    { value: String(rooms), unit: "", label: "rooms" },
  ];

  return (
    <div className="viewer-stats" aria-label="This apartment at a glance">
      {tiles.map((tile) => (
        <div className="viewer-stat" key={tile.label}>
          <span className="viewer-stat-value">
            {tile.value}
            {tile.value !== "–" && tile.unit ? <small>{tile.unit}</small> : null}
          </span>
          <span className="viewer-stat-label">{tile.label}</span>
        </div>
      ))}
    </div>
  );
}

/** Small heat key: what the glow colours mean. */
export function HeatKey() {
  return (
    <div className="heat-key" aria-label="Glow colour: less heat (blue) to more heat (red)">
      <span>Less heat</span>
      <span className="heat-key-bar" style={{ background: LEGEND_CSS }} />
      <span>More heat</span>
    </div>
  );
}
