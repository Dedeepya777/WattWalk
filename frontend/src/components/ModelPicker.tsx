/** Model picker (plan 11.3). Five configured test models from GET /models/test. */
import { useState } from "react";
import type { TestModel } from "../contracts";
import { FIXTURE_SID } from "../fixtures";
import { useAppDispatch, useAppState } from "../state";
import { BirdsEyeThumb, BirdsEyeViewer } from "./BirdsEye";
import { FindBuilding } from "./FindBuilding";

interface Props {
  onRetry: () => void;
  /** Reload the apartments list (after a building was added). */
  onReload: () => Promise<void>;
  /** Cancel the running audit (waiting up to 5 s), then select the target scan. */
  onCancelAndSwitch: (sid: string) => Promise<boolean>;
  switchBusy: boolean;
  switchError: string | null;
  onDismissSwitchError: () => void;
}

/** "215 W 7th St, Unit 301" from "215 W 7th St, Unit 301, Los Angeles, CA" (city and state dropped). */
function shortAddress(model: TestModel): string {
  const parts = model.address.split(",").map((part) => part.trim());
  const cut = parts.findIndex((part, index) => index > 0 && part.toLowerCase().startsWith(model.city.toLowerCase().split(" ")[0]));
  return (cut > 0 ? parts.slice(0, cut) : parts.slice(0, 2)).join(", ");
}

export interface BuildingGroup {
  key: string;
  street: string;
  models: TestModel[];
}

/** Apartments grouped by building (street address); the demo fixture last. */
export function groupModels(models: TestModel[]): BuildingGroup[] {
  const groups = new Map<string, BuildingGroup>();
  for (const model of models) {
    const street = model.address.split(",")[0].trim();
    const key = street.toLowerCase();
    if (!groups.has(key)) groups.set(key, { key, street, models: [] });
    groups.get(key)!.models.push(model);
  }
  return [...groups.values()].sort(
    (a, b) => Number(a.models[0].sid === FIXTURE_SID) - Number(b.models[0].sid === FIXTURE_SID),
  );
}

/** "Studio - 331" from "1830 N Cherokee Ave, Studio - 331, Los Angeles, CA". */
export function unitName(model: TestModel): string {
  const parts = shortAddress(model).split(",").map((part) => part.trim());
  return parts.length > 1 ? parts.slice(1).join(", ") : "Scanned unit";
}

export function ModelPicker({
  onRetry,
  onReload,
  onCancelAndSwitch,
  switchBusy,
  switchError,
  onDismissSwitchError,
}: Props) {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const running = state.audit?.status.status === "running";
  const [pending, setPending] = useState<TestModel | null>(null);
  const [finding, setFinding] = useState(false);
  const [aerial, setAerial] = useState<{ sid: string; label: string } | null>(null);
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set());
  const toggleGroup = (key: string) =>
    setOpenGroups((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const currentAddress =
    state.testModels.find((model) => model.sid === state.selectedSid)?.address ??
    state.selectedSid;

  const choose = (model: TestModel) => {
    if (model.sid === state.selectedSid) return;
    if (running) {
      onDismissSwitchError();
      setPending(model);
      return;
    }
    dispatch({ type: "selectSid", sid: model.sid });
  };

  return (
    <section className="panel" aria-labelledby="models-heading">
      <div className="panel-heading">
        <h2 id="models-heading">Apartments</h2>
        <button type="button" className="add-building" onClick={() => setFinding(true)}>
          + Add building
        </button>
      </div>
      {state.modelsError ? (
        <div className="inline-error">
          <p>{state.modelsError}</p>
          <button className="button small" onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : state.testModels.length === 0 ? (
        <p className="empty">No test models configured.</p>
      ) : (
        <>
          <ul className="model-list">
            {groupModels(state.testModels).map((group) => {
              const single = group.models.length === 1;
              const hasSelected = group.models.some((model) => model.sid === state.selectedSid);
              const expanded = !single && (openGroups.has(group.key) || hasSelected);
              const only = group.models[0];
              const ready = (model: TestModel) => model.has_fixture || model.has_replay;
              return (
                <li key={group.key} className={`model-item${hasSelected ? " has-selected" : ""}`}>
                  <BirdsEyeThumb
                    sid={only.sid}
                    label={group.street}
                    onOpen={() => setAerial({ sid: only.sid, label: group.street })}
                  />
                  <button
                    type="button"
                    className={`model-row ${single && hasSelected ? "selected" : ""}`}
                    onClick={() => (single ? choose(only) : toggleGroup(group.key))}
                    aria-pressed={single ? hasSelected : undefined}
                    aria-expanded={single ? undefined : expanded}
                    title={single ? `${only.address}\n${only.note}` : `${group.street}: ${group.models.length} units`}
                  >
                    <span className="model-address">{single ? shortAddress(only) : group.street}</span>
                    <span className="model-meta">
                      <span>{only.city}</span>
                      {single ? (
                        ready(only) ? (
                          <span className="model-tag model-tag-ready">Instant demo</span>
                        ) : (
                          <span className="model-tag">Live scan</span>
                        )
                      ) : (
                        <span className="model-tag model-tag-units">
                          {group.models.length} units {expanded ? "▴" : "▾"}
                        </span>
                      )}
                    </span>
                  </button>
                  {expanded ? (
                    <ul className="unit-list">
                      <li>
                        <button
                          type="button"
                          className={`unit-row unit-overview${state.buildingView === group.key ? " selected" : ""}`}
                          onClick={() => dispatch({ type: "buildingView", key: group.key })}
                        >
                          <span className="unit-name">Building overview</span>
                          <span aria-hidden="true">→</span>
                        </button>
                      </li>
                      {group.models.map((model) => {
                        const selected = model.sid === state.selectedSid && !state.buildingView;
                        return (
                          <li key={model.sid}>
                            <button
                              type="button"
                              className={`unit-row${selected ? " selected" : ""}`}
                              onClick={() => choose(model)}
                              aria-pressed={selected}
                              title={model.address}
                            >
                              <span className="unit-name">{unitName(model)}</span>
                              {ready(model) ? <span className="model-tag model-tag-ready">Instant demo</span> : null}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      )}

      {aerial ? (
        <BirdsEyeViewer sid={aerial.sid} label={aerial.label} onClose={() => setAerial(null)} />
      ) : null}

      {finding ? (
        <FindBuilding
          onClose={() => setFinding(false)}
          onAdded={async (firstSid) => {
            await onReload();
            setFinding(false);
            if (!running) dispatch({ type: "selectSid", sid: firstSid });
          }}
        />
      ) : null}

      {pending ? (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => {
            if (!switchBusy) setPending(null);
          }}
        >
          <div
            className="modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="switch-scan-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="switch-scan-title">Switch scan?</h2>
            </div>
            <p>
              An audit for {currentAddress} is running. Cancel it and switch to{" "}
              {pending.address}?
            </p>
            {switchError ? <p className="inline-error">{switchError}</p> : null}
            <p className="muted small">
              If you keep it running, Start stays disabled until that audit finishes or you
              cancel it. The audit keeps running on the server either way.
            </p>
            <div className="modal-actions">
              <button
                className="button primary"
                disabled={switchBusy}
                onClick={async () => {
                  const switched = await onCancelAndSwitch(pending.sid);
                  if (switched) setPending(null);
                }}
              >
                {switchBusy ? <span className="spinner" aria-hidden="true" /> : null}
                Cancel audit and switch
              </button>
              <button
                className="button"
                disabled={switchBusy}
                onClick={() => {
                  onDismissSwitchError();
                  setPending(null);
                }}
              >
                Keep running
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
