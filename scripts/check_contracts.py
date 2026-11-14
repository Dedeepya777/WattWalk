"""Check that contract copies match the canonical shared pack and that all examples validate.

Run from the repository root before every pull request:
    python scripts/check_contracts.py
Exit code 0 means OK. Owner: Person 3.
"""
import filecmp
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
problems: list[str] = []

pairs = [
    (SHARED / "contracts" / "python" / "contracts.py", ROOT / "backend" / "wattwalk" / "contracts.py"),
    (SHARED / "contracts" / "typescript" / "contracts.ts", ROOT / "frontend" / "src" / "contracts.ts"),
]
for canonical, copy in pairs:
    if not copy.exists():
        problems.append(f"missing copy: {copy.relative_to(ROOT)}")
    elif not filecmp.cmp(canonical, copy, shallow=False):
        problems.append(f"copy differs from canonical: {copy.relative_to(ROOT)} (follow shared/integration.md section 6)")

try:
    sys.path.insert(0, str(SHARED / "contracts" / "python"))
    import contracts as C  # noqa: E402
    from pydantic import TypeAdapter  # noqa: E402
except ImportError as exc:
    print(f"pydantic not installed ({exc}); skipped example validation")
    C = None

if C is not None:
    single = {
        "model_geometry": C.ModelGeometry, "building": C.Building, "coverage": C.Coverage,
        "start_audit_request": C.StartAuditRequest, "correction_request": C.CorrectionRequest,
        "correction_response": C.CorrectionResponse, "explain_request": C.ExplainRequest,
        "explain_response": C.ExplainResponse, "answer_request": C.AnswerRequest,
    }
    lists = {"observations": C.Observation, "inventory": C.Asset, "heat_shares": C.HeatShare,
             "model_calls": C.ModelCall, "questions": C.Question, "test_models": C.TestModel}
    prefixes = {"audit_response": C.AuditResponse, "audit_status_": C.AuditStatus, "plan_request_": C.PlanRequest,
                "plan_response_": C.PlanResponse, "health_": C.Health, "benchmark_": C.Benchmark, "error_": C.Error}
    for path in sorted((SHARED / "examples").glob("*.json")):
        stem = path.stem
        model = single.get(stem)
        is_list = stem in lists
        if is_list:
            model = lists[stem]
        if model is None:
            model = next((m for p, m in prefixes.items() if stem.startswith(p)), None)
        if model is None:
            problems.append(f"no contract mapped for example {path.name}")
            continue
        data = json.loads(path.read_text())
        try:
            if is_list:
                TypeAdapter(list[model]).validate_python(data)
            else:
                model.model_validate(data)
        except Exception as exc:  # pydantic.ValidationError
            problems.append(f"{path.name}: {exc}")
    events = SHARED / "examples" / "events.jsonl"
    for i, line in enumerate(events.read_text().splitlines()):
        if line.strip():
            try:
                C.Event.model_validate_json(line)
            except Exception as exc:
                problems.append(f"events.jsonl line {i + 1}: {exc}")

if problems:
    print("CONTRACT CHECK FAILED")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print("Contract check OK")
