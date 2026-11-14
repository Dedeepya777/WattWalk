/** Model picker (plan 11.3). Five configured test models from GET /models/test. */
import { formatNumber } from "../format";
import { useAppDispatch, useAppState } from "../state";

export function ModelPicker({ onRetry }: { onRetry: () => void }) {
  const state = useAppState();
  const dispatch = useAppDispatch();
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
        <ul className="model-list">
          {state.testModels.map((model) => {
            const selected = model.sid === state.selectedSid;
            return (
              <li key={model.sid}>
                <button
                  type="button"
                  className={`model-row ${selected ? "selected" : ""}`}
                  onClick={() => dispatch({ type: "selectSid", sid: model.sid })}
                  disabled={running}
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
      )}
    </section>
  );
}
