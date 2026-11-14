/**
 * Energy alternatives card (step 2 of the energy alternatives feature): one asset's energy today and
 * the upgrades that apply to it, from GET /audits/{sid}/energy. Opened from the evidence card's
 * "Compare alternatives" button. Plain on purpose: the expanding animation and the glows come later.
 */
import { useEffect } from "react";
import type { AssetEnergy, EnergyAlternative } from "../contracts";
import { formatRange, labelText } from "../format";
import { useAppDispatch, useAppState } from "../state";

/** "4–6 months" under a year, else "1.5–2.8 years". */
export function formatPayback(range: [number, number] | null): string {
  if (!range) return "no saving";
  const [lo, hi] = range;
  if (hi < 1) {
    const m = (v: number) => Math.max(1, Math.round(v * 12));
    return m(lo) === m(hi) ? `${m(lo)} months` : `${m(lo)}–${m(hi)} months`;
  }
  const y = (v: number) => (v < 10 ? v.toFixed(1) : Math.round(v).toString());
  return y(lo) === y(hi) ? `${y(lo)} years` : `${y(lo)}–${y(hi)} years`;
}

function heatText(range: [number, number] | null): string {
  if (!range) return "–";
  if (range[0] < 0) return `${formatRange([-range[1], -range[0]], "kWh")} moved outside`;
  return formatRange(range, "kWh");
}

function NowRow({ row }: { row: AssetEnergy }) {
  return (
    <section className="energy-alt-now">
      <h3>Today</h3>
      <dl className="energy-grid">
        <dt>Cost per year</dt>
        <dd>{formatRange(row.usd_yr, "", true)}</dd>
        <dt>Heat into the room per year</dt>
        <dd>{heatText(row.heat_kwh_yr)}</dd>
        {row.power_w ? (
          <>
            <dt>Power while running</dt>
            <dd>{formatRange(row.power_w, "W")}</dd>
          </>
        ) : null}
      </dl>
    </section>
  );
}

function AlternativeRow({ alt }: { alt: EnergyAlternative }) {
  const mayBeZero = alt.saves_usd_yr[0] <= 0;
  return (
    <li className="energy-alt-option">
      <div className="energy-alt-option-head">
        <strong>{alt.title}</strong>
        <span className="muted small">{alt.who}</span>
      </div>
      <dl className="energy-grid">
        {alt.usd_yr ? (
          <>
            <dt>Cost per year after</dt>
            <dd>{formatRange(alt.usd_yr, "", true)}</dd>
          </>
        ) : null}
        {alt.heat_kwh_yr ? (
          <>
            <dt>Heat per year after</dt>
            <dd>{heatText(alt.heat_kwh_yr)}</dd>
          </>
        ) : null}
        {alt.power_w ? (
          <>
            <dt>Power after</dt>
            <dd>{formatRange(alt.power_w, "W")}</dd>
          </>
        ) : null}
        <dt>Saves per year</dt>
        <dd className="energy-alt-saves">{formatRange(alt.saves_usd_yr, "", true)}</dd>
        <dt>Upgrade costs</dt>
        <dd>{formatRange(alt.cost_usd, "", true)}</dd>
        <dt>Pays back in</dt>
        <dd>
          {formatPayback(alt.payback_years)}
          {mayBeZero && alt.payback_years ? " (best case)" : ""}
        </dd>
      </dl>
      <p className="muted small">{alt.basis}</p>
    </li>
  );
}

export function EnergyAlternatives() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const assetId = state.focusAssetId;
  const row = assetId ? state.energy?.assets.find((item) => item.asset_id === assetId) ?? null : null;
  const asset = assetId ? state.audit?.inventory.find((item) => item.id === assetId) ?? null : null;
  const room = asset?.room_id ? state.audit?.rooms.find((r) => r.id === asset.room_id)?.label : undefined;
  const close = () => dispatch({ type: "focusEnergy", assetId: null });

  useEffect(() => {
    if (!assetId) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") dispatch({ type: "focusEnergy", assetId: null });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [assetId, dispatch]);

  if (!assetId || !row) return null;

  return (
    <div className="modal-backdrop" role="presentation" onClick={close}>
      <div
        className="modal energy-alt-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="energy-alt-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2 id="energy-alt-title">{labelText(row.label)}: alternatives</h2>
            <p className="muted small">
              {room ?? "Unknown room"} · {row.asset_id}
            </p>
          </div>
          <button className="button small" onClick={close} aria-label="Close">
            ×
          </button>
        </div>
        {row.estimated ? <NowRow row={row} /> : <p className="muted">Today: not estimated ({row.note}).</p>}
        {row.alternatives.length === 0 ? (
          <p className="empty">
            {row.label === "lamp" || row.label === "ceiling_light"
              ? "Already efficient: these bulbs are LED."
              : "No upgrade in the library applies to this item yet."}
          </p>
        ) : (
          <ul className="energy-alt-list">
            {row.alternatives.map((alt) => (
              <AlternativeRow key={alt.upgrade_id} alt={alt} />
            ))}
          </ul>
        )}
        <p className="muted small">
          Ranges come from the same assumptions as the upgrade plan. Upgrade costs are installed cost
          ranges from the plan's upgrade library.
        </p>
      </div>
    </div>
  );
}
