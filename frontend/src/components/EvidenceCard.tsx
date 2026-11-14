/** Evidence card drawer (plan 11.3): crops, source chips, next step, corrections. */
import { useEffect, useState } from "react";
import {
  ApiFailure,
  consumeFixtureNotice,
  fileUrl,
  postCorrection,
} from "../api";
import type { AssetEnergy, AssetLabel, CorrectionRequest, PlanResponse } from "../contracts";
import {
  attrText,
  attrValueText,
  formatKwh,
  formatRange,
  labelText,
  unknownAttrCount,
} from "../format";
import { useAppDispatch, useAppState } from "../state";
import { SourceChip } from "./SourceChip";

/** Energy and heat of one asset (GET /audits/{sid}/energy). Ranges widen when details were not seen. */
function EnergySection({ row }: { row: AssetEnergy | null }) {
  if (!row) {
    return (
      <section>
        <h3>Energy and heat</h3>
        <p className="empty">Estimates appear once the inventory is ready.</p>
      </section>
    );
  }
  if (!row.estimated) {
    return (
      <section>
        <h3>Energy and heat</h3>
        <p className="muted">Not estimated: {row.note}</p>
      </section>
    );
  }
  const heat = row.heat_kwh_yr;
  const removes = heat !== null && heat[0] < 0;
  const heatAbs: [number, number] | null = heat ? [Math.abs(heat[0]), Math.abs(heat[1])] : null;
  return (
    <section>
      <h3>Energy and heat</h3>
      <dl className="energy-grid">
        <dt>Electricity per year</dt>
        <dd>{formatRange(row.kwh_yr, "kWh")}</dd>
        <dt>Cost per year</dt>
        <dd>{formatRange(row.usd_yr, "", true)}</dd>
        <dt>{removes ? "Heat moved outside per year" : "Heat into the room per year"}</dt>
        <dd>{formatRange(heatAbs, "kWh")}</dd>
        {row.power_w ? (
          <>
            <dt>Power while running</dt>
            <dd>{formatRange(row.power_w, "W")}</dd>
          </>
        ) : null}
      </dl>
      <p className="muted small">{row.basis}</p>
      {row.assumed.length > 0 ? (
        <p className="muted small">
          Assumed, not seen in the scan: {row.assumed.map((key) => attrText(key)).join(", ")}
        </p>
      ) : null}
      {row.note ? <p className="muted small">{row.note}</p> : null}
    </section>
  );
}

const STRING_FIELDS: Partial<Record<AssetLabel, Record<string, string[]>>> = {
  window: {
    panes: ["single", "double", "unknown"],
    shading: ["blinds", "curtains", "shutters", "none", "unknown"],
  },
  ceiling_light: { bulb_type: ["led", "cfl", "incandescent", "unknown"] },
  lamp: { bulb_type: ["led", "cfl", "incandescent", "unknown"] },
  thermostat: { thermostat_type: ["smart", "digital", "dial", "unknown"] },
  refrigerator: {
    style: ["top_freezer", "bottom_freezer", "side_by_side", "french_door", "unknown"],
  },
};

const NUMBER_FIELDS: Partial<Record<AssetLabel, Record<string, { min: number; max: number; step: number }>>> = {
  window: {
    width_m: { min: 0.2, max: 5, step: 0.1 },
    height_m: { min: 0.2, max: 5, step: 0.1 },
  },
  ceiling_light: { bulb_count: { min: 1, max: 12, step: 1 } },
  lamp: { bulb_count: { min: 1, max: 12, step: 1 } },
  refrigerator: { age_years: { min: 0, max: 60, step: 1 } },
};

function shortUpgradeName(id: string, fallback: string): string {
  const names: Record<string, string> = {
    led: "LED",
    window_film: "Window film",
    fridge: "Fridge",
    heat_pump: "Heat pump",
    smart_thermostat: "Thermostat",
  };
  return names[id] ?? fallback;
}

function planDiff(oldPlan: PlanResponse | null, newPlan: PlanResponse): string[] {
  if (!oldPlan) return [];
  const oldLines = new Map(oldPlan.upgrades.map((line) => [line.upgrade_id, line] as const));
  return newPlan.upgrades.flatMap((line) => {
    const before = oldLines.get(line.upgrade_id);
    if (!before || before.kwh_saved_yr === line.kwh_saved_yr) return [];
    return [
      `${shortUpgradeName(line.upgrade_id, line.name)}: ${formatKwh(
        before.kwh_saved_yr,
      ).replace(" kWh/yr", "")} to ${formatKwh(line.kwh_saved_yr)}`,
    ];
  });
}

