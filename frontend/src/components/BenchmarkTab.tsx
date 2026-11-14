/** Benchmark tab (plan 11.3). Table only; no charts in the MVP. */
import { formatNumber, formatPercent } from "../format";
import { useAppState } from "../state";

export function BenchmarkTab() {
  const benchmark = useAppState().benchmark;
  const error = useAppState().benchmarkError;

  if (error) return <p className="inline-error">{error}</p>;
  if (!benchmark) return <p className="empty">Loading benchmark…</p>;
  if (benchmark.status === "not_run") {
    return (
      <div className="benchmark">
        <h3>Benchmark not run</h3>
        <p className="empty">
          Small-only, large-only and adaptive routing have not been measured yet.
        </p>
        {benchmark.notes.map((note) => (
          <p key={note} className="muted small">
            {note}
          </p>
        ))}
      </div>
    );
  }

  return (
    <div className="benchmark">
      <p className="small">
        {benchmark.dataset.n_images} labeled crops · labeled by{" "}
        {benchmark.dataset.labeled_by || "—"} · status {benchmark.status}
      </p>
      <div className="table-wrap">
        <table className="data-table benchmark-table">
          <thead>
            <tr>
              <th scope="col">Mode</th>
              <th scope="col">Precision</th>
              <th scope="col">Recall</th>
              <th scope="col">Attr. acc.</th>
              <th scope="col">Abstentions</th>
              <th scope="col">Unsupported</th>
              <th scope="col">Escalation</th>
              <th scope="col">Calls</th>
              <th scope="col">Tokens in</th>
              <th scope="col">Tokens out</th>
              <th scope="col">p50 ms</th>
              <th scope="col">Cache</th>
            </tr>
          </thead>
          <tbody>
            {benchmark.modes.map((mode) => (
              <tr key={mode.mode}>
                <td>{mode.mode.replace("_", " ")}</td>
                <td>{formatPercent(mode.detection_precision)}</td>
                <td>{formatPercent(mode.detection_recall)}</td>
                <td>{formatPercent(mode.attr_accuracy)}</td>
                <td>{formatNumber(mode.correct_abstentions)}</td>
                <td>{formatNumber(mode.unsupported_claims)}</td>
                <td>{formatPercent(mode.escalation_rate)}</td>
                <td>{formatNumber(mode.calls)}</td>
                <td>{formatNumber(mode.tokens_in)}</td>
                <td>{formatNumber(mode.tokens_out)}</td>
                <td>{formatNumber(mode.latency_ms_p50)}</td>
                <td>{formatNumber(mode.cache_hits)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {benchmark.notes.length > 0 ? (
        <ul className="note-list">
          {benchmark.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
