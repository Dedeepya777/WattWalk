/**
 * Bird's-eye views (Vexcel oblique aerial photos) of an apartment's building: a small thumbnail for
 * the apartment list, and a larger viewer with the four sides.
 */
import { useEffect, useState } from "react";
import { birdseyeUrl } from "../api";

type Direction = "north" | "east" | "south" | "west";
const SIDES: { dir: Direction; label: string }[] = [
  { dir: "north", label: "North" },
  { dir: "east", label: "East" },
  { dir: "south", label: "South" },
  { dir: "west", label: "West" },
];

/** Thumbnail next to an apartment's name; a plain tile when there is no aerial photo. */
export function BirdsEyeThumb({ sid, label, onOpen }: { sid: string; label: string; onOpen: () => void }) {
  const url = birdseyeUrl(sid, "north");
  const [state, setState] = useState<"loading" | "ok" | "missing">(url ? "loading" : "missing");
  useEffect(() => setState(url ? "loading" : "missing"), [url]);
  return (
    <button
      type="button"
      className={`birdseye-thumb ${state}`}
      onClick={onOpen}
      disabled={state === "missing"}
      aria-label={`Bird’s-eye view of ${label}`}
      title={state === "missing" ? "No aerial photo (needs VEXCEL_API_KEY in .env)" : "Bird’s-eye view"}
    >
      {url ? (
        <img
          src={url}
          alt=""
          loading="lazy"
          onLoad={() => setState("ok")}
          onError={() => setState("missing")}
        />
      ) : null}
    </button>
  );
}

/** Larger bird's-eye view of the building, looking from each side. */
export function BirdsEyeViewer({ sid, label, onClose }: { sid: string; label: string; onClose: () => void }) {
  const [dir, setDir] = useState<Direction>("north");
  const [loading, setLoading] = useState(true);
  const url = birdseyeUrl(sid, dir);

  useEffect(() => setLoading(true), [url]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="birdseye-viewer"
        role="dialog"
        aria-modal="true"
        aria-label={`Bird’s-eye view of ${label}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="birdseye-viewer-head">
          <strong>{label}</strong>
          <div className="birdseye-sides" role="group" aria-label="Look from">
            {SIDES.map((side) => (
              <button
                key={side.dir}
                type="button"
                className={dir === side.dir ? "active" : ""}
                aria-pressed={dir === side.dir}
                onClick={() => setDir(side.dir)}
              >
                {side.label}
              </button>
            ))}
          </div>
          <button type="button" className="button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className={`birdseye-viewer-frame${loading ? " loading" : ""}`}>
          <img key={url} src={url} alt={`Aerial view of ${label}, looking ${dir}`} onLoad={() => setLoading(false)} />
        </div>
      </div>
    </div>
  );
}
