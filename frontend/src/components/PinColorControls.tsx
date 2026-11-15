/** "Pins: Details | Cost | Heat" switch and its colour legend (step 3 of the energy view). */
import { useAppDispatch, useAppState } from "../state";
import { LEGEND_CSS, REMOVES_HEAT, buildScale, legendLabels, toHex, type PinColorMode } from "../viewer/energyColor";

const MODES: { mode: PinColorMode; label: string; title: string }[] = [
  { mode: "heat", label: "Heat", title: "Colour by heat added to the room per year (blue low, red high)" },
  { mode: "cost", label: "Cost", title: "Colour by electricity cost per year (blue low, red high)" },
];

export function PinColorControls() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const hasEnergy = (state.energy?.assets.length ?? 0) > 0;
  const scale = buildScale(state.energy?.assets ?? [], state.pinColorMode);
  const labels = scale ? legendLabels(scale) : null;

  return (
    <div className="pin-color-controls">
      <div className="segmented" role="group" aria-label="Colour items by">
        {MODES.map(({ mode, label, title }) => {
          const disabled = mode !== "details" && !hasEnergy;
          return (
            <button
              key={mode}
              type="button"
              className={state.pinColorMode === mode ? "segmented-button active" : "segmented-button"}
              aria-pressed={state.pinColorMode === mode}
              disabled={disabled}
              title={disabled ? "Energy estimates appear once the inventory is ready" : title}
              onClick={() => dispatch({ type: "pinColor", mode })}
            >
              {label}
            </button>
          );
        })}
      </div>
      {labels ? (
        <div className="energy-legend" role="img" aria-label={`${labels.title}: ${labels.low} (blue) to ${labels.high} (red)`}>
          <span className="muted small">{labels.low}</span>
          <span className="energy-legend-bar" style={{ background: LEGEND_CSS }} />
          <span className="muted small">{labels.high}</span>
          {scale?.mode === "heat" &&
          (state.energy?.assets ?? []).some((row) => (row.heat_kwh_yr?.[0] ?? 0) < 0) ? (
            <span className="energy-legend-key muted small">
              <span className="energy-swatch" style={{ background: toHex(REMOVES_HEAT) }} /> removes heat
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
