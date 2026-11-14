/**
 * Audit progress maths (Person 2 addition, not in plan 11.3).  Derived only from the events the
 * backend already streams; no new API.  Kept free of React and app state so it can be checked on
 * recorded events.
 *
 * Stage weights are rough shares of wall-clock time with the local model: the walk (one vision
 * call per face plus second looks) dominates.
 */
import type { WattEvent } from "../contracts";

export const WEIGHTS = { building: 5, walk: 70, resolve: 15, finish: 10 } as const;
const FINISH_TOOLS = ["build_inventory_tool", "plan_upgrades", "verify_audit_tool"];

export interface Progress {
  percent: number;
  stage: string;
  detail: string;
  /** Seconds left in the current stage, from that stage's own pace; null while estimating. */
  etaS: number | null;
  /** True when an estimate is expected but not yet possible (nothing timed in this stage). */
  estimating: boolean;
  elapsedS: number;
}

function toolOf(event: WattEvent): string | undefined {
  const tool = event.data.tool;
  return typeof tool === "string" ? tool : undefined;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function computeProgress(events: WattEvent[]): Progress {
  let buildingDone = false;
  let totalViews: number | null = null;
  let viewsDone = 0;
  let walkStartS: number | null = null;
  let lastViewS: number | null = null;
  let lastGapS = 0;
  let resolveTotal = 0;
  let unresolved: number | null = null;
  let resolveStartS: number | null = null;
  let resolvedDone = 0;
  let lastResolvedS: number | null = null;
  const finished = new Set<string>();
  let current = "Starting";
  let elapsedS = 0;
  let done = false;
  let waiting = false;

  for (const event of events) {
    elapsedS = Math.max(elapsedS, event.t_s);
    const tool = toolOf(event);
    if (event.type === "done") done = true;
    // A question pauses the walk until the user answers (or it expires); the next tool event resumes.
    if (event.type === "question") waiting = true;
    else if (event.type === "tool_call" || event.type === "tool_result") waiting = false;
    if (event.type === "tool_call") {
      if (tool === "inspect_next_view" && walkStartS === null) walkStartS = event.t_s;
      if (tool === "resolve_next" && resolveStartS === null) resolveStartS = event.t_s;
      current = tool ?? current;
    }
    if (event.type !== "tool_result") continue;
    if (tool === "load_building") buildingDone = true;
    if (tool === "list_rooms") totalViews = num(event.data.views);
    if (tool === "inspect_next_view") {
      viewsDone += 1;
      lastGapS = event.t_s - (lastViewS ?? walkStartS ?? event.t_s);
      lastViewS = event.t_s;
      const pending = num(event.data.pending);
      if (pending !== null) totalViews = Math.max(totalViews ?? 0, viewsDone + pending);
    }
    if (tool === "resolve_next") {
      // One observation can take several resolve steps; "final" marks the step that settles it.
      if (event.data.final === true) {
        resolvedDone += 1;
        lastResolvedS = event.t_s;
      }
      const left = num(event.data.unresolved);
      if (left !== null) {
        unresolved = left;
        resolveTotal = Math.max(resolveTotal, resolvedDone + left);
      }
    }
    if (tool && FINISH_TOOLS.includes(tool)) finished.add(tool);
  }

  const walkFrac = totalViews ? Math.min(1, viewsDone / totalViews) : 0;
  const resolveFrac =
    finished.size > 0 ? 1 : resolveTotal > 0 ? resolvedDone / resolveTotal : 0;
  const finishFrac = finished.size / FINISH_TOOLS.length;
  let percent = done
    ? 100
    : (buildingDone ? WEIGHTS.building : 0) +
      WEIGHTS.walk * walkFrac +
      WEIGHTS.resolve * resolveFrac +
      WEIGHTS.finish * finishFrac;
  percent = Math.round(Math.min(100, percent));

  let stage = "Starting";
  let detail = "";
  if (done) {
    stage = "Done";
  } else if (waiting) {
    stage = "Waiting for your answer";
    detail = "the agent asked a question";
  } else if (finished.size > 0 || current === "build_inventory_tool" || current === "plan_upgrades" || current === "verify_audit_tool") {
    stage = "Building inventory and upgrade plan";
    detail = `${finished.size} of ${FINISH_TOOLS.length} steps`;
  } else if (resolveTotal > 0 || current === "resolve_next") {
    stage = "Double-checking unclear items";
    detail = resolveTotal > 0 ? `${resolvedDone} of ${resolveTotal} items` : "first item";
  } else if (totalViews !== null) {
    stage = "Walking the rooms";
    detail = `${viewsDone} of ${totalViews} views`;
  } else if (buildingDone || current === "load_building") {
    stage = "Loading building info";
  }

  // Each stage is timed on its own pace: a walk served from the cache finishes in seconds, while
  // double-checking makes fresh (slow) model calls, so one pace cannot predict the other.
  let etaS: number | null = null;
  let estimating = false;
  if (!done && !waiting && stage === "Walking the rooms" && totalViews) {
    const perView =
      viewsDone > 0 && walkStartS !== null && lastViewS !== null
        ? Math.max((lastViewS - walkStartS) / viewsDone, lastGapS)
        : null;
    // Under 3 s a view was a cache hit: it says nothing about the views still to come.
    if (perView !== null && perView >= 3) etaS = Math.round(perView * (totalViews - viewsDone));
    else estimating = true;
  } else if (!done && !waiting && stage === "Double-checking unclear items") {
    if (resolvedDone > 0 && resolveStartS !== null && lastResolvedS !== null && unresolved !== null) {
      etaS = Math.round(((lastResolvedS - resolveStartS) / resolvedDone) * unresolved);
    } else {
      estimating = true;
    }
  }

  return { percent, stage, detail, etaS, estimating, elapsedS: Math.round(elapsedS) };
}
