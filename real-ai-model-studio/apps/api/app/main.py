"""Real AI Model Studio API.

All routers mount under /api/v1 (docs/03_api_spec.md). Compliance and generation
gating live in services; routers only orchestrate. Importing app.models registers
all tables on Base.metadata.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

import app.models  # noqa: F401  (register ORM tables)
from app.core.config import get_settings
from app.routers import (
    assets,
    audit,
    auth,
    compliance,
    contracts,
    deliveries,
    files,
    generations,
    models,
    outputs,
    projects,
    users,
)
from app.services.generation_service import GenerationBlocked

app = FastAPI(
    title="Real AI Model Studio API",
    version="0.1.0",
    description="社内専用・実在AIモデル生成基盤。生成可否は Backend/API/DB で強制する。",
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
    outputs.router,
    deliveries.router,
    files.router,
    audit.router,
):
    app.include_router(r, prefix=API_PREFIX)


@app.exception_handler(GenerationBlocked)
async def _blocked_handler(_request, exc: GenerationBlocked):
    return JSONResponse(
        status_code=422,
        content={"success": False, "data": None,
                 "error": {"code": "generation_blocked", "message": str(exc)}},
    )


@app.get("/health")
def health():
    return {"success": True, "data": {"status": "ok", "env": get_settings().app_env}, "error": None}
