/**
 * 3D tour viewer (plan 11.3 and 13.6).  The Showcase SDK requires an
 * application key (U1).  Without a key, or until the SDK frame is calibrated,
 * this component explains why it is unavailable and sends the user to 2D.
 */
import { useEffect } from "react";
import { useAppDispatch } from "../state";
import { isSdkFrameCalibrated, sdkFrameResidual } from "./coords";

export function Viewer3D() {
  const dispatch = useAppDispatch();
  const calibrated = isSdkFrameCalibrated();

  useEffect(() => {
    if (!calibrated) dispatch({ type: "view", view: "2d" });
  }, [calibrated, dispatch]);

  return (
    <div className="viewer-empty" role="status">
      <div className="viewer-empty-icon" aria-hidden="true">
        3D
      </div>
      <h2>3D viewer unavailable</h2>
      <p>
        {calibrated
          ? "The Showcase SDK frame is calibrated, but no SDK application key is configured for this build."
          : `The Showcase SDK frame is not calibrated${
              sdkFrameResidual === null ? "" : ` (residual ${sdkFrameResidual} m)`
            }. Pins would land in the wrong place.`}
      </p>
      <p className="muted">
        The 2D floor plan is the fallback in plan 11.5: room polygons, panorama
        positions and one pin per asset.
      </p>
      <button className="button" onClick={() => dispatch({ type: "view", view: "2d" })}>
        Use 2D floor plan
      </button>
    </div>
  );
}
