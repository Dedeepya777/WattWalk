/**
 * Intro page (hero): what WattWalk does in one line, and one button into the demo apartment's heat map.
 * Shown over the app each time the site opens; the app loads underneath so the demo opens at once.
 * The room on the right is a drawing (no scan imagery is bundled).
 */
import { useEffect, useState } from "react";
import { Logo } from "./Logo";

interface Props {
  /** Open the demo apartment on the heat map. */
  onExplore: () => void;
  /** Go to the app without choosing an apartment. */
  onSkip: () => void;
}

/** An apartment building in 3D (isometric), its windows glowing by heat, with a scan sweeping down it. */
type Pt = [number, number];
const A: Pt = [110, 120]; // left top corner of the front-left face
const B: Pt = [260, 200]; // nearest top corner
const E: Pt = [410, 120]; // right top corner
const DROP = 250; // height of the walls
const down = ([x, y]: Pt): Pt => [x, y + DROP];
const lerp = (p: Pt, q: Pt, t: number): Pt => [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
const HEAT = ["#5b8fd6", "#8fb4e0", "#e9c03f", "#f29b38", "#e0573f"];

/** A window on a wall from `top0` to `top1` (top edge), at columns u0-u1 and floors v0-v1 (0 = top). */
function pane(top0: Pt, top1: Pt, u0: number, u1: number, v0: number, v1: number): string {
  const at = (u: number, v: number) => {
    const t = lerp(top0, top1, u);
    return [t[0], t[1] + v * DROP] as Pt;
  };
  return [at(u0, v0), at(u1, v0), at(u1, v1), at(u0, v1)].map((p) => p.join(",")).join(" ");
}

/** Deterministic "heat" per window so the drawing is the same every time. */
const heatOf = (i: number) => [4, 1, 2, 0, 3, 4, 2, 1, 0, 3, 2, 4, 1, 0, 3, 2][i % 16];

function BuildingIllustration() {
  const floors = 6;
  const cols = 4;
  const windows: { points: string; heat: number; delay: number }[] = [];
  let n = 0;
  for (const [top0, top1] of [[A, B], [B, E]] as [Pt, Pt][]) {
    for (let f = 0; f < floors; f += 1) {
      for (let c = 0; c < cols; c += 1) {
        const u0 = 0.1 + c * 0.215;
        const v0 = 0.08 + f * 0.148;
        windows.push({ points: pane(top0, top1, u0, u0 + 0.13, v0, v0 + 0.085), heat: heatOf(n), delay: (n % 7) * 0.45 });
        n += 1;
      }
    }
  }
  const roofTop: Pt = [260, 40];
  const silhouette = [A, roofTop, E, down(E), down(B), down(A)].map((p) => p.join(",")).join(" ");
  return (
    <svg className="intro-building" viewBox="0 0 520 470" role="img" aria-label="An apartment building, its windows glowing by how much heat they let in">
      <defs>
        <filter id="ib-blur" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
        <linearGradient id="ib-scan" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#a3b77f" stopOpacity="0" />
          <stop offset="70%" stopColor="#a3b77f" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#4b6237" stopOpacity="0.9" />
        </linearGradient>
        <clipPath id="ib-clip">
          <polygon points={silhouette} />
        </clipPath>
      </defs>
      <ellipse cx="260" cy="455" rx="190" ry="14" fill="rgba(40,45,40,0.08)" />
      {/* walls and roof */}
      <polygon points={[A, B, down(B), down(A)].map((p) => p.join(",")).join(" ")} fill="#ecebe5" />
      <polygon points={[B, E, down(E), down(B)].map((p) => p.join(",")).join(" ")} fill="#dcdad2" />
      <polygon points={[A, roofTop, E, B].map((p) => p.join(",")).join(" ")} fill="#f6f5f1" />
      <polygon points={[A, roofTop, E, B].map((p) => p.join(",")).join(" ")} fill="none" stroke="#d3d1c8" />
      {/* window glows (blurred), then the panes */}
      <g filter="url(#ib-blur)">
        {windows.map((w, i) =>
          w.heat >= 2 ? (
            <polygon key={`g${i}`} className="ib-glow" points={w.points} fill={HEAT[w.heat]} style={{ animationDelay: `${w.delay}s` }} />
          ) : null,
        )}
      </g>
      {windows.map((w, i) => (
        <polygon key={i} points={w.points} fill={HEAT[w.heat]} opacity={w.heat >= 2 ? 0.95 : 0.55} />
      ))}
      {/* the scan sweeping down the building */}
      <g clipPath="url(#ib-clip)">
        <rect className="ib-scan" x="90" y="-70" width="340" height="70" fill="url(#ib-scan)" />
      </g>
    </svg>
  );
}

export function Intro({ onExplore, onSkip }: Props) {
  // The button grows to fill the screen, fading to the app's background, then the app is there.
  const [grow, setGrow] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onSkip();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onSkip]);

  const start = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      onExplore();
      return;
    }
    const b = event.currentTarget.getBoundingClientRect();
    setGrow({ x: b.left, y: b.top, w: b.width, h: b.height });
  };

  return (
    <div className={`intro${grow ? " intro-leaving" : ""}`} role="dialog" aria-modal="true" aria-labelledby="intro-title">
      <header className="intro-top">
        <span className="intro-brand">
          <Logo className="intro-logo" />
          WattWalk
        </span>
      </header>

      <main className="intro-hero">
        <div className="intro-copy">
          <h1 id="intro-title">
            Better buildings. Lower bills. Cleaner planet.
            <span>Energy intelligence for landlords and renters alike.</span>
          </h1>
          <div className="intro-actions">
            <button type="button" className="intro-cta" onClick={start} disabled={grow !== null}>
              Get started
            </button>
          </div>
        </div>
        <div className="intro-visual">
          <BuildingIllustration />
        </div>
      </main>

      {grow ? (
        <div
          className="intro-grow"
          style={{
            // the button's exact box, as insets from the screen edges, and its pill radius
            ["--it" as string]: `${grow.y}px`,
            ["--il" as string]: `${grow.x}px`,
            ["--ir" as string]: `${window.innerWidth - grow.x - grow.w}px`,
            ["--ib" as string]: `${window.innerHeight - grow.y - grow.h}px`,
            ["--rr" as string]: `${grow.h / 2}px`,
          } as React.CSSProperties}
          onAnimationEnd={onExplore}
          aria-hidden="true"
        />
      ) : null}
    </div>
  );
}
