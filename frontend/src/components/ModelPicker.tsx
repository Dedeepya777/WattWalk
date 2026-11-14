/** Model picker (plan 11.3). Five configured test models from GET /models/test. */
import { formatNumber } from "../format";
import { useAppDispatch, useAppState } from "../state";

export function ModelPicker({ onRetry }: { onRetry: () => void }) {
  const state = useAppState();
  const dispatch = useAppDispatch();
  // Switching is allowed during a run: audits run on the server per model, so the run keeps going,
  // and selecting the model again reattaches to its events (App.tsx). Only Start/Cancel act on a run.
  const running = state.audit?.status.status === "running";

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
            This audit keeps running if you switch scans. Come back to it to cancel it or see progress.
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
                  onClick={() => dispatch({ type: "selectSid", sid: model.sid })}
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
    </section>
  );
}
