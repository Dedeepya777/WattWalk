"""FastAPI app: every route in shared/contracts/README.md section 4. Owner: Person 3.

Run: uvicorn wattwalk.api.app:app --app-dir backend --reload --port 8000
Plan, corrections and audit reads never call a model (D3).
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .. import config, health_registry, store
from ..agent import ask as ask_mod
from ..agent import providers as P
from ..agent import run as runner
from ..agent import tools
from ..agent.verify import verify_audit  # noqa: F401  (re-exported for convenience)
from ..engine.asset_energy import energy_response
from ..contracts import (
    AiAlternativesResponse,
    AnswerRequest,
    AssetEnergyResponse,
    Asset,
    AuditResponse,
    AuditStatus,
    Benchmark,
    Building,
    CorrectionRequest,
    CorrectionResponse,
    Coverage,
    ExplainRequest,
    ExplainResponse,
    HeatShare,
    Health,
    HealthIntegrations,
    ModelCall,
    ModelCallSummary,
    Observation,
    Pano,
    PlanRequest,
    PlanResponse,
    Question,
    Room,
    StartAuditRequest,
    TestModel,
)
from . import errors as E
from . import replay, sse

log = logging.getLogger("wattwalk.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="WattWalk API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
E.install(app)

TEST_MODELS_FILE = Path(__file__).with_name("test_models.json")


def _require_audit(sid: str) -> None:
    try:
        ok = store.exists(sid)
    except ValueError:
        ok = False
    if not ok:
        raise E.audit_not_found(sid)


def _status(sid: str) -> AuditStatus:
    return runner.current_status(sid) or AuditStatus(sid=sid, status="idle", mode="live")


# ----------------------------------------------------------------------------- meta
# Probe functions owned by Person 1 (data) and Person 2 (vision). Each makes one cheap real call and
# records its outcome in health_registry itself.
PROBES = {
    "matterport": ("wattwalk.data.probes", "probe_matterport"),
    "vexcel": ("wattwalk.data.probes", "probe_vexcel"),
    "costar_kit": ("wattwalk.data.probes", "probe_costar_kit"),
    "ebewe": ("wattwalk.data.probes", "probe_ebewe"),
    "bedrock": ("wattwalk.vision.probes", "probe_bedrock"),
}
PROBE_TIMEOUT_S = 20


def _configured() -> dict[str, bool]:
    return {
        "matterport": bool(config.MATTERPORT_API_KEY and config.MATTERPORT_API_TOKEN),
        "vexcel": bool(config.VEXCEL_API_KEY),
        "costar_kit": bool(config.COSTAR_KIT_ZIP),
        "ebewe": True,
        "bedrock": bool(config.SMALL_VISION_MODEL_ID or config.LARGE_VISION_MODEL_ID),
    }


def _is_fixture(name: str) -> bool:
    mode = config.VISION_MODE if name == "bedrock" else config.DATA_MODE
    return mode == "fixture"


def _integrations() -> HealthIntegrations:
    conf = _configured()
    return HealthIntegrations(**{n: health_registry.status(n, conf[n], _is_fixture(n)) for n in health_registry.INTEGRATIONS})


def _probe_fn(name: str):
    module, fn = PROBES[name]
    try:
        return getattr(importlib.import_module(module), fn)
    except (ImportError, AttributeError):
        return None


def run_probes() -> None:
    """Call every live, configured integration's probe concurrently, capped at PROBE_TIMEOUT_S overall."""
    conf = _configured()
    jobs = {}
    for name in health_registry.INTEGRATIONS:
        if _is_fixture(name) or not conf[name]:
            continue
        fn = _probe_fn(name)
        if fn is None:
            log.info("health probe %s: probe not available (%s.%s not merged)", name, *PROBES[name])
            continue
        jobs[name] = fn
    if not jobs:
        return
    pool = ThreadPoolExecutor(max_workers=len(jobs), thread_name_prefix="probe")
    futures = {pool.submit(fn): name for name, fn in jobs.items()}
    done, pending = wait(futures, timeout=PROBE_TIMEOUT_S)
    for f in done:
        name = futures[f]
        exc = f.exception()
        if exc is not None:  # a probe should record itself; make sure a crash still counts as a failure
            health_registry.record(name, False, f"probe raised {type(exc).__name__}: {exc}")
        entry = health_registry.last(name)
        log.info("health probe %s: %s", name, entry and ("ok" if entry[0] else "failed") + (f" ({entry[1]})" if entry[1] else ""))
    for f in pending:
        name = futures[f]
        health_registry.record(name, False, f"probe timed out after {PROBE_TIMEOUT_S} s")
        log.warning("health probe %s: timed out after %s s", name, PROBE_TIMEOUT_S)
    pool.shutdown(wait=False, cancel_futures=True)


