/**
 * Energy alternatives card (step 2 of the energy alternatives feature): one asset's energy today and
 * the upgrades that apply to it, from GET /audits/{sid}/energy. Opened from the evidence card's
 * "Compare alternatives" button. Plain on purpose: the expanding animation and the glows come later.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { fileUrl, postResearchAlternatives } from "../api";
import type { AiAlternativesResponse, AssetEnergy, EnergyAlternative } from "../contracts";
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

const GLOW_MAX = 84; // px, today's glow (centred card)
const POP_WIDTH = 380; // px, the pop-out next to a 3D pin
const POP_MARGIN = 12;

/** CSS variables for the bubble: it starts as the pressed glow (radius r around the click point x, y)
 *  and ends as the card's box. */
function bubbleFrom(card: { left: number; top: number; h: number }, x: number, y: number, r: number): Record<string, string> {
  return {
    "--bx0": `${x - r}px`,
    "--by0": `${y - r}px`,
    "--bs0": `${2 * r}px`,
    "--bx1": `${card.left}px`,
    "--by1": `${card.top}px`,
    "--bw1": `${POP_WIDTH}px`,
    "--bh1": `${card.h}px`,
  };
}

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

function Glow({ size, color }: { size: number; color: string; from?: number }) {
  const current = size;
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
  if (share === null) return null;
  const width = share * 100;
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

/** Pop-out: today's cost as the one big number, heat as a short line under it. */
function PopNow({ row, scale }: { row: AssetEnergy; scale: EnergyScale | null }) {
  const heat = mid(row.heat_kwh_yr);
  return (
    <section className="energy-alt-now pop-row pop-now">
      <div>
        <div className="pop-kicker">
          <span className="pop-dot" style={{ background: glowColor(heat, scale) }} aria-hidden="true" />
          Today
        </div>
        <div className="pop-big">
          {formatRange(row.usd_yr, "", true)}
          <span className="pop-unit">/yr</span>
        </div>
      </div>
    </section>
  );
}

/** Pop-out: the upgrade, what it saves (big), and cost and payback in one line. */
function PopAlt({ alt, row, ai = false }: { alt: EnergyAlternative; row: AssetEnergy; ai?: boolean }) {
  const dispatch = useAppDispatch();
  const picked = useAppState().chosenUpgrades[row.asset_id] === alt.upgrade_id;
  const toggle = () =>
    dispatch({ type: "chooseUpgrade", assetId: row.asset_id, upgradeId: picked ? null : alt.upgrade_id });
  const free = alt.cost_usd[1] <= 0;
  return (
    <li
      className={`energy-alt-option energy-alt-with-glow pop-row pop-pickable${picked ? " pop-picked" : ""}`}
      role="checkbox"
      aria-checked={picked}
      tabIndex={0}
      title={picked ? "Shown on the heat map (click to unpick)" : "Pick this upgrade to show it on the heat map"}
      onClick={toggle}
      onKeyDown={(event) => {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          toggle();
        }
      }}
    >
      <span className="pop-check" aria-hidden="true">{picked ? "✓" : ""}</span>
      <div>
        <div className="pop-title">
          {alt.title}
          {ai ? <span className="pop-ai-tag" title={alt.basis}>estimate</span> : null}
        </div>
        <div className="pop-save">
          Save {formatRange(alt.saves_usd_yr, "", true)}
          <span className="pop-unit">/yr</span>
        </div>
        <div className="pop-sub">
          {free ? "Free" : `Pays back in ${formatPayback(alt.payback_years)}`}
          {alt.products?.[0] ? (
            <>
              {" · "}
              <a
                className="pop-shop"
                href={alt.products[0].url}
                target="_blank"
                rel="noopener noreferrer"
                title={`${alt.products[0].name} (opens on Amazon)`}
                // Opening a product must not pick or unpick the upgrade.
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
              >
                Shop ↗
              </a>
            </>
          ) : null}
        </div>
      </div>
    </li>
  );
}

