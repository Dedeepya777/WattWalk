/** Model picker (plan 11.3). Five configured test models from GET /models/test. */
import { useState } from "react";
import type { TestModel } from "../contracts";
import { useAppDispatch, useAppState } from "../state";

interface Props {
  onRetry: () => void;
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

export function ModelPicker({
  onRetry,
  onCancelAndSwitch,
  switchBusy,
  switchError,
  onDismissSwitchError,
}: Props) {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const running = state.audit?.status.status === "running";
  const [pending, setPending] = useState<TestModel | null>(null);
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
            {state.testModels.map((model) => {
              const selected = model.sid === state.selectedSid;
              return (
                <li key={model.sid}>
                  <button
                    type="button"
                    className={`model-row ${selected ? "selected" : ""}`}
                    onClick={() => choose(model)}
                    aria-pressed={selected}
                    title={`${model.address}\n${model.note}`}
                  >
                    <span className="model-address">{shortAddress(model)}</span>
                    <span className="model-meta">
                      <span>{model.city}</span>
                      {model.has_fixture || model.has_replay ? (
                        <span className="model-tag model-tag-ready">Instant demo</span>
                      ) : (
                        <span className="model-tag">Live scan</span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}

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
