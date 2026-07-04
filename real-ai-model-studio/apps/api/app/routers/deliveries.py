from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import GenerationOutput
from app.schemas.common import ok
from app.schemas.dto import DeliveryCreate
from app.models.workflow import Delivery
from app.services import audit_service

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.post("")
def create_delivery(
    body: DeliveryCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.DELIVER))],
):
    output = db.get(GenerationOutput, body.output_id)
    if not output:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画像が見つかりません。")
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
