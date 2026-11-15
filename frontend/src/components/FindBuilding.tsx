/**
 * "Find your building": a landlord types a street address (Los Angeles), sees the buildings that match
 * with their scanned units, ticks the units they own and adds the building. Its units then appear in the
 * Apartments list, ready to audit.
 */
import { useEffect, useRef, useState } from "react";
import { addBuilding, searchBuildings } from "../api";
import type { BuildingMatch } from "../contracts";

interface Props {
  onClose: () => void;
  /** Called after a building was added, with its first unit (to select it). */
  onAdded: (firstSid: string) => void;
}

const EXAMPLES = ["819 Santee St", "1830 N Cherokee Ave", "334 S Main St"];

export function FindBuilding({ onClose, onAdded }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<BuildingMatch[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => inputRef.current?.focus(), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Search as the landlord types (a short pause first).
  useEffect(() => {
    const q = query.trim();
    if (q.length < 3) {
      setResults(null);
      setError(null);
      return undefined;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearching(true);
      setError(null);
      try {
        const response = await searchBuildings(q, controller.signal);
        setResults(response.buildings);
        if (response.buildings.length === 1) choose(response.buildings[0]);
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query]);

  const choose = (building: BuildingMatch) => {
    setOpen(building.building_id);
    setChosen(new Set(building.tours.map((tour) => tour.sid)));
  };

  const toggle = (sid: string) =>
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(sid)) next.delete(sid);
      else next.add(sid);
      return next;
    });

  const add = async (building: BuildingMatch) => {
    const sids = building.tours.map((tour) => tour.sid).filter((sid) => chosen.has(sid));
    if (sids.length === 0) return;
    setAdding(true);
    setError(null);
    try {
      await addBuilding({ building_id: building.building_id, sids });
      onAdded(sids[0]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="modal-backdrop find-backdrop" role="presentation" onClick={onClose}>
      <div
        className="find-building"
        role="dialog"
        aria-modal="true"
        aria-labelledby="find-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="find-head">
          <h2 id="find-title">Find your building</h2>
          <button type="button" className="button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <label className="find-field">
          <span className="sr-only">Street address</span>
          <input
            ref={inputRef}
            type="search"
            value={query}
            placeholder="Street address, e.g. 819 Santee St"
            onChange={(event) => setQuery(event.target.value)}
            autoComplete="off"
          />
          {searching ? <span className="spinner" aria-hidden="true" /> : null}
        </label>
        <p className="find-hint">Los Angeles buildings with 3D tours.</p>

        {error ? <p className="inline-error" role="alert">{error}</p> : null}

        {results === null ? (
          <div className="find-examples">
            Try{" "}
            {EXAMPLES.map((example, index) => (
              <span key={example}>
                <button type="button" className="find-example" onClick={() => setQuery(example)}>
                  {example}
                </button>
                {index < EXAMPLES.length - 1 ? ", " : ""}
              </span>
            ))}
          </div>
        ) : results.length === 0 && !searching ? (
          <p className="find-empty">
            No 3D tours found for this address. Check the street number, or try another building.
          </p>
        ) : (
          <ul className="find-results">
            {results.map((building) => {
              const isOpen = open === building.building_id;
              const picked = building.tours.filter((tour) => chosen.has(tour.sid)).length;
              return (
                <li key={building.building_id} className={isOpen ? "find-building-row open" : "find-building-row"}>
                  <button type="button" className="find-building-head" onClick={() => choose(building)} aria-expanded={isOpen}>
                    <span className="find-address">{building.address.replace(", Los Angeles, CA", "")}</span>
                    <span className="find-meta">
                      Los Angeles{building.postal_code ? ` ${building.postal_code}` : ""} · {building.tours.length} unit
                      {building.tours.length === 1 ? "" : "s"} scanned
                    </span>
                  </button>
                  {isOpen ? (
                    <div className="find-units">
                      <p className="find-units-title">Which units are yours?</p>
                      <ul>
                        {building.tours.map((tour) => (
                          <li key={tour.sid}>
                            <label>
                              <input type="checkbox" checked={chosen.has(tour.sid)} onChange={() => toggle(tour.sid)} />
                              <span className="find-unit-name">{tour.name}</span>
                              <span className="find-unit-meta">
                                {tour.room_count} rooms · {tour.pano_count} views
                              </span>
                            </label>
                          </li>
                        ))}
                      </ul>
                      <button
                        type="button"
                        className="button primary find-add"
                        disabled={picked === 0 || adding}
                        onClick={() => void add(building)}
                      >
                        {adding ? <span className="spinner" aria-hidden="true" /> : null}
                        Add building ({picked} unit{picked === 1 ? "" : "s"})
                      </button>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
