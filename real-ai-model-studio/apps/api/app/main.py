"""Real AI Model Studio API.

All routers mount under /api/v1 (docs/03_api_spec.md). Compliance and generation
gating live in services; routers only orchestrate. Importing app.models registers
all tables on Base.metadata.
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.models  # noqa: F401  (register ORM tables)
from app.core.config import get_settings
from app.db.session import engine
from app.routers import (
    assets,
    audit,
    auth,
    compliance,
    contracts,
    dashboard,
    deliveries,
    files,
    generations,
    models,
    outputs,
    projects,
    prompt_templates,
    users,
)
from app.services.generation_service import GenerationBlocked

app = FastAPI(
    title="Real AI Model Studio API",
    version="0.1.0",
    description="社内専用・実在AIモデル生成基盤。生成可否は Backend/API/DB で強制する。",
)

# Browser frontend runs on a separate origin (split deployment). Allow only the
# configured origins; never use "*" here since requests carry the bearer token.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

for r in (
    auth.router,
    users.router,
    models.router,
    contracts.router,
    assets.router,
    projects.router,
    compliance.router,
    generations.router,
    prompt_templates.router,
    outputs.router,
    deliveries.router,
    files.router,
    audit.router,
    dashboard.router,
):
    app.include_router(r, prefix=API_PREFIX)


def _envelope(status_code: int, code: str, message: str) -> JSONResponse:
    """Every error leaves the API in the same {success,data,error} shape the
    frontend expects (docs/03 §2). Without this, FastAPI's default HTTPException
    ({"detail": ...}) and validation ({"detail": [...]}) bodies bypass the
    envelope and the UI can only show a generic 'Request failed'."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "data": None,
                 "error": {"code": code, "message": message}},
    )


@app.exception_handler(GenerationBlocked)
async def _blocked_handler(_request, exc: GenerationBlocked):
    return _envelope(422, "generation_blocked", str(exc))


@app.exception_handler(StarletteHTTPException)
async def _http_exc_handler(_request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "リクエストを処理できません。"
    return _envelope(exc.status_code, f"http_{exc.status_code}", detail)


@app.exception_handler(RequestValidationError)
async def _validation_handler(_request, exc: RequestValidationError):
    # Summarize the first field error into a readable message; keep 422.
    errs = exc.errors()
    if errs:
        loc = ".".join(str(p) for p in errs[0].get("loc", []) if p != "body")
        msg = errs[0].get("msg", "入力が不正です。")
        message = f"{loc}: {msg}" if loc else msg
    else:
        message = "入力が不正です。"
    return _envelope(422, "validation_error", message)


@app.exception_handler(ValueError)
async def _value_error_handler(_request, exc: ValueError):
    # Domain guards raise bare ValueError (e.g. unknown AI adapter). Surface as a
    # 400 envelope instead of an opaque 500.
    return _envelope(400, "invalid_request", str(exc) or "不正なリクエストです。")


@app.exception_handler(Exception)
async def _unhandled_handler(_request, exc: Exception):
    # Last-resort: never leak a stack trace or raw string to the client.
    return _envelope(500, "internal_error", "サーバー内部エラーが発生しました。")


@app.get("/health")
def health():
    """Liveness + DB reachability. Returns 503 when the database is unreachable
    so orchestrators can gate traffic (docs/06 §監視)."""
    db_ok = True
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
    except Exception:
        db_ok = False
    payload = {"status": "ok" if db_ok else "degraded",
               "env": get_settings().app_env, "database": "up" if db_ok else "down"}
    if not db_ok:
        return JSONResponse(status_code=503,
                            content={"success": False, "data": payload, "error":
                                     {"code": "db_unavailable", "message": "データベースに接続できません。"}})
    return {"success": True, "data": payload, "error": None}
