/**
 * The selected apartment at a glance, above the heat map: one sentence with the big numbers in it, and a
 * heat ribbon showing where the heat in the rooms comes from (windows, lights, appliances...).
 */
import type { AssetEnergy } from "../contracts";
import { useAppState } from "../state";
import { LEGEND_CSS } from "../viewer/energyColor";

const mid = (r: [number, number] | null | undefined) => (r ? (r[0] + r[1]) / 2 : 0);

const GROUPS: { name: string; labels: string[]; color: string }[] = [
  { name: "Windows", labels: ["window"], color: "#d9533d" },
  { name: "Lights", labels: ["ceiling_light", "lamp"], color: "#ef9a3c" },
  { name: "Fridge", labels: ["refrigerator"], color: "#e8c547" },
  { name: "Appliances", labels: ["stove", "oven", "microwave", "dishwasher", "washer", "dryer", "tv"], color: "#b9c86a" },
];
const OTHER = { name: "Other", color: "#a3b0a0" };

/** Heat into the rooms per year by source group, biggest first (heat removed by AC is left out). */
function heatSources(rows: AssetEnergy[]) {
  const totals = new Map<string, { name: string; color: string; kwh: number }>();
  for (const row of rows) {
    const heat = mid(row.heat_kwh_yr);
    if (heat <= 0) continue;
    const group = GROUPS.find((g) => g.labels.includes(row.label)) ?? OTHER;
    const entry = totals.get(group.name) ?? { name: group.name, color: group.color, kwh: 0 };
    entry.kwh += heat;
    totals.set(group.name, entry);
  }
  return [...totals.values()].sort((a, b) => b.kwh - a.kwh);
}

function money(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}

export function ViewerStats() {
  const state = useAppState();
  const rows = state.energy?.assets ?? [];
  const items = state.audit?.inventory.length ?? 0;
  const rooms = state.audit?.rooms.length ?? 0;
  if (!state.energy || rows.length === 0) {
    return (
      <div className="heat-story heat-story-empty">
        {state.audit ? "Working out this apartment’s energy…" : "Run an audit to see where this apartment’s heat and cost come from."}
      </div>
    );
  }
  const cost = mid(state.energy.total_usd_yr);
  const sources = heatSources(rows);
  const heat = sources.reduce((sum, s) => sum + s.kwh, 0);

  return (
    <div className="heat-story">
      <p className="heat-story-line">
        <strong className="heat-story-money">{money(cost)}</strong> a year in energy, and{" "}
        <strong>{Math.round(heat).toLocaleString()} kWh</strong> of heat poured into <strong>{rooms} rooms</strong> by
        the <strong>{items}</strong> things we found.
      </p>
      {heat > 0 ? (
        <div className="heat-ribbon" aria-label="Where the heat comes from">
          {sources.map((source) => {
            const share = source.kwh / heat;
            return (
              <div
                key={source.name}
                className="heat-ribbon-part"
                style={{ flexGrow: share, background: source.color }}
                title={`${source.name}: ${Math.round(source.kwh).toLocaleString()} kWh a year (${Math.round(share * 100)}%)`}
              >
                {share >= 0.08 ? (
                  <span>
                    {source.name} <b>{Math.round(share * 100)}%</b>
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
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
