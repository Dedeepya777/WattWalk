/** Inventory tab (plan 11.3). */
import type { Asset } from "../contracts";
import { labelText, unknownAttrCount } from "../format";
import { useAppDispatch, useAppState } from "../state";

export function Inventory() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const audit = state.audit;
  const assets: Asset[] = audit?.inventory ?? [];
  const rooms = new Map((audit?.rooms ?? []).map((room) => [room.id, room.label] as const));
  const running = audit?.status.status === "running";

  if (assets.length === 0) {
    return (
      <p className="empty">
        {running ? "The walker is still building the inventory…" : "No assets yet."}
      </p>
    );
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Asset</th>
            <th scope="col">Room</th>
            <th scope="col">Evidence</th>
            <th scope="col">Unknown</th>
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => {
            const changed = state.changedAssetIds.includes(asset.id);
            return (
              <tr
                key={asset.id}
                className={changed ? "row-changed" : ""}
                onClick={() => dispatch({ type: "selectAsset", assetId: asset.id })}
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    dispatch({ type: "selectAsset", assetId: asset.id });
                  }
                }}
                aria-label={`${labelText(asset.label)} in ${
                  asset.room_id ? rooms.get(asset.room_id) ?? "unknown room" : "unknown room"
                }`}
              >
                <td>
                  <strong>{labelText(asset.label)}</strong>
                  <span className="muted small"> {asset.id}</span>
                </td>
                <td>{asset.room_id ? rooms.get(asset.room_id) ?? asset.room_id : "—"}</td>
                <td>seen {asset.observation_ids.length} times</td>
                <td>
                  {unknownAttrCount(asset.attrs) === 0 ? (
                    <span className="badge badge-ok">all known</span>
                  ) : (
                    <span className="badge badge-warn">
                      {unknownAttrCount(asset.attrs)} unknown
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
