from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.schemas.common import ok

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
def list_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.AUDIT_VIEW))],
    target_type: str | None = None,
    action_type: str | None = None,
    from_: date | None = None,
    to: date | None = None,
    limit: int = 100,
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if action_type:
        stmt = stmt.where(AuditLog.action_type == action_type)
    stmt = stmt.limit(min(limit, 500))
    rows = db.scalars(stmt).all()
    return ok([
        {"id": str(a.id), "user_id": str(a.user_id) if a.user_id else None,
         "action_type": a.action_type, "target_type": a.target_type,
         "target_id": str(a.target_id) if a.target_id else None,
         "created_at": a.created_at.isoformat() if a.created_at else None}
        for a in rows
    ])
