from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.model import Model
from app.schemas.common import ok
from app.schemas.dto import DEFAULT_LIMIT, MAX_LIMIT, AdultVerify, ModelCreate, ModelUpdate
from app.services import audit_service

router = APIRouter(prefix="/models", tags=["models"])


def _out(m: Model) -> dict:
    return {"id": str(m.id), "stage_name": m.stage_name, "agency_name": m.agency_name,
            "adult_verified": m.adult_verified, "status": m.status, "birth_date": str(m.birth_date) if m.birth_date else None}


@router.get("")
def list_models(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.MODEL_VIEW))],
    status_: str | None = None,
    agency_name: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    stmt = select(Model).where(Model.deleted_at.is_(None))
    if status_:
        stmt = stmt.where(Model.status == status_)
    if agency_name:
        stmt = stmt.where(Model.agency_name == agency_name)
    stmt = stmt.limit(limit).offset(offset)
    return ok([_out(m) for m in db.scalars(stmt).all()])


@router.post("")
def create_model(
    body: ModelCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.MODEL_EDIT))],
):
    m = Model(**body.model_dump(exclude={"adult_verified"}))
    # adult verification is a privileged action; ignore client-provided flag on create.
    db.add(m)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="create",
                         target_type="model", target_id=str(m.id), after=_out(m))
    db.commit()
    return ok(_out(m))


@router.get("/{model_id}")
def get_model(
    model_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.MODEL_VIEW))],
):
    m = db.get(Model, model_id)
    if not m or m.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "モデルが見つかりません。")
    return ok(_out(m))


@router.patch("/{model_id}")
def update_model(
    model_id: str,
    body: ModelUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.MODEL_EDIT))],
):
    m = db.get(Model, model_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "モデルが見つかりません。")
    before = _out(m)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update",
                         target_type="model", target_id=model_id, before=before, after=_out(m))
    db.commit()
    return ok(_out(m))


@router.post("/{model_id}/adult-verification")
def verify_adult(
    model_id: str,
    body: AdultVerify,
    db: Annotated[Session, Depends(get_db)],
    # only contract managers (legal/admin) can attest adult verification
    user: Annotated[CurrentUserDep, Depends(require(Perm.CONTRACT_MANAGE))],
):
    m = db.get(Model, model_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "モデルが見つかりません。")
    m.adult_verified = body.adult_verified
    m.adult_verified_at = datetime.now(timezone.utc) if body.adult_verified else None
    m.adult_verified_by = user.id if body.adult_verified else None
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update",
                         target_type="model", target_id=model_id,
                         after={"adult_verified": body.adult_verified})
    db.commit()
    return ok(_out(m))
