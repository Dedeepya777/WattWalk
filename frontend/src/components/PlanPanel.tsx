/** Plan panel with budget, role, objectives, exclusions, notes and Explain (plan 11.3). */
import { useEffect, useState } from "react";
import { ApiFailure, consumeFixtureNotice, postExplain } from "../api";
import type { PlanRequest, UpgradeLine } from "../contracts";
import {
  evidenceNote,
  formatCostRange,
  formatCostShort,
  formatCurrency,
  formatKwh,
  formatNumber,
  formatPayback,
  paybackText,
  reasonText,
  whoPaysSentence,
} from "../format";
import { useAppDispatch, useAppState } from "../state";
import { ExplainBox } from "./ExplainBox";

interface ExplainState {
  loading: boolean;
  text: string | null;
  generatedBy: "template" | "llm" | null;
  error: string | null;
}

const EMPTY_EXPLAIN: ExplainState = {
  loading: false,
  text: null,
  generatedBy: null,
  error: null,
};

function clamp(value: number, low: number, high: number): number {
  if (!Number.isFinite(value)) return low;
  return Math.min(high, Math.max(low, value));
}

export function PlanPanel() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const plan = state.plan;
  const request = state.planRequest;
  const hasInventory = (state.audit?.inventory.length ?? 0) > 0;
  const disabled = !hasInventory;
  const [explainFor, setExplainFor] = useState<string | null>(null);
  const [explain, setExplain] = useState<ExplainState>(EMPTY_EXPLAIN);
  const requestKey = JSON.stringify(request);

  useEffect(() => {
    // An explanation belongs to the request that produced it; never show stale wording.
    setExplainFor(null);
  }, [requestKey]);

  const setRequest = (patch: Partial<PlanRequest>) => {
    dispatch({ type: "planRequest", request: { ...request, ...patch } });
  };

  const assumptionValue = (key: string): number | null => {
    const found = plan?.assumptions_used.find((item) => item.key === key);
    return found ? found.value : null;
  };

  const setOverride = (key: string, raw: string) => {
    const overrides = { ...request.overrides };
    if (raw.trim() === "" || Number.isNaN(Number(raw))) {
      delete overrides[key];
    } else {
      overrides[key] = Number(raw);
    }
    setRequest({ overrides });
  };

  const showExplain = async (line: UpgradeLine) => {
    if (explainFor === line.upgrade_id) {
      setExplainFor(null);
      return;
    }
    setExplainFor(line.upgrade_id);
    setExplain({ loading: true, text: null, generatedBy: null, error: null });
    try {
      const response = await postExplain(state.selectedSid, {
        upgrade_id: line.upgrade_id,
        plan_request: request,
      });
      setExplain({
        loading: false,
        text: response.text,
        generatedBy: response.generated_by,
        error: null,
      });
      const notice = consumeFixtureNotice();
      if (notice) dispatch({ type: "fixtureNotice", notice });
    } catch (error) {
      setExplain({
        loading: false,
        text: null,
        generatedBy: null,
        error:
          error instanceof ApiFailure
            ? error.message
            : "The explanation request failed; the formula above is still valid.",
      });
    }
  };

  const monthlyHours = request.overrides.lighting_hours_per_day ?? assumptionValue("lighting_hours_per_day");
  const rate = request.overrides.electricity_rate_usd_per_kwh ?? assumptionValue("electricity_rate_usd_per_kwh");

  return (
    <section className="panel plan-panel" aria-labelledby="plan-heading">
      <div className="panel-heading">
        <h2 id="plan-heading">Upgrade plan</h2>
        {state.planLoading ? (
          <span className="muted small">
            <span className="spinner" aria-hidden="true" /> recalculating
          </span>
        ) : null}
      </div>

      <div className="plan-inputs">
        <label className="field">
          <span>
            Budget <strong>{formatCurrency(request.budget_usd)}</strong>
          </span>
          <input
            type="range"
            min={0}
            max={15000}
            step={250}
            value={clamp(request.budget_usd, 0, 15000)}
            disabled={disabled}
            onChange={(event) =>
              setRequest({ budget_usd: clamp(Number(event.target.value), 0, 50000) })
            }
            aria-label="Budget slider"
          />
          <input
            type="number"
            min={0}
            max={50000}
            step={100}
            value={request.budget_usd}
            disabled={disabled}
            onChange={(event) =>
              setRequest({ budget_usd: clamp(Number(event.target.value), 0, 50000) })
            }
            aria-label="Budget in dollars"
          />
        </label>

        <label className="field">
          <span>Objective</span>
          <select
            value={request.objective}
            disabled={disabled}
            onChange={(event) =>
              setRequest({ objective: event.target.value as PlanRequest["objective"] })
            }
          >
            <option value="max_bill">Maximize bill savings</option>
            <option value="max_kwh">Maximize energy saved</option>
            <option value="best_value">Best value (payback)</option>
            <option value="conservative">Conservative (upper costs)</option>
          </select>
        </label>

        <div className="field">
          <span>Who are you?</span>
          <div className="segmented" role="group" aria-label="Owner or tenant">
            <button
              type="button"
              className={request.role === "owner" ? "segmented-button active" : "segmented-button"}
              aria-pressed={request.role === "owner"}
              disabled={disabled}
              onClick={() => setRequest({ role: "owner" })}
            >
              Owner
            </button>
            <button
              type="button"
              className={request.role === "tenant" ? "segmented-button active" : "segmented-button"}
              aria-pressed={request.role === "tenant"}
              disabled={disabled}
              onClick={() => setRequest({ role: "tenant" })}
            >
              Tenant
            </button>
          </div>
        </div>

        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={request.tenant_pays_electric}
            disabled={disabled}
            onChange={(event) => setRequest({ tenant_pays_electric: event.target.checked })}
          />
          <span>Tenant pays the electric bill</span>
        </label>

        <label className="field">
          <span>Stay (months)</span>
          <input
            type="number"
            min={1}
            max={120}
            value={request.stay_months}
            disabled={disabled}
            onChange={(event) =>
              setRequest({ stay_months: clamp(Number(event.target.value), 1, 120) })
            }
          />
        </label>

        <details className="override-block">
          <summary>Assumption overrides</summary>
          <label className="field">
            <span>Lighting hours per day</span>
            <input
              type="number"
              min={0}
              max={24}
              step={0.5}
              value={monthlyHours ?? ""}
              placeholder="from API assumptions"
              disabled={disabled}
              onChange={(event) => setOverride("lighting_hours_per_day", event.target.value)}
            />
          </label>
          <label className="field">
            <span>Electricity rate (USD/kWh)</span>
            <input
              type="number"
              min={0}
              max={5}
              step={0.01}
              value={rate ?? ""}
              placeholder="from API assumptions"
              disabled={disabled}
              onChange={(event) => setOverride("electricity_rate_usd_per_kwh", event.target.value)}
            />
          </label>
          {Object.keys(request.overrides).length > 0 ? (
            <button
              className="button small"
              onClick={() => setRequest({ overrides: {} })}
              disabled={disabled}
            >
              Reset overrides
            </button>
          ) : null}
        </details>
      </div>

      {state.fixtureNotice ? (
        <p className="notice" role="status">
          {state.fixtureNotice}
        </p>
      ) : null}

      {state.planError ? (
        <p className="inline-error" role="alert">
          {state.planError.status === 404
            ? "No inventory yet. The plan appears when the walk finishes."
            : `${state.planError.field ? `${state.planError.field}: ` : ""}${state.planError.message}`}
        </p>
      ) : null}

      {state.correctionDiff.length > 0 ? (
        <div className="diff-line" role="status">
          {state.correctionDiff.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      ) : null}

      {!plan ? (
        <p className="empty">Plan appears when the inventory is ready.</p>
      ) : (
        <div className={state.planLoading ? "plan-lines loading" : "plan-lines"}>
          <h3>Package</h3>
          {plan.upgrades.length === 0 ? (
            <p className="empty">No upgrades selected for this budget and role.</p>
          ) : (
            <ul className="upgrade-list">
              {plan.upgrades.map((line) => {
                const payback = paybackText(line.cost_low_usd, line.cost_high_usd, line.bill_saved_usd_yr);
                return (
                <li key={line.upgrade_id} className="upgrade-line">
                  <div className="upgrade-head">
                    <strong className="upgrade-name">{line.name}</strong>
                    <span className="upgrade-saving" title={formatKwh(line.kwh_saved_yr)}>
                      {formatCurrency(line.bill_saved_usd_yr)}
                      <small>/yr saved</small>
                    </span>
                  </div>
                  <p className="upgrade-cost">
                    Costs {formatCostShort(line.cost_low_usd, line.cost_high_usd)}
                    {payback ? ` · ${payback.toLowerCase()}` : ""}
                  </p>
                  <p className="who-pays">{whoPaysSentence(line.who_pays)}</p>
                  <div className="upgrade-foot">
                    <span className={`evidence-note ${line.evidence_level === "verified" ? "seen" : "estimated"}`}>
                      {evidenceNote(line.evidence_level)}
                    </span>
                    <button className="link-button" onClick={() => void showExplain(line)}>
                      {explainFor === line.upgrade_id ? "Hide" : "Why this?"}
                    </button>
                  </div>
                  {explainFor === line.upgrade_id ? (
                    <ExplainBox
                      formula={line.explanation}
                      text={explain.text}
                      generatedBy={explain.generatedBy}
                      loading={explain.loading}
                      error={explain.error}
                      onClose={() => setExplainFor(null)}
                    />
                  ) : null}
                </li>
                );
              })}
            </ul>
          )}

          <div className="totals">
            <h3>Totals</h3>
            <dl>
              <div>
                <dt>Cost</dt>
                <dd>{formatCostRange(plan.totals.cost_low_usd, plan.totals.cost_high_usd)}</dd>
              </div>
              <div>
                <dt>Energy saved</dt>
                <dd>{formatKwh(plan.totals.kwh_saved_yr)}</dd>
              </div>
              <div>
                <dt>Bill savings</dt>
                <dd>{formatCurrency(plan.totals.bill_saved_usd_yr, true)}/yr</dd>
              </div>
              <div>
                <dt>Payback</dt>
                <dd>{formatPayback(plan.totals.payback_years)}</dd>
              </div>
              <div>
                <dt>Baseline</dt>
                <dd>{formatKwh(plan.totals.baseline_kwh_yr)}</dd>
              </div>
              <div>
                <dt>After upgrades</dt>
                <dd>{formatKwh(plan.totals.after_kwh_yr)}</dd>
              </div>
              <div>
                <dt>Combinations evaluated</dt>
                <dd>{formatNumber(plan.combos_evaluated)}</dd>
              </div>
            </dl>
          </div>

          <div className="excluded">
            <h3>Excluded</h3>
            {plan.excluded.length === 0 ? (
              <p className="empty">Nothing excluded for this request.</p>
            ) : (
              <ul className="note-list">
                {plan.excluded.map((item) => (
                  <li key={item.upgrade_id}>
                    <strong>{reasonText(item.reason_code)}:</strong> {item.reason}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="notes">
            <h3>Notes</h3>
            {plan.notes.length === 0 ? (
              <p className="empty">No notes.</p>
            ) : (
              <ul className="note-list">
                {plan.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="assumptions">
            <h3>Assumptions used</h3>
            <ul className="assumption-list">
              {plan.assumptions_used.map((item) => (
                <li key={item.key} title={item.source || undefined}>
                  <span className="assumption-key">{item.key}</span>
                  <span>
                    {formatNumber(item.value, Number.isInteger(item.value) ? 0 : 2)} {item.unit}
                  </span>
                  <span className={`badge ${item.status === "unverified_default" ? "badge-warn" : "badge-muted"}`}>
                    {item.status === "unverified_default" ? "unverified default" : item.status.replace("_", " ")}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