@app.get("/health", response_model=Health)
def health(probe: bool = False) -> Health:
    """Plain GET reads the registry only. GET /health?probe=1 first calls each integration's probe."""
    if probe:
        run_probes()
    if config.AGENT_MODE == "deep_agents" and not config.PLANNER_MODEL_ID:
        log.warning("health: WATTWALK_AGENT_MODE=deep_agents but WATTWALK_PLANNER_MODEL_ID is empty")
    integ = _integrations()
    ok = all(v == "live" for v in integ.model_dump().values())
    return Health(status="ok" if ok else "degraded", integrations=integ)


@app.get("/models/test", response_model=list[TestModel])
def models_test() -> list[TestModel]:
    out = []
    for m in json.loads(TEST_MODELS_FILE.read_text(encoding="utf-8")):
        m["has_fixture"] = runner.fixture_available(m["sid"])
        m["has_replay"] = replay.has_replay(m["sid"])
        out.append(TestModel.model_validate(m))
    return out


@app.get("/benchmark", response_model=Benchmark)
def benchmark() -> Benchmark:
    results = config.REPO_ROOT / "eval" / "results.json"
    src = results if results.exists() else config.EXAMPLES_DIR / "benchmark_not_run.json"
    return Benchmark.model_validate_json(src.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- audit lifecycle
@app.post("/audits/{sid}", status_code=202, response_model=AuditStatus)
async def start_audit(sid: str, req: StartAuditRequest) -> AuditStatus:
    try:
        store._check_sid(sid)
    except ValueError:
        raise E.invalid(f"invalid sid {sid!r}", "sid", sid)
    try:
        return await runner.start_run(sid, req.mode)
    except runner.Conflict:
        raise E.conflict(f"An audit for {sid} is already running.", sid=sid)
    except runner.NotFound as e:
        raise E.not_found(str(e), sid=sid, mode=req.mode)


@app.post("/audits/{sid}/cancel", response_model=AuditStatus)
async def cancel_audit(sid: str) -> AuditStatus:
    _require_audit(sid)
    try:
        return await runner.cancel_run(sid)
    except runner.NotFound:
        raise E.audit_not_found(sid)


@app.delete("/audits/{sid}", response_model=AuditStatus)
def delete_audit(sid: str) -> AuditStatus:
    try:
        return runner.reset(sid)
    except runner.Conflict:
        raise E.conflict(f"An audit for {sid} is running; cancel it first.", sid=sid)
    except ValueError:
        raise E.audit_not_found(sid)


def _summary(calls: list[ModelCall]) -> ModelCallSummary:
    tin = [c.tokens_in for c in calls if c.tokens_in is not None]
    tout = [c.tokens_out for c in calls if c.tokens_out is not None]
    return ModelCallSummary(
        calls_total=len(calls),
        calls_small=sum(c.model_tier == "small" for c in calls),
        calls_large=sum(c.model_tier == "large" for c in calls),
        calls_planner=sum(c.model_tier == "planner" for c in calls),
        cache_hits=sum(c.cache_hit for c in calls),
        tokens_in=sum(tin) if tin or not calls else None,
        tokens_out=sum(tout) if tout or not calls else None,
    )


@app.get("/audits/{sid}", response_model=AuditResponse)
def get_audit(sid: str) -> AuditResponse:
    _require_audit(sid)
    with store.lock(sid):
        return AuditResponse(
            status=_status(sid),
            building=store.read(sid, "building.json", Building),
            rooms=store.read(sid, "rooms.json", list[Room], default=[]),
            panos=store.read(sid, "panos.json", list[Pano], default=[]),
            observations=store.read(sid, "observations.json", list[Observation], default=[]),
            inventory=store.read(sid, "inventory.json", list[Asset], default=[]),
            coverage=store.read(sid, "coverage.json", Coverage),
            heat_shares=store.read(sid, "heat_shares.json", list[HeatShare], default=[]),
            model_call_summary=_summary(store.read(sid, "model_calls.json", list[ModelCall], default=[])),
            questions=store.read(sid, "questions.json", list[Question], default=[]),
            report_md=store.read_text(sid, "report.md"),
        )


@app.get("/audits/{sid}/events")
def events(sid: str, from_seq: int = 0, speed: float = 1.0):
    _require_audit(sid)
    return sse.stream(sid, from_seq, speed)


@app.get("/audits/{sid}/model_calls", response_model=list[ModelCall])
def model_calls(sid: str) -> list[ModelCall]:
    _require_audit(sid)
    return store.read(sid, "model_calls.json", list[ModelCall], default=[])


@app.post("/audits/{sid}/answer", response_model=Question)
def answer(sid: str, req: AnswerRequest) -> Question:
    _require_audit(sid)
    try:
        return ask_mod.answer(sid, req.question_id, req.answer)
    except ask_mod.QuestionNotFound:
        raise E.not_found(f"No question {req.question_id} in audit {sid}.", sid=sid, question_id=req.question_id)
    except ask_mod.QuestionNotOpen:
        raise E.conflict(f"Question {req.question_id} is not open (answered or expired).", question_id=req.question_id)
    except ValueError as e:
        raise E.invalid(str(e), "answer", req.answer)


# ----------------------------------------------------------------------------- deterministic endpoints
def _inventory_and_building(sid: str) -> tuple[list[Asset], Building]:
    _require_audit(sid)
    inv = store.read(sid, "inventory.json", list[Asset])
    b = store.read(sid, "building.json", Building)
    if inv is None or b is None:
        raise E.not_found(f"Audit {sid} has no inventory yet; wait for the walk to finish.", sid=sid)
    return inv, b


def _plan(sid: str, inv: list[Asset], b: Building, req: PlanRequest) -> PlanResponse:
    try:
        return P.plan(sid, inv, b, req)
    except ValueError as e:
        msg = str(e)
        field = "overrides" if "overrides" in msg else None
        raise E.invalid(msg, field, None)


@app.post("/audits/{sid}/plan", response_model=PlanResponse)
def plan(sid: str, req: PlanRequest) -> PlanResponse:
    inv, b = _inventory_and_building(sid)
    return _plan(sid, inv, b, req)


@app.get("/audits/{sid}/energy", response_model=AssetEnergyResponse)
def asset_energy(sid: str) -> AssetEnergyResponse:
    """Energy and heat per inventory asset (engine/asset_energy.py); recomputed on every call."""
    inv, b = _inventory_and_building(sid)
    return energy_response(sid, inv, b)


@app.post("/audits/{sid}/assets/{asset_id}/alternatives/research", response_model=AiAlternativesResponse)
async def research_alternatives(sid: str, asset_id: str, refresh: bool = False) -> AiAlternativesResponse:
    """2-3 rough upgrade ideas for one asset from DeepSeek (engine/ai_alternatives.py), saved per audit."""
    from ..engine import ai_alternatives as ai

    inv, b = _inventory_and_building(sid)
    if asset_id not in {a.id for a in inv}:
        raise E.not_found(f"Audit {sid} has no asset {asset_id}.", sid=sid, asset_id=asset_id)
    try:
        return await asyncio.to_thread(ai.research, sid, asset_id, inv, b, None, refresh)
    except ai.ResearchUnavailable as e:
        raise E.ApiError(503, "upstream_unavailable", str(e), False, {"fix": "Add DEEPSEEK_API_KEY to .env and restart."})
    except ai.ResearchFailed as e:
        raise E.ApiError(502, "upstream_unavailable", f"Could not get alternatives: {e}", True)


@app.post("/audits/{sid}/explain", response_model=ExplainResponse)
async def explain(sid: str, req: ExplainRequest) -> ExplainResponse:
    inv, b = _inventory_and_building(sid)
    p = _plan(sid, inv, b, req.plan_request)
    if req.upgrade_id not in {u.upgrade_id for u in p.upgrades}:
        raise E.not_found(f"Upgrade {req.upgrade_id} is not in the chosen package for this request.",
                          upgrade_id=req.upgrade_id)
    text = P.explain_template(p, req.upgrade_id)
    if config.AGENT_MODE == "deep_agents" and config.PLANNER_MODEL_ID:
        from ..agent.deep import reword
        try:
            t0 = time.monotonic()
            new = await asyncio.wait_for(asyncio.to_thread(reword, text), timeout=config.TIMEOUTS_S["explain"])
            store.append_model_calls(sid, [ModelCall(
                id=f"mc_explain_{uuid.uuid4().hex[:8]}", agent="planner", kind="explain", model_id=config.PLANNER_MODEL_ID,
                model_tier="planner", latency_ms=int((time.monotonic() - t0) * 1000), cache_hit=False,
                at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))])
            if new:
                return ExplainResponse(upgrade_id=req.upgrade_id, text=new, generated_by="llm")
        except Exception as e:  # noqa: BLE001 - timeout or model error falls back to the template
            log.warning("explain rewording failed, using template: %s", e)
    return ExplainResponse(upgrade_id=req.upgrade_id, text=text, generated_by="template")


