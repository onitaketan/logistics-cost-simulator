"""Generation endpoints — the enforced gate.

`assert_generation_allowed` re-validates the compliance check at request time
(app layer), and the DB trigger validates again on INSERT (db layer). Neither
trusts the UI.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import AIEngine, ComplianceCheck, Generation, GenerationOutput
from app.schemas.common import ok
from app.schemas.dto import GenerationCreate
from app.services import audit_service, generation_service as gen
from app.services.ai_engines import get_adapter
from app.services.storage_service import compute_hash

router = APIRouter(tags=["generations"])


@router.post("/generations")
async def create_generation(
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
    try:
        gen.assert_generation_allowed(ref, project_id=body.project_id, model_id=body.model_id)
    except gen.GenerationBlocked as e:
        # 422: request is well-formed but forbidden by compliance state
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))

    engine = None
    if body.ai_engine_id:
        engine = db.get(AIEngine, body.ai_engine_id)

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
        status="running",
        generated_by=user.id,
    )
    db.add(generation)
    db.flush()

    # Run the adapter (mock in MVP). In production this is dispatched to a queue worker.
    adapter_key = engine.adapter_key if engine else get_settings().ai_engine
    adapter = get_adapter(adapter_key)
    images = await gen.run_generation(adapter, body.prompt_text, body.generation_params)
    for img in images:
        db.add(GenerationOutput(
            generation_id=generation.id,
            file_path=img.file_path,
            file_hash=compute_hash(img.file_path.encode()),
            width=img.width,
            height=img.height,
            output_status="candidate",
        ))
    generation.status = "completed"
    db.flush()

    audit_service.record(
        db, user_id=user.id, action_type="generate", target_type="output",
        target_id=str(generation.id),
        after={"compliance_check_id": body.compliance_check_id, "count": len(images)},
    )
    db.commit()
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
        {"id": str(o.id), "file_path": o.file_path, "output_status": o.output_status,
         "width": o.width, "height": o.height}
        for o in rows
    ])
