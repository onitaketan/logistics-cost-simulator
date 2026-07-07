"""Generation endpoints — the enforced gate.

`assert_generation_allowed` re-validates the compliance check at request time
(app layer), and the DB trigger validates again on INSERT (db layer). Neither
trusts the UI.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import accessible_project_ids, assert_project_access
from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import ComplianceCheck, Generation, GenerationOutput
from app.models.model import Model
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
        assert_project_access(db, user, project_id)
        stmt = stmt.where(Generation.project_id == project_id)
    else:
        # Data scope: non-global roles see only generations of accessible projects.
        allowed = accessible_project_ids(db, user)
        if allowed is not None:
            if not allowed:
                return ok([])
            stmt = stmt.where(Generation.project_id.in_(allowed))
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
    # Data scope: the caller must have access to the target project.
    assert_project_access(db, user, body.project_id)
    # Consent gate: never generate against a soft-deleted model (defense in depth;
    # the worker re-checks this at execution time too).
    model = db.get(Model, body.model_id)
    if model is None or model.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "モデルが見つかりません。")
    # Screen the ACTUAL prompt/negative prompt sent to the engine (docs/05 §7).
    # A passing check must not become a licence to send an unscreened prompt.
    gen.assert_prompt_clean(body.prompt_text, body.negative_prompt_text)

    # Clamp the batch size to a sane range (1..8): the count drives real engine
    # cost and downstream review load, and must never be caller-unbounded.
    # Coerce defensively — a non-numeric output_count falls back to 1 rather than
    # raising (which would surface as an inconsistent 400/500).
    params = dict(body.generation_params or {})
    try:
        requested = int(params.get("output_count", 1))
    except (TypeError, ValueError):
        requested = 1
    output_count = max(1, min(requested, 8))
    params["output_count"] = output_count

    generation = Generation(
        project_id=body.project_id,
        model_id=body.model_id,
        compliance_check_id=body.compliance_check_id,
        ai_engine_id=body.ai_engine_id,
        prompt_text=body.prompt_text,
        negative_prompt_text=body.negative_prompt_text,
        prompt_template_id=body.prompt_template_id,
        generation_params=params,
        output_count=output_count,
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
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_VIEW))],
):
    g = db.get(Generation, generation_id)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "生成ジョブが見つかりません。")
    assert_project_access(db, user, g.project_id)
    return ok({"id": str(g.id), "status": g.status, "output_count": g.output_count})


@router.get("/generations/{generation_id}/outputs")
def list_outputs(
    generation_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_VIEW))],
):
    g = db.get(Generation, generation_id)
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "生成ジョブが見つかりません。")
    assert_project_access(db, user, g.project_id)
    rows = db.scalars(
        select(GenerationOutput).where(GenerationOutput.generation_id == generation_id)
    ).all()
    return ok([
        {"id": str(o.id), "file_path": o.file_path, "file_hash": o.file_hash,
         "output_status": o.output_status, "width": o.width, "height": o.height}
        for o in rows
    ])
