/** Coverage tab (plan 11.3 and 7.8). */
import { labelText } from "../format";
import { useAppState } from "../state";

export function Coverage() {
  const coverage = useAppState().audit?.coverage ?? null;
  const running = useAppState().audit?.status.status === "running";

  if (!coverage) {
    return (
      <p className="empty">
        {running ? "Coverage appears after the walk." : "Coverage appears after the walk."}
      </p>
    );
  }

  return (
    <div className="coverage">
      <div className="coverage-summary">
        <div>
          <span className="coverage-number">{coverage.rooms_reviewed}</span>
          <span className="coverage-label">of {coverage.rooms_total} rooms reviewed</span>
        </div>
        <div>
          <span className="coverage-number">{coverage.panos_reviewed}</span>
          <span className="coverage-label">of {coverage.panos_total} panoramas reviewed</span>
        </div>
        <div>
          <span className="coverage-number">{coverage.assets_unique}</span>
          <span className="coverage-label">unique assets</span>
        </div>
        <div>
          <span className="coverage-number">{coverage.observations_total}</span>
          <span className="coverage-label">observations</span>
        </div>
        <div>
          <span className="coverage-number">{coverage.attrs_known}</span>
          <span className="coverage-label">attributes known</span>
        </div>
        <div>
          <span className="coverage-number">{coverage.attrs_unknown}</span>
          <span className="coverage-label">attributes unknown</span>
        </div>
      </div>

      <ul className="room-coverage-list">
        {coverage.rooms.map((room) => (
          <li key={room.room_id} className={`room-coverage status-${room.status}`}>
            <div className="room-coverage-head">
              <strong>{room.room_label}</strong>
              <span className={`badge ${
                room.status === "reviewed"
                  ? "badge-ok"
                  : room.status === "partial"
                    ? "badge-warn"
                    : "badge-muted"
              }`}>
                {room.status.replace("_", " ")}
              </span>
              <span className="muted small">
                {room.panos_reviewed.length} panorama
                {room.panos_reviewed.length === 1 ? "" : "s"}
              </span>
            </div>
            {room.notes.length > 0 ? (
              <ul className="note-list">
                {room.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : null}
          </li>
        ))}
      </ul>

      <div className="not-visible">
        <h3>Not visible in this scan</h3>
        {coverage.not_visible.length === 0 ? (
          <p className="empty">None from the fixed checklist.</p>
        ) : (
          <p>{coverage.not_visible.map((label) => labelText(label)).join(", ")}</p>
        )}
        <p className="muted small">
          {coverage.faces_rejected} face{coverage.faces_rejected === 1 ? "" : "s"} rejected for
          image quality.
        </p>
      </div>
    </div>
  );
}