export function EvidenceCard() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const asset = state.audit?.inventory.find((item) => item.id === state.selectedAssetId) ?? null;
  const [field, setField] = useState("");
  const [value, setValue] = useState("");
  const [mergeInto, setMergeInto] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fieldOptions = asset
    ? Object.keys({
        ...(STRING_FIELDS[asset.label] ?? {}),
        ...(NUMBER_FIELDS[asset.label] ?? {}),
      })
    : [];

  useEffect(() => {
    setField(fieldOptions[0] ?? "");
    setValue("");
    setMergeInto("");
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asset?.id]);

  if (!asset) return null;

  const room = state.audit?.rooms.find((item) => item.id === asset.room_id);
  const observations = (state.audit?.observations ?? []).filter((item) =>
    asset.observation_ids.includes(item.id),
  );
  const dependentUpgrades =
    state.plan?.upgrades.filter((line) => line.asset_ids.includes(asset.id)) ?? [];
  const running = state.audit?.status.status === "running";
  const stringValues = STRING_FIELDS[asset.label]?.[field];
  const numberSpec = NUMBER_FIELDS[asset.label]?.[field];
  const mergeCandidates =
    state.audit?.inventory.filter(
      (item) => item.id !== asset.id && item.label === asset.label,
    ) ?? [];

  const close = () => dispatch({ type: "selectAsset", assetId: null });

  const submit = async (request: CorrectionRequest) => {
    setBusy(true);
    setError(null);
    try {
      const response = await postCorrection(state.selectedSid, request);
      dispatch({
        type: "correction",
        response,
        diff: planDiff(state.plan, response.plan),
        changed: response.changed_asset_ids,
      });
      const notice = consumeFixtureNotice();
      if (notice) dispatch({ type: "fixtureNotice", notice });
      window.setTimeout(() => dispatch({ type: "changed", ids: [] }), 3000);
    } catch (failure) {
      if (failure instanceof ApiFailure) {
        setError(failure.message);
      } else {
        setError("Correction failed.");
      }
    } finally {
      setBusy(false);
    }
  };

  const applyCorrection = () => {
    if (!field) return;
    const parsed = numberSpec ? Number(value) : value;
    if (numberSpec && (Number.isNaN(parsed) || value.trim() === "")) {
      setError(`${attrText(field)} needs a number.`);
      return;
    }
    if (!numberSpec && !value) {
      setError(`Choose a value for ${attrText(field)}.`);
      return;
    }
    void submit({
      asset_id: asset.id,
      field,
      value: parsed,
      plan_request: state.planRequest,
    });
  };

  return (
    <div className="drawer-backdrop" role="presentation" onClick={close}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="drawer-head">
          <div>
            <h2 id="evidence-title">{labelText(asset.label)}</h2>
            <p className="muted small">
              {room?.label ?? "Unknown room"} · {asset.id} ·{" "}
              {unknownAttrCount(asset.attrs)} unknown attribute
              {unknownAttrCount(asset.attrs) === 1 ? "" : "s"}
            </p>
          </div>
          <button className="icon-button" onClick={close} aria-label="Close evidence card">
            ×
          </button>
        </div>

        <section>
          <h3>Evidence crops</h3>
          <p className="muted small">
            Seen in {observations.length} observation{observations.length === 1 ? "" : "s"}.
            Crops are served by GET /audits/{"{sid}"}/files/crops/…
          </p>
          <div className="crop-grid">
            {observations.map((observation) => {
              const url = fileUrl(state.selectedSid, observation.crop_ref);
              return (
                <figure className="crop-frame" key={observation.id}>
                  <div className="crop-placeholder" aria-hidden={url ? "true" : undefined}>
                    <span className="crop-box" />
                    <span className="muted small">
                      {state.audit?.status.mode === "fixture"
                        ? "Sample audit: no real photo"
                        : observation.crop_ref}
                    </span>
                  </div>
                  {url ? (
                    <img
                      className="crop-img"
                      src={url}
                      alt={`Crop of ${labelText(asset.label)} from ${observation.pano_id} face ${observation.face}`}
                      onError={(event) => {
                        (event.currentTarget as HTMLImageElement).classList.add("broken");
                      }}
                      onLoad={(event) => {
                        // Fixture audits ship 1x1 placeholder crops (no real photos in the repo):
                        // show the labelled placeholder instead of a stretched black pixel.
                        const img = event.currentTarget as HTMLImageElement;
                        if (img.naturalWidth <= 2 || img.naturalHeight <= 2) img.classList.add("broken");
                      }}
                    />
                  ) : null}
                  <figcaption>
                    <span className="mono">{observation.id}</span> · {observation.pano_id} face{" "}
                    {observation.face} · {observation.resolution}
                    {observation.escalated ? (
                      <span className="badge badge-info"> escalated </span>
                    ) : null}
                  </figcaption>
                </figure>
              );
            })}
          </div>
        </section>

        <section>
          <h3>Attributes</h3>
          {Object.keys(asset.attrs).length === 0 ? (
            <p className="empty">No attributes for this label.</p>
          ) : (
            <ul className="evidence-attrs">
              {Object.entries(asset.attrs).map(([key, attr]) => (
                <li key={key} className="evidence-attr">
                  <div className="evidence-attr-head">
                    <span className="attr-key">{attrText(key)}</span>
                    <span className="attr-value">{attrValueText(key, attr)}</span>
                    <SourceChip source={attr.source} note={attr.note} />
                  </div>
                  {attr.note ? <p className="muted small">{attr.note}</p> : null}
                </li>
              ))}
            </ul>
          )}
          {asset.disagreement ? (
            <p className="inline-error">
              Observations disagree on at least one attribute. The escalated result is shown
              where available.
            </p>
          ) : null}
        </section>

        <EnergySection row={state.energy?.assets.find((row) => row.asset_id === asset.id) ?? null} />

        <section>
          <h3>Next step</h3>
          <p>{asset.next_step || "Nothing unknown for this asset."}</p>
        </section>

        <section>
          <h3>Upgrades that use this asset</h3>
          {dependentUpgrades.length === 0 ? (
            <p className="empty">No upgrade in the current package uses this asset.</p>
          ) : (
            <ul className="note-list">
              {dependentUpgrades.map((line) => (
                <li key={line.upgrade_id}>
                  {line.name} · {formatKwh(line.kwh_saved_yr)} ·{" "}
                  {line.explanation}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="correction-block">
          <h3>Correct this finding</h3>
          {running ? (
            <p className="hint">Corrections are disabled while the audit is running.</p>
          ) : null}
          <div className="correction-form">
            <label className="field">
              <span>Attribute</span>
              <select
                value={field}
                disabled={running || busy || fieldOptions.length === 0}
                onChange={(event) => {
                  setField(event.target.value);
                  setValue("");
                }}
              >
                {fieldOptions.length === 0 ? <option value="">No editable attribute</option> : null}
                {fieldOptions.map((option) => (
                  <option key={option} value={option}>
                    {attrText(option)}
                  </option>
                ))}
              </select>
            </label>

            {stringValues ? (
              <label className="field">
                <span>Value</span>
                <select
                  value={value}
                  disabled={running || busy}
                  onChange={(event) => setValue(event.target.value)}
                >
                  <option value="">Choose…</option>
                  {stringValues.map((option) => (
                    <option key={option} value={option}>
                      {option.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </label>
            ) : numberSpec ? (
              <label className="field">
                <span>Value</span>
                <input
                  type="number"
                  min={numberSpec.min}
                  max={numberSpec.max}
                  step={numberSpec.step}
                  value={value}
                  disabled={running || busy}
                  onChange={(event) => setValue(event.target.value)}
                />
              </label>
            ) : null}

            <button
              className="button primary"
              disabled={running || busy || !field}
              onClick={applyCorrection}
            >
              {busy ? "Applying…" : "Apply correction"}
            </button>
          </div>

          {mergeCandidates.length > 0 ? (
            <div className="merge-form">
              <label className="field">
                <span>Mark duplicate of</span>
                <select
                  value={mergeInto}
                  disabled={running || busy}
                  onChange={(event) => setMergeInto(event.target.value)}
                >
                  <option value="">Choose another {labelText(asset.label).toLowerCase()}…</option>
                  {mergeCandidates.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.id} · {candidate.observation_ids.join(", ")}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="button"
                disabled={running || busy || !mergeInto}
                onClick={() =>
                  void submit({
                    asset_id: asset.id,
                    field: "merge_into",
                    value: mergeInto,
                    plan_request: state.planRequest,
                  })
                }
              >
                Merge duplicate
              </button>
            </div>
          ) : null}

          {error ? (
            <p className="inline-error" role="alert">
              {error}
            </p>
          ) : null}
        </section>
      </aside>
    </div>
  );
}
