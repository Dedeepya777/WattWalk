/**
 * The selected apartment at a glance, above the heat map: a few plain numbers with small labels, and a
 * slim bar showing where the heat in the rooms comes from (windows, lights, appliances...).
 */
import type { AssetEnergy } from "../contracts";
import { useAppState } from "../state";
import { LEGEND_CSS } from "../viewer/energyColor";

const mid = (r: [number, number] | null | undefined) => (r ? (r[0] + r[1]) / 2 : 0);

const GROUPS: { name: string; labels: string[]; color: string }[] = [
  { name: "Windows", labels: ["window"], color: "#e0573f" },
  { name: "Lights", labels: ["ceiling_light", "lamp"], color: "#f29b38" },
  { name: "Fridge", labels: ["refrigerator"], color: "#e9c03f" },
  { name: "Appliances", labels: ["stove", "oven", "microwave", "dishwasher", "washer", "dryer", "tv"], color: "#9fb563" },
];
const OTHER = { name: "Other", color: "#b9bdb5" };

/** Heat into the rooms per year by source, biggest first (heat removed by AC is left out). */
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

/** Toolbar button with the yearly cost; opens the cost details below the toolbar. */
export function CostsButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const state = useAppState();
  if (!state.energy || state.energy.assets.length === 0) return null;
  return (
    <button type="button" className={`costs-button${open ? " open" : ""}`} onClick={onToggle} aria-expanded={open}>
      <span className="costs-button-value">${Math.round(mid(state.energy.total_usd_yr)).toLocaleString()}</span>
      <span className="costs-button-unit">/ yr</span>
      <span className="costs-button-label">{open ? "Hide details" : "Cost details"}</span>
      <svg className="costs-button-chevron" viewBox="0 0 12 12" aria-hidden="true">
        <path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

export function ViewerStats({ open }: { open: boolean }) {
  const state = useAppState();
  const rows = state.energy?.assets ?? [];
  if (!state.energy || rows.length === 0) return null;
  const sources = heatSources(rows);
  const heat = sources.reduce((sum, s) => sum + s.kwh, 0);
  const metrics = [
    { label: "Energy", value: `$${Math.round(mid(state.energy.total_usd_yr)).toLocaleString()}`, unit: "per year" },
    { label: "Heat", value: Math.round(heat).toLocaleString(), unit: "kWh a year" },
    { label: "Items", value: String(state.audit?.inventory.length ?? 0), unit: "found" },
    { label: "Rooms", value: String(state.audit?.rooms.length ?? 0), unit: "scanned" },
  ].filter((metric) => !(metric.label === "Rooms" && metric.value === "0")); // some scans have no floor plan

  return (
    <div className={`glance-wrap${open ? " open" : ""}`} aria-hidden={!open}>
    <div className="glance-inner">
    <div className="glance">
      <dl className="glance-metrics">
        {metrics.map((metric) => (
          <div key={metric.label} className="glance-metric">
            <dt>{metric.label}</dt>
            <dd>
              {metric.value} <span>{metric.unit}</span>
            </dd>
          </div>
        ))}
      </dl>
      {heat > 0 ? (
        <div className="glance-heat">
          <div className="glance-bar" aria-hidden="true">
            {sources.map((source) => (
              <span key={source.name} style={{ flexGrow: source.kwh / heat, background: source.color }} />
            ))}
          </div>
          <ul className="glance-legend" aria-label="Where the heat comes from">
            {sources.map((source) => (
              <li key={source.name}>
                <i style={{ background: source.color }} aria-hidden="true" />
                {source.name} <span>{Math.round((source.kwh / heat) * 100)}%</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <HeatKey />
    </div>
    </div>
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
