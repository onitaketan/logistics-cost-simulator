from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.model import ModelContract, ModelPermission
from app.schemas.common import ok
from app.schemas.dto import ContractCreate, PermissionCreate
from app.services import audit_service

router = APIRouter(tags=["contracts"])


@router.post("/models/{model_id}/contracts")
def create_contract(
    model_id: str,
    body: ContractCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.CONTRACT_MANAGE))],
):
    c = ModelContract(model_id=model_id, created_by=user.id, **body.model_dump())
    db.add(c)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="create",
                         target_type="contract", target_id=str(c.id),
                         after={"contract_number": c.contract_number})
    db.commit()
    return ok({"id": str(c.id), "contract_number": c.contract_number})


@router.get("/models/{model_id}/contracts")
def list_contracts(
    model_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.MODEL_VIEW))],
):
    rows = db.scalars(select(ModelContract).where(ModelContract.model_id == model_id)).all()
    return ok([{"id": str(c.id), "contract_number": c.contract_number,
                "contract_type": c.contract_type,
                "contract_start": str(c.contract_start),
                "contract_end": str(c.contract_end),
                "ai_generation_allowed": c.ai_generation_allowed,
                "ai_training_allowed": c.ai_training_allowed,
                "post_contract_use_allowed": c.post_contract_use_allowed}
               for c in rows])


@router.post("/models/{model_id}/permissions")
def create_permission(
    model_id: str,
    body: PermissionCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.CONTRACT_MANAGE))],
):
    contract = db.get(ModelContract, body.contract_id)
    if not contract:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "契約が存在しません。")
    # The permission must attach to a contract of the SAME model. Otherwise a
    # permission row could bind model A's likeness to model B's contract, and the
    # compliance engine would evaluate generation against the wrong consent scope.
    if str(contract.model_id) != str(model_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "契約が指定モデルに属していません。")
    p = ModelPermission(model_id=model_id, **body.model_dump())
    db.add(p)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="create",
                         target_type="permission", target_id=str(p.id))
    db.commit()
    return ok({"id": str(p.id)})


@router.get("/models/{model_id}/permissions")
def list_permissions(
    model_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.MODEL_VIEW))],
):
    rows = db.scalars(select(ModelPermission).where(ModelPermission.model_id == model_id)).all()
    return ok([{"id": str(p.id), "contract_id": str(p.contract_id),
                "media_scope": p.media_scope, "region_scope": p.region_scope,
                "product_scope": p.product_scope,
                "prohibited_product_scope": p.prohibited_product_scope,
                "swimwear_allowed": p.swimwear_allowed, "underwear_allowed": p.underwear_allowed,
                "bath_allowed": p.bath_allowed, "exposure_level_max": p.exposure_level_max,
                "overseas_allowed": p.overseas_allowed,
                "approval_required_level": p.approval_required_level}
               for p in rows])
