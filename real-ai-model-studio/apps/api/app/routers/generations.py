"""Generation endpoints — the enforced gate.

`assert_generation_allowed` re-validates the compliance check at request time
(app layer), and the DB trigger validates again on INSERT (db layer). Neither
trusts the UI.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import ComplianceCheck, Generation, GenerationOutput
from app.schemas.common import ok
from app.schemas.dto import DEFAULT_LIMIT, MAX_LIMIT, GenerationCreate
from app.services import generation_service as gen

router = APIRouter(tags=["generations"])


@router.get("/generations")
def list_generations(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_VIEW))],
    project_id: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    stmt = select(Generation)
    if project_id:
        stmt = stmt.where(Generation.project_id == project_id)
    stmt = stmt.order_by(Generation.generated_at.desc()).limit(limit).offset(offset)
    rows = db.scalars(stmt).all()
    return ok([
        {
            "id": str(g.id),
            "project_id": str(g.project_id),
            "model_id": str(g.model_id),
            "status": g.status,
            "output_count": g.output_count,
            "prompt_text": g.prompt_text,
            "generated_at": g.generated_at.isoformat() if g.generated_at else None,
        }
        for g in rows
    ])


@router.post("/generations")
def create_generation(
    body: GenerationCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.GENERATE))],
):
    check = db.get(ComplianceCheck, body.compliance_check_id)
    ref = None
    if check:
        ref = gen.ComplianceCheckRef(
            id=str(check.id), project_id=str(check.project_id),
            model_id=str(check.model_id), check_status=check.check_status,
        )
    # Request-time gate (checkpoint 1). Raises GenerationBlocked if the check is
    # missing / mismatched / not ok|conditional; the app-level handler turns that
    # into the consistent 422 envelope.
    gen.assert_generation_allowed(ref, project_id=body.project_id, model_id=body.model_id)

    generation = Generation(
        project_id=body.project_id,
        model_id=body.model_id,
        compliance_check_id=body.compliance_check_id,
        ai_engine_id=body.ai_engine_id,
        prompt_text=body.prompt_text,
        negative_prompt_text=body.negative_prompt_text,
        prompt_template_id=body.prompt_template_id,
        generation_params=body.generation_params,
        output_count=int(body.generation_params.get("output_count", 1)),
        status="queued",
        generated_by=user.id,
    )
    db.add(generation)
    # Commit the queued row (DB trigger validates at INSERT — checkpoint 2) BEFORE
    # enqueuing, so the worker's own session can see it. The worker re-validates
    # compliance at execution time (checkpoint 3) and produces the outputs.
    db.commit()

    # Dispatch to the queue worker. In eager mode (local/dev/test) this runs the
    # task inline, so the row already reaches 'completed' before we respond;
    # refresh() then reflects that terminal state. In async mode it stays 'queued'
    # and the client polls until the worker finishes.
    gen.enqueue_generation(generation.id)
    db.refresh(generation)

    return ok({"generation_id": str(generation.id), "status": generation.status})


@router.get("/generations/{generation_id}")
def get_generation(
    generation_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUserDep,
):
    g = db.get(Generation, generation_id)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "生成ジョブが見つかりません。")
    return ok({"id": str(g.id), "status": g.status, "output_count": g.output_count})


@router.get("/generations/{generation_id}/outputs")
def list_outputs(
    generation_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUserDep,
):
    rows = db.scalars(
        select(GenerationOutput).where(GenerationOutput.generation_id == generation_id)
    ).all()
    return ok([
        {"id": str(o.id), "file_path": o.file_path, "file_hash": o.file_hash,
         "output_status": o.output_status, "width": o.width, "height": o.height}
        for o in rows
    ])
