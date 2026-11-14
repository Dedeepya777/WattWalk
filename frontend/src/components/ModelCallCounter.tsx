/** Model-call counter (plan 11.3). Values come from model_call_summary. */
import { formatNumber } from "../format";
import { useAppState } from "../state";

export function ModelCallCounter() {
  const summary = useAppState().audit?.model_call_summary;
  const total = summary?.calls_total ?? 0;
  return (
    <div className="model-counter" aria-label="Model call counter">
      <div className="model-counter-total">
        <span className="model-counter-number">{formatNumber(total)}</span>
        <span className="model-counter-label">model calls</span>
      </div>
      <dl>
        <div>
          <dt>small</dt>
          <dd>{formatNumber(summary?.calls_small ?? 0)}</dd>
        </div>
        <div>
          <dt>large</dt>
          <dd>{formatNumber(summary?.calls_large ?? 0)}</dd>
        </div>
        <div>
          <dt>planner</dt>
          <dd>{formatNumber(summary?.calls_planner ?? 0)}</dd>
        </div>
        <div>
          <dt>cache</dt>
          <dd>{formatNumber(summary?.cache_hits ?? 0)}</dd>
        </div>
      </dl>
    </div>
  );
}
