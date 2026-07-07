from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import accessible_project_ids, assert_project_access
from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import Generation, GenerationOutput
from app.schemas.common import ok
from app.schemas.dto import DEFAULT_LIMIT, MAX_LIMIT, DeliveryCreate
from app.models.workflow import Delivery
from app.services import audit_service

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get("")
def list_deliveries(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_VIEW))],
    project_id: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    stmt = select(Delivery)
    if project_id:
        assert_project_access(db, user, project_id)
        stmt = stmt.where(Delivery.project_id == project_id)
    else:
        allowed = accessible_project_ids(db, user)
        if allowed is not None:
            if not allowed:
                return ok([])
            stmt = stmt.where(Delivery.project_id.in_(allowed))
    stmt = stmt.order_by(Delivery.created_at.desc()).limit(limit).offset(offset)
    rows = db.scalars(stmt).all()
    return ok([
        {
            "id": str(d.id),
            "project_id": str(d.project_id),
            "output_id": str(d.output_id),
            "delivered_to": d.delivered_to,
            "delivery_method": d.delivery_method,
            "usage_media": d.usage_media,
            "usage_region": d.usage_region,
            "usage_start": d.usage_start.isoformat() if d.usage_start else None,
            "usage_end": d.usage_end.isoformat() if d.usage_end else None,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in rows
    ])


@router.post("")
def create_delivery(
    body: DeliveryCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.DELIVER))],
):
    assert_project_access(db, user, body.project_id)
    output = db.get(GenerationOutput, body.output_id)
    if not output:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画像が見つかりません。")
    # Ownership: the output must belong to the project it is being delivered under.
    # Without this an approved image from project A could be delivered under
    # project B's (looser) usage scope — a permission-scope escape (docs/05 §9).
    generation = db.get(Generation, output.generation_id)
    if generation is None or str(generation.project_id) != str(body.project_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "画像が指定案件に属していません。")
    # Delivery is only permitted for approved outputs (post-approval gate).
    if output.output_status not in ("approved", "delivered"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "承認済みの画像のみ納品できます。")
    d = Delivery(delivered_by=user.id, **body.model_dump())
    db.add(d)
    output.output_status = "delivered"
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="deliver", target_type="delivery",
                         target_id=str(d.id), after={"delivered_to": body.delivered_to})
    db.commit()
    return ok({"id": str(d.id), "status": d.status})
