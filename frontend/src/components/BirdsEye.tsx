/** Bird's-eye view of the selected apartment's building (Vexcel oblique aerial), from four sides. */
import { useEffect, useState } from "react";
import { birdseyeUrl } from "../api";
import { useAppState } from "../state";

type Direction = "north" | "east" | "south" | "west";
const SIDES: { dir: Direction; label: string; title: string }[] = [
  { dir: "north", label: "N", title: "Looking north" },
  { dir: "east", label: "E", title: "Looking east" },
  { dir: "south", label: "S", title: "Looking south" },
  { dir: "west", label: "W", title: "Looking west" },
];

export function BirdsEye() {
  const { selectedSid } = useAppState();
  const [dir, setDir] = useState<Direction>("north");
  const [status, setStatus] = useState<"loading" | "ok" | "missing">("loading");
  const [big, setBig] = useState(false);
  const url = birdseyeUrl(selectedSid, dir);

  useEffect(() => setStatus(url ? "loading" : "missing"), [url]);

  if (!url) return null;
  return (
    <section className="panel birdseye" aria-labelledby="birdseye-heading">
      <div className="panel-heading">
        <h2 id="birdseye-heading">Bird’s-eye</h2>
        <div className="birdseye-sides" role="group" aria-label="Look from">
          {SIDES.map((side) => (
            <button
              key={side.dir}
              type="button"
              className={dir === side.dir ? "active" : ""}
              aria-pressed={dir === side.dir}
              title={side.title}
              onClick={() => setDir(side.dir)}
            >
              {side.label}
            </button>
          ))}
        </div>
      </div>
      {status === "missing" ? (
        <p className="birdseye-note">No aerial view for this building (needs VEXCEL_API_KEY in .env).</p>
      ) : null}
      <button
        type="button"
        className={`birdseye-frame${status === "loading" ? " loading" : ""}${status === "missing" ? " hidden" : ""}`}
        onClick={() => setBig(true)}
        aria-label="Open the bird’s-eye view larger"
      >
        <img
          key={url}
          src={url}
          alt={`Aerial view of the building, looking ${dir}`}
          onLoad={() => setStatus("ok")}
          onError={() => setStatus("missing")}
        />
      </button>
      {big ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setBig(false)}>
          <img className="birdseye-big" src={url} alt={`Aerial view of the building, looking ${dir}`} />
        </div>
      ) : null}
    </section>
  );
}
