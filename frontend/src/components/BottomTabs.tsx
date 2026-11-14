/** Inventory / Coverage / Report / Benchmark tabs (plan 11.2). */
import { useState } from "react";
import { BenchmarkTab } from "./BenchmarkTab";
import { Coverage } from "./Coverage";
import { Inventory } from "./Inventory";
import { ReportTab } from "./ReportTab";

type TabId = "inventory" | "coverage" | "report" | "benchmark";

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "inventory", label: "Inventory" },
  { id: "coverage", label: "Coverage" },
  { id: "report", label: "Report" },
  { id: "benchmark", label: "Benchmark" },
];

export function BottomTabs() {
  const [active, setActive] = useState<TabId>("inventory");

  return (
    <section className="panel tabs-panel">
      <div className="tab-row" role="tablist" aria-label="Audit details">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={active === tab.id}
            aria-controls={`panel-${tab.id}`}
            className={`tab ${active === tab.id ? "active" : ""}`}
            onClick={() => setActive(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        className="tab-panel"
        role="tabpanel"
        id={`panel-${active}`}
        aria-labelledby={`tab-${active}`}
      >
        {active === "inventory" ? <Inventory /> : null}
        {active === "coverage" ? <Coverage /> : null}
        {active === "report" ? <ReportTab /> : null}
        {active === "benchmark" ? <BenchmarkTab /> : null}
      </div>
    </section>
  );
}