/** The item's clearest photo: the crop with the largest box (a sharper, closer view). */
function PopPhoto({ assetId }: { assetId: string }) {
  const state = useAppState();
  const [hidden, setHidden] = useState(false);
  const asset = state.audit?.inventory.find((item) => item.id === assetId);
  const ids = new Set(asset?.observation_ids ?? []);
  const area = (o: { bbox: { x0: number; y0: number; x1: number; y1: number } }) =>
    (o.bbox.x1 - o.bbox.x0) * (o.bbox.y1 - o.bbox.y0);
  const best = (state.audit?.observations ?? [])
    .filter((o) => ids.has(o.id) && o.crop_ref)
    .sort((a, b) => area(b) - area(a))[0];
  const url = best ? fileUrl(state.selectedSid, best.crop_ref) : null;
  useEffect(() => setHidden(false), [url]);
  if (!url || hidden) return null;
  return (
    <figure className="pop-photo">
      <img
        src={url}
        alt={asset ? `Photo of the ${asset.label.replace(/_/g, " ")}` : "Photo of the item"}
        onError={() => setHidden(true)}
        onLoad={(event) => {
          // Demo audits ship 1x1 placeholder crops: hide them rather than show a stretched pixel.
          const img = event.currentTarget;
          if (img.naturalWidth <= 2 || img.naturalHeight <= 2) setHidden(true);
        }}
      />
    </figure>
  );
}

type AiState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; data: AiAlternativesResponse }
  | { status: "error"; message: string };

