/**
 * 3D tour viewer (plan 11.3 and 13.6).
 *
 * Step 1 (tour only): embeds the Matterport tour of the selected model with the standard public
 * viewer URL. Public and unlisted models play in an iframe without the Showcase SDK (CoStar
 * quickstart, section 3), so no application key is needed for this step.
 *
 * Pins are not drawn in 3D yet: placing them needs the Showcase SDK and the SDK frame calibration
 * (plan 9.7, viewer/coords.ts). Until that is calibrated, pins stay on the 2D floor plan.
 */
import { FIXTURE_SID } from "../fixtures";
import { useAppDispatch, useAppState } from "../state";
import { isSdkFrameCalibrated } from "./coords";

const TOUR_URL = "https://my.matterport.com/show/";

/** Matterport model ids are 11 characters of letters and digits. */
const isModelId = (sid: string): boolean => /^[A-Za-z0-9]{11}$/.test(sid);

export function tourUrl(sid: string): string {
  // play=1 starts the tour without a click; qs=1 starts on the first panorama (quick start)
  const params = new URLSearchParams({ m: sid, play: "1", qs: "1" });
  return `${TOUR_URL}?${params.toString()}`;
}

export function Viewer3D() {
  const { selectedSid } = useAppState();
  const dispatch = useAppDispatch();

  if (selectedSid === FIXTURE_SID || !isModelId(selectedSid)) {
    return (
      <div className="viewer-empty" role="status">
        <div className="viewer-empty-icon" aria-hidden="true">
          3D
        </div>
        <h2>No 3D tour for this apartment</h2>
        <p>
          {selectedSid === FIXTURE_SID
            ? "The fixture apartment is illustrative data, not a real Matterport scan."
            : "This model id is not a Matterport scan."}{" "}
          Pick a real apartment to see its tour.
        </p>
        <button className="button" onClick={() => dispatch({ type: "view", view: "2d" })}>
          Use 2D floor plan
        </button>
      </div>
    );
  }

  return (
    <div className="viewer-tour">
      <iframe
        key={selectedSid}
        className="viewer-tour-frame"
        title={`Matterport 3D tour of ${selectedSid}`}
        src={tourUrl(selectedSid)}
        allow="fullscreen; xr-spatial-tracking"
      />
      {!isSdkFrameCalibrated() && (
        <p className="viewer-tour-note" role="note">
          3D tour only. Asset pins are on the 2D plan until the 3D frame is calibrated.
        </p>
      )}
    </div>
  );
}