@app.post("/audits/{sid}/corrections", response_model=CorrectionResponse)
def corrections(sid: str, req: CorrectionRequest) -> CorrectionResponse:
    inv, b = _inventory_and_building(sid)
    if req.asset_id not in {a.id for a in inv}:
        raise E.not_found(f"No asset {req.asset_id} in audit {sid}.", asset_id=req.asset_id)
    with store.lock(sid):
        obs = store.observations(sid)
        stored = store.read(sid, "corrections.json", list[CorrectionRequest], default=[])
        new_inv = P.build_inventory(obs)
        try:
            for c in stored:
                new_inv, _ = P.apply_correction(new_inv, obs, c)
            new_inv, changed = P.apply_correction(new_inv, obs, req)
        except KeyError:
            raise E.not_found(f"No asset {req.asset_id} in audit {sid}.", asset_id=req.asset_id)
        except ValueError as e:
            raise E.invalid(str(e), req.field, req.value if isinstance(req.value, (str, int, float)) else None)
        cov = tools.coverage_for(sid, new_inv)
        p = _plan(sid, new_inv, b, req.plan_request)
        store.write(sid, "corrections.json", stored + [req])
        store.write(sid, "inventory.json", new_inv)
        store.write(sid, "coverage.json", cov)
        old_default = store.read(sid, "plan_default.json", PlanResponse)
        if old_default is not None:  # keep the stored default plan consistent with the corrected inventory
            store.write(sid, "plan_default.json", P.plan(sid, new_inv, b, old_default.request))
        geom = store.read(sid, "rooms.json", list[Room], default=[])
        if geom:
            store.write(sid, "heat_shares.json", P.heat_shares(geom, new_inv, b))
    return CorrectionResponse(inventory=new_inv, coverage=cov, plan=p, changed_asset_ids=changed)


@app.get("/audits/{sid}/files/{path:path}")
def files(sid: str, path: str):
    _require_audit(sid)
    rel = PurePosixPath(path)
    if ".." in rel.parts or "\\" in path or rel.is_absolute() or not rel.parts or rel.parts[0] not in ("crops", "vexcel"):
        raise E.not_found(f"No file {path}.", path=path)
    base = store.audit_dir(sid).resolve()
    target = (base / rel).resolve()
    if base not in target.parents or not target.is_file():
        raise E.not_found(f"No file {path}.", path=path)
    return FileResponse(target, media_type="image/jpeg")


@app.get("/", include_in_schema=False)
def root():
    return JSONResponse({"service": "wattwalk", "docs": "/docs"})
