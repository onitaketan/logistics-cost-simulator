from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, hash_password, require
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ok
from app.schemas.dto import DEFAULT_LIMIT, MAX_LIMIT, UserCreate, UserUpdate
from app.services import audit_service

router = APIRouter(prefix="/users", tags=["users"])


def _out(u: User) -> dict:
    return {"id": str(u.id), "name": u.name, "email": u.email,
            "role": u.role, "department": u.department, "status": u.status}


@router.get("")
def list_users(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.USER_MANAGE))],
    role: str | None = None,
    status_: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if status_:
        stmt = stmt.where(User.status == status_)
    stmt = stmt.limit(limit).offset(offset)
    return ok([_out(u) for u in db.scalars(stmt).all()])


@router.post("")
def create_user(
    body: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.USER_MANAGE))],
):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "このメールアドレスは既に登録されています。")
    u = User(name=body.name, email=body.email, role=body.role,
             department=body.department, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="create",
                         target_type="user", target_id=str(u.id), after=_out(u))
    db.commit()
    return ok(_out(u))


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.USER_MANAGE))],
):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ユーザーが見つかりません。")
    before = _out(u)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(u, k, v)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update",
                         target_type="user", target_id=user_id, before=before, after=_out(u))
    db.commit()
    return ok(_out(u))
