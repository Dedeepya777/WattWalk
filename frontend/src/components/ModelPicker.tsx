/** Model picker (plan 11.3). Five configured test models from GET /models/test. */
import { useState } from "react";
import type { TestModel } from "../contracts";
import { formatNumber } from "../format";
import { useAppDispatch, useAppState } from "../state";

interface Props {
  onRetry: () => void;
  /** Cancel the running audit (waiting up to 5 s), then select the target scan. */
  onCancelAndSwitch: (sid: string) => Promise<boolean>;
  switchBusy: boolean;
  switchError: string | null;
  onDismissSwitchError: () => void;
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
        <h2 id="models-heading">Choose a scan</h2>
        <span className="muted small">{formatNumber(state.testModels.length)} models</span>
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
          {running ? (
            <p className="hint small">
              An audit is running. Switching scans asks you to cancel it first; you can keep it
              running and come back later.
            </p>
          ) : null}
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
                  >
                    <span className="model-address">{model.address}</span>
                    <span className="model-meta">
                      <span>{model.city}</span>
                      <span className="model-sid">{model.sid}</span>
                    </span>
                    <span className="model-note">{model.note}</span>
                    <span className="badge-row">
                      {model.has_fixture ? <span className="badge badge-ok">fixture</span> : null}
                      {model.has_replay ? <span className="badge badge-info">replay</span> : null}
                      {!model.has_fixture && !model.has_replay ? (
                        <span className="badge badge-muted">live only</span>
                      ) : null}
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
