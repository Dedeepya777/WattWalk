"""Mapping from exceptions to the Error contract (plan 7.14, 12.6). Owner: Person 3."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..agent.providers import StubLimitation
from ..contracts import AnswerRequest, CorrectionRequest, ExplainRequest, PlanRequest
from ..errors import UpstreamError

# Last path segment -> request body model, used to phrase range errors ("between 0 and 50000").
_BODY_MODELS = {"plan": PlanRequest, "corrections": CorrectionRequest, "explain": ExplainRequest, "answer": AnswerRequest}

log = logging.getLogger("wattwalk.api")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False, details: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.retryable, self.details = status, code, message, retryable, details or {}


def body(code: str, message: str, retryable: bool, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "retryable": retryable, "details": details or {}}}


def not_found(message: str, **details) -> ApiError:
    return ApiError(404, "not_found", message, False, details)


def audit_not_found(sid: str) -> ApiError:
    return not_found(f"No audit exists for sid {sid}. Start one with POST /audits/{sid}.", sid=sid)


def conflict(message: str, **details) -> ApiError:
    return ApiError(409, "conflict", message, True, details)


def invalid(message: str, field: str | None = None, value=None) -> ApiError:
    details = {}
    if field is not None:
        details["field"] = field
        details["value"] = value
    return ApiError(422, "invalid_request", message, False, details)


def _fmt(x) -> str:
    return str(int(x)) if isinstance(x, (int, float)) and float(x).is_integer() else str(x)


def _bounds(model, loc: list[str]):
    for part in loc[:-1]:  # descend into nested models (for example plan_request.budget_usd)
        f = getattr(model, "model_fields", {}).get(part)
        model = f.annotation if f is not None else None
    field = loc[-1] if loc else None
    if model is None or field not in getattr(model, "model_fields", {}):
        return None, None
    ge = le = None
    for m in model.model_fields[field].metadata:
        ge = getattr(m, "ge", ge)
        le = getattr(m, "le", le)
    return ge, le


def validation_error(exc: RequestValidationError, model=None) -> ApiError:
    err = exc.errors()[0] if exc.errors() else {"loc": ("body",), "msg": "invalid request"}
    loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
    field = ".".join(loc) or "body"
    value = err.get("input")
    if not isinstance(value, (str, int, float, bool, type(None))):
        value = None
    ge, le = _bounds(model, loc) if loc else (None, None)
    if err.get("type") in ("greater_than_equal", "less_than_equal") and ge is not None and le is not None:
        msg = f"{field} must be between {_fmt(ge)} and {_fmt(le)}."
    elif err.get("type") == "missing":
        msg = f"{field} is required."
    elif err.get("type") == "extra_forbidden":
        msg = f"{field} is not a known field."
    else:
        msg = f"{field}: {err.get('msg', 'invalid value')}."
    return invalid(msg, field, value)


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(_: Request, e: ApiError):
        return JSONResponse(body(e.code, e.message, e.retryable, e.details), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, e: RequestValidationError):
        a = validation_error(e, _BODY_MODELS.get(request.url.path.rstrip("/").rsplit("/", 1)[-1]))
        return JSONResponse(body(a.code, a.message, a.retryable, a.details), status_code=a.status)

    @app.exception_handler(UpstreamError)
    async def _upstream(_: Request, e: UpstreamError):
        status = 502 if e.code == "upstream_auth" else 503
        return JSONResponse(body(e.code, e.message, e.retryable, {"integration": e.integration}), status_code=status)

    @app.exception_handler(StubLimitation)
    async def _stub(_: Request, e: StubLimitation):
        return JSONResponse(body("internal", str(e), False, {"temporary_stub": True}), status_code=501)

    @app.exception_handler(ValueError)
    async def _value(_: Request, e: ValueError):
        return JSONResponse(body("invalid_request", str(e)[:300], False, {}), status_code=422)

    @app.exception_handler(Exception)
    async def _internal(_: Request, e: Exception):
        log.exception("unhandled error")
        return JSONResponse(body("internal", (str(e) or type(e).__name__)[:300], False, {}), status_code=500)
