/**
 * Intro page (hero): what WattWalk does in one line, and one button into the demo apartment's heat map.
 * Shown over the app each time the site opens; the app loads underneath so the demo opens at once.
 * The room on the right is a drawing (no scan imagery is bundled).
 */
import { useEffect } from "react";
import { Logo } from "./Logo";

interface Props {
  /** Open the demo apartment on the heat map. */
  onExplore: () => void;
  /** Go to the app without choosing an apartment. */
  onSkip: () => void;
}

/** A simple room with heat glows, echoing the 3D heat map. */
function RoomIllustration() {
  return (
    <svg className="intro-room" viewBox="0 0 480 360" role="img" aria-label="A room with glowing heat sources">
      <defs>
        {[
          ["hot", "#e2553d"],
          ["warm", "#f2b33d"],
          ["cool", "#5b8fd6"],
        ].map(([id, color]) => (
          <radialGradient key={id} id={`intro-${id}`}>
            <stop offset="0%" stopColor={color} stopOpacity="0.85" />
            <stop offset="35%" stopColor={color} stopOpacity="0.45" />
            <stop offset="70%" stopColor={color} stopOpacity="0" />
          </radialGradient>
        ))}
      </defs>
      {/* back wall, floor and side wall */}
      <polygon points="70,40 410,40 410,250 70,250" fill="#f3f2ed" />
      <polygon points="70,250 410,250 470,340 10,340" fill="#e7e5de" />
      <polygon points="10,0 70,40 70,250 10,340" fill="#ebe9e2" />
      <polygon points="470,0 410,40 410,250 470,340" fill="#ebe9e2" />
      {/* window */}
      <rect x="250" y="70" width="120" height="120" rx="4" fill="#dfe8ef" stroke="#c9c7bf" strokeWidth="4" />
      <line x1="310" y1="70" x2="310" y2="190" stroke="#c9c7bf" strokeWidth="4" />
      <line x1="250" y1="130" x2="370" y2="130" stroke="#c9c7bf" strokeWidth="4" />
      {/* ceiling light */}
      <line x1="160" y1="40" x2="160" y2="78" stroke="#9a9a92" strokeWidth="2" />
      <path d="M140 78 h40 l-8 14 h-24 z" fill="#d9d8d0" />
      {/* fridge */}
      <rect x="100" y="150" width="56" height="100" rx="5" fill="#ffffff" stroke="#d9d8d0" strokeWidth="2" />
      <line x1="100" y1="190" x2="156" y2="190" stroke="#d9d8d0" strokeWidth="2" />
      <line x1="146" y1="162" x2="146" y2="180" stroke="#9a9a92" strokeWidth="3" strokeLinecap="round" />
      {/* sofa */}
      <rect x="196" y="214" width="120" height="36" rx="10" fill="#cfd9bd" />
      <rect x="196" y="200" width="120" height="22" rx="8" fill="#b9c8a0" />
      {/* glows */}
      <circle className="intro-glow" cx="310" cy="130" r="110" fill="url(#intro-hot)" />
      <circle className="intro-glow intro-glow-2" cx="160" cy="88" r="60" fill="url(#intro-warm)" />
      <circle className="intro-glow intro-glow-3" cx="128" cy="200" r="70" fill="url(#intro-cool)" />
      {/* labels */}
      <g className="intro-tag" transform="translate(310 214)">
        <rect x="-50" y="-11" width="100" height="22" rx="11" fill="rgba(40,45,40,0.72)" />
        <text textAnchor="middle" y="4" fill="#ffffff" fontSize="11" fontWeight="600">1,187 kWh/yr</text>
      </g>
      <g className="intro-tag" transform="translate(160 120)">
        <rect x="-34" y="-10" width="68" height="20" rx="10" fill="rgba(40,45,40,0.72)" />
        <text textAnchor="middle" y="4" fill="#ffffff" fontSize="11" fontWeight="600">190 W</text>
      </g>
    </svg>
  );
}

export function Intro({ onExplore, onSkip }: Props) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onSkip();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onSkip]);

  return (
    <div className="intro" role="dialog" aria-modal="true" aria-labelledby="intro-title">
      <header className="intro-top">
        <span className="intro-brand">
          <Logo className="intro-logo" />
          WattWalk
        </span>
        <button type="button" className="intro-skip" onClick={onSkip}>
          Open the app
        </button>
      </header>

      <main className="intro-hero">
        <div className="intro-copy">
          <p className="intro-eyebrow">Energy audits from a 3D tour</p>
          <h1 id="intro-title">
            See where an apartment loses energy.
            <span>And what to fix first.</span>
          </h1>
          <div className="intro-actions">
            <button type="button" className="intro-cta" onClick={onExplore}>
              Explore a demo apartment
            </button>
            <button type="button" className="intro-link" onClick={onSkip}>
              Open the app <span aria-hidden="true">›</span>
            </button>
          </div>
        </div>
        <div className="intro-visual">
          <RoomIllustration />
        </div>
        <ol className="intro-steps">
          <li>
            <strong>Scan</strong>
            <span>Uses the Matterport tour the listing already has. No site visit.</span>
          </li>
          <li>
            <strong>See</strong>
            <span>Every light, window and appliance glows by the heat it adds.</span>
          </li>
          <li>
            <strong>Fix</strong>
            <span>Pick upgrades and get one plan with cost, savings and payback.</span>
          </li>
        </ol>
      </main>
    </div>
  );
}
