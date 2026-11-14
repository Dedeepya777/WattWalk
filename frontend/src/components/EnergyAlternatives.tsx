/**
 * Energy alternatives card (step 2 of the energy alternatives feature): one asset's energy today and
 * the upgrades that apply to it, from GET /audits/{sid}/energy. Opened from the evidence card's
 * "Compare alternatives" button. Plain on purpose: the expanding animation and the glows come later.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { AssetEnergy, EnergyAlternative } from "../contracts";
import { formatRange, labelText } from "../format";
import { useAppDispatch, useAppState } from "../state";
import { REMOVES_HEAT, buildScale, gradient, position, toHex, type EnergyScale } from "../viewer/energyColor";

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

const GLOW_MAX = 84; // px, today's glow

const mid = (r: [number, number] | null) => (r ? (r[0] + r[1]) / 2 : null);

/** Glow colour for a heat value on the apartment's heat scale (cyan when it removes heat). */
function glowColor(heat: number | null, scale: EnergyScale | null): string {
  if (heat === null) return "#6b7280";
  if (heat < 0) return toHex(REMOVES_HEAT);
  if (!scale || heat <= 0) return toHex(gradient(0));
  return toHex(gradient(position(heat, scale)));
}

/** Glow diameter: today's is GLOW_MAX; others scale by the square root of their heat (area ~ heat). */
function glowSize(heat: number | null, todayHeat: number | null): number {
  if (heat === null || todayHeat === null || todayHeat === 0) return GLOW_MAX * 0.5;
  const ratio = Math.min(1, Math.max(0, Math.abs(heat) / Math.abs(todayHeat)));
  return Math.max(14, GLOW_MAX * Math.sqrt(ratio));
}

function Glow({ size, color, from }: { size: number; color: string; from?: number }) {
  // Starts at `from` (today's size) and transitions to `size` once the card has opened.
  const [current, setCurrent] = useState(from ?? size);
  useEffect(() => {
    const id = window.requestAnimationFrame(() => setCurrent(size));
    return () => window.cancelAnimationFrame(id);
  }, [size]);
  return (
    <div className="energy-alt-glow-box" aria-hidden="true">
      <span
        className="energy-alt-glow"
        style={{
          width: current,
          height: current,
          background: `radial-gradient(circle, ${color}e6 0%, ${color}8c 30%, ${color}33 55%, ${color}00 72%)`,
        }}
      />
    </div>
  );
}

/** Bar from 100% (today) sliding to the share left after the upgrade, with the change in %. */
function ChangeBar({ before, after, unit }: { before: number | null; after: number | null; unit: string }) {
  const share = before && after !== null && before > 0 ? Math.max(0, Math.min(1, after / before)) : null;
  const [width, setWidth] = useState(100);
  useEffect(() => {
    if (share === null) return undefined;
    const id = window.setTimeout(() => setWidth(share * 100), 120);
    return () => window.clearTimeout(id);
  }, [share]);
  if (share === null) return null;
  const pct = Math.round((share - 1) * 100);
  return (
    <div className="energy-alt-bar-row" aria-label={`${unit} ${pct}% compared with today`}>
      <div className="energy-alt-bar-track">
        <div className="energy-alt-bar-fill" style={{ width: `${width}%` }} />
      </div>
      <span className="energy-alt-pct">{pct === 0 ? "same" : `${pct}% ${unit}`}</span>
    </div>
  );
}

function NowRow({ row, scale }: { row: AssetEnergy; scale: EnergyScale | null }) {
  const heat = mid(row.heat_kwh_yr);
  return (
    <section className="energy-alt-now energy-alt-with-glow">
      <Glow size={GLOW_MAX} color={glowColor(heat, scale)} />
      <div className="energy-alt-body">
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
      </div>
    </section>
  );
}

function AlternativeRow({ alt, row, scale, index }: {
  alt: EnergyAlternative;
  row: AssetEnergy;
  scale: EnergyScale | null;
  index: number;
}) {
  const mayBeZero = alt.saves_usd_yr[0] <= 0;
  const todayHeat = mid(row.heat_kwh_yr);
  const afterHeat = mid(alt.heat_kwh_yr);
  return (
    <li className="energy-alt-option energy-alt-with-glow" style={{ animationDelay: `${120 + index * 90}ms` }}>
      {afterHeat !== null ? (
        <Glow size={glowSize(afterHeat, todayHeat)} from={GLOW_MAX} color={glowColor(afterHeat, scale)} />
      ) : (
        <div className="energy-alt-glow-box" aria-hidden="true" />
      )}
      <div className="energy-alt-body">
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
      <ChangeBar before={mid(row.usd_yr)} after={mid(alt.usd_yr)} unit="cost" />
      <p className="muted small">{alt.basis}</p>
      </div>
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
  const heatScale = buildScale(state.energy?.assets ?? [], "heat");
  const origin = state.focusOrigin;
  const cardRef = useRef<HTMLDivElement | null>(null);
  const [fromOrigin, setFromOrigin] = useState<{ x: number; y: number } | null>(null);

  // Measure the card before the first paint and start it at the clicked glow (offset from its centre).
  useLayoutEffect(() => {
    if (!assetId || !origin || !cardRef.current) {
      setFromOrigin(null);
      return;
    }
    const rect = cardRef.current.getBoundingClientRect();
    setFromOrigin({ x: origin.x - (rect.left + rect.width / 2), y: origin.y - (rect.top + rect.height / 2) });
  }, [assetId, origin]);

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
    <div className="modal-backdrop energy-alt-backdrop" role="presentation" onClick={close}>
      <div
        ref={cardRef}
        className={`modal energy-alt-card${origin ? (fromOrigin ? " energy-alt-from-glow" : " energy-alt-measuring") : ""}`}
        style={
          fromOrigin
            ? ({ "--from-x": `${fromOrigin.x}px`, "--from-y": `${fromOrigin.y}px` } as React.CSSProperties)
            : undefined
        }
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
        {row.estimated ? <NowRow row={row} scale={heatScale} /> : <p className="muted">Today: not estimated ({row.note}).</p>}
        {row.alternatives.length === 0 ? (
          <p className="empty">
            {row.label === "lamp" || row.label === "ceiling_light"
              ? "Already efficient: these bulbs are LED."
              : "No upgrade in the library applies to this item yet."}
          </p>
        ) : (
          <ul className="energy-alt-list">
            {row.alternatives.map((alt, index) => (
              <AlternativeRow key={alt.upgrade_id} alt={alt} row={row} scale={heatScale} index={index} />
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