/** Pop-out: "Find more alternatives" asks DeepSeek for 2-3 rough ideas and lists them, marked as AI. */
function PopAiAlternatives({ sid, row }: { sid: string; row: AssetEnergy }) {
  // Fetched ideas live in the app state, so the card shows them again at once and the heat map's
  // "After upgrades" preview can use them.
  const dispatch = useAppDispatch();
  const saved = useAppState().aiAlternatives[row.asset_id];
  const key = `${sid}:${row.asset_id}`;
  const [ai, setAi] = useState<AiState>(() => (saved ? { status: "done", data: saved } : { status: "idle" }));
  useEffect(() => {
    setAi(saved ? { status: "done", data: saved } : { status: "idle" });
  }, [key, saved]);

  const find = async (refresh: boolean) => {
    setAi({ status: "loading" });
    try {
      const data = await postResearchAlternatives(sid, row.asset_id, refresh);
      dispatch({ type: "aiAlternatives", data });
      setAi({ status: "done", data });
    } catch (error) {
      setAi({ status: "error", message: error instanceof Error ? error.message : String(error) });
    }
  };

  if (ai.status === "idle") {
    return (
      <button className="pop-ai-button" onClick={() => void find(false)}>
        More options
      </button>
    );
  }
  if (ai.status === "loading") {
    return (
      <div className="pop-ai-button pop-ai-loading" role="status">
        <span className="spinner" aria-hidden="true" /> Looking for more options…
      </div>
    );
  }
  if (ai.status === "error") {
    return (
      <div className="pop-ai-error" role="alert">
        <span>{ai.message}</span>
        <button className="pop-link" onClick={() => void find(false)}>
          Try again
        </button>
      </div>
    );
  }
  const { data } = ai;
  // For an item with no sourced estimate, the ideas are relative to the model's estimate of today.
  const base: AssetEnergy = data.today_kwh_yr ? { ...row, kwh_yr: data.today_kwh_yr, usd_yr: data.today_usd_yr } : row;
  return (
    <section className="pop-ai">
      {data.today_usd_yr ? (
        <p className="pop-ai-today">
          Today, roughly <strong>{formatRange(data.today_usd_yr, "", true)}/yr</strong>
          <span className="pop-ai-tag">estimate</span>
        </p>
      ) : null}
      {data.alternatives.length ? (
        <ul className="energy-alt-list">
          {data.alternatives.map((alt) => (
            <PopAlt key={alt.upgrade_id} alt={alt} row={base} ai />
          ))}
        </ul>
      ) : (
        <p className="empty">{data.note}</p>
      )}
      <button className="pop-link" onClick={() => void find(true)}>
        Look again
      </button>
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
  const [place, setPlace] = useState<{ left: number; top: number; ox: number; oy: number; h: number } | null>(null);

  // Pop-out mode (opened from a 3D pin or glow): measure before the first paint, sit beside the clicked
  // point (right of it, or left if there is no room), stay on screen, and grow out of that point.
  useLayoutEffect(() => {
    if (!assetId || !origin || !cardRef.current) {
      setPlace(null);
      return;
    }
    const cardRect = cardRef.current.getBoundingClientRect();
    const h = cardRect.height;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    // Put the card's "Today" glow exactly on the pressed button, so the button becomes that glow and the
    // card grows out around it. Clamp to the screen (the reveal still starts at the button).
    const todayGlow = cardRef.current.querySelector(".energy-alt-now .energy-alt-glow-box");
    let gx = 46;
    let gy = 110;
    if (todayGlow) {
      const g = todayGlow.getBoundingClientRect();
      gx = g.left - cardRect.left + g.width / 2;
      gy = g.top - cardRect.top + g.height / 2;
    }
    const left = Math.max(POP_MARGIN, Math.min(origin.x - gx, vw - POP_WIDTH - POP_MARGIN));
    const top = Math.max(POP_MARGIN, Math.min(origin.y - gy, vh - h - POP_MARGIN));
    const ox = origin.x - left;
    const oy = origin.y - top;
    setPlace({ left, top, ox, oy, h });
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

  const popout = Boolean(origin);
  const cardClass = popout
    ? `energy-pop${place ? " energy-pop-in" : " energy-pop-measuring"}`
    : "modal energy-alt-card";
  const cardStyle = popout
    ? ({
        left: place?.left ?? 0,
        top: place?.top ?? 0,
        width: POP_WIDTH,
      } as React.CSSProperties)
    : undefined;

  return (
    <div
      className={popout ? "energy-pop-catcher" : "modal-backdrop energy-alt-backdrop"}
      role="presentation"
      onClick={close}
    >
      {popout && place && origin ? (
        // The pressed glow itself: same place, size and colour, it grows into the card's shape.
        <div
          className="energy-pop-bubble"
          aria-hidden="true"
          style={{
            ...bubbleFrom(place, origin.x, origin.y, origin.r ?? 14),
            ["--seed" as string]: origin.color ?? "#f97316",
          } as React.CSSProperties}
        />
      ) : null}
      <div
        ref={cardRef}
        className={cardClass}
        style={cardStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby="energy-alt-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2 id="energy-alt-title">{popout ? labelText(row.label) : `${labelText(row.label)}: alternatives`}</h2>
            <p className="muted small">
              {room ?? "Unknown room"}
              {popout ? "" : ` · ${row.asset_id}`}
            </p>
          </div>
          <div className="energy-pop-actions">
            {popout ? null : <button
              className="button small"
              onClick={() => {
                dispatch({ type: "focusEnergy", assetId: null });
                dispatch({ type: "selectAsset", assetId: row.asset_id });
              }}
            >
              See evidence
            </button>}
            <button className="button small" onClick={close} aria-label="Close">
              ×
            </button>
          </div>
        </div>
        {popout ? <PopPhoto assetId={row.asset_id} /> : null}
        {row.estimated ? (
          popout ? <PopNow row={row} scale={heatScale} /> : <NowRow row={row} scale={heatScale} />
        ) : (
          <p className="muted">Today: not estimated ({row.note}).</p>
        )}
        {row.alternatives.length === 0 && popout ? null : row.alternatives.length === 0 ? (
          <p className="empty">
            {row.label === "lamp" || row.label === "ceiling_light"
              ? "Already efficient: these bulbs are LED."
              : "No upgrade in the library applies to this item yet."}
          </p>
        ) : (
          <ul className="energy-alt-list">
            {row.alternatives.map((alt, index) =>
              popout ? (
                <PopAlt key={alt.upgrade_id} alt={alt} row={row} />
              ) : (
                <AlternativeRow key={alt.upgrade_id} alt={alt} row={row} scale={heatScale} index={index} />
              ),
            )}
          </ul>
        )}
        {popout && state.selectedSid ? <PopAiAlternatives sid={state.selectedSid} row={row} /> : null}
        {popout ? null : (
          <p className="muted small">
            Ranges come from the same assumptions as the upgrade plan. Upgrade costs are installed cost
            ranges from the plan's upgrade library.
          </p>
        )}
      </div>
    </div>
  );
}
