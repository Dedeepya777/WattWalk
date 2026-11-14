/** Agent log with the planner todo checklist (plan 11.3, 4.4). */
import { useEffect, useMemo, useRef, useState } from "react";
import type { AgentName } from "../contracts";
import { formatClock } from "../format";
import { useAppState } from "../state";

const AGENTS: AgentName[] = [
  "planner",
  "walker",
  "exterior_analyst",
  "retrofit_planner",
  "verifier",
  "system",
  "benchmark",
];

export function AgentLog() {
  const state = useAppState();
  const [agent, setAgent] = useState<AgentName | "all">("all");
  const listRef = useRef<HTMLDivElement | null>(null);
  const running = state.audit?.status.status === "running";

  const todo = useMemo(() => {
    for (let index = state.events.length - 1; index >= 0; index -= 1) {
      const event = state.events[index];
      if (event.type === "todo" && Array.isArray(event.data.todo)) {
        return event.data.todo.filter((item): item is string => typeof item === "string");
      }
    }
    return [];
  }, [state.events]);

  const completedSteps = useMemo(() => {
    const completed = new Set<string>();
    for (const event of state.events) {
      if (event.type !== "tool_result") continue;
      const tool = typeof event.data.tool === "string" ? event.data.tool : "";
      if (tool === "load_building") completed.add("building context");
      if (tool === "list_rooms" || tool === "inspect_next_view") completed.add("walk rooms");
      if (tool === "build_inventory_tool") completed.add("walk rooms");
      if (tool === "plan_upgrades") completed.add("plan upgrades");
      if (tool === "verify_audit_tool") completed.add("verify");
    }
    if (state.audit?.report_md) completed.add("write report");
    return completed;
  }, [state.events, state.audit?.report_md]);

  const visible = state.events.filter((event) => agent === "all" || event.agent === agent);

  useEffect(() => {
    const node = listRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [visible.length]);

  return (
    <section className="panel log-panel" aria-labelledby="log-heading">
      <div className="panel-heading">
        <h2 id="log-heading">Agent log</h2>
        <label className="inline-field">
          <span className="sr-only">Filter by agent</span>
          <select value={agent} onChange={(event) => setAgent(event.target.value as AgentName | "all")}>
            <option value="all">All agents</option>
            {AGENTS.map((name) => (
              <option key={name} value={name}>
                {name.replace("_", " ")}
              </option>
            ))}
          </select>
        </label>
      </div>

      {todo.length > 0 ? (
        <div className="todo-list" aria-label="Planner todo list">
          {todo.map((item) => {
            const done = completedSteps.has(item.toLowerCase());
            return (
              <span key={item} className={`todo-item ${done ? "done" : ""}`}>
                <span aria-hidden="true">{done ? "✓" : "○"}</span> {item}
              </span>
            );
          })}
        </div>
      ) : null}

      <div className="log-list" ref={listRef} role="log" aria-live="polite">
        {state.events.length === 0 ? (
          <p className="empty">
            {running ? "Waiting for events…" : "Start an audit to see the agent work."}
          </p>
        ) : visible.length === 0 ? (
          <p className="empty">No events from {agent.replace("_", " ")} yet.</p>
        ) : (
          visible.map((event) => (
            <div
              key={`${event.seq}-${event.type}`}
              className={`log-line ${event.type === "error" ? "log-error" : ""} ${
                event.type === "finding" ? "log-finding" : ""
              }`}
            >
              <span className="log-time">{formatClock(event.t_s)}</span>
              <span className={`agent-chip agent-${event.agent}`}>
                {event.agent.replace("_", " ")}
              </span>
              <span className="log-type">{event.type.replace("_", " ")}</span>
              <span className="log-summary">{event.summary}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
