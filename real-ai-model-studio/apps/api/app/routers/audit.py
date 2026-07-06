import csv
import io
from datetime import date, datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.schemas.common import ok

router = APIRouter(prefix="/audit-logs", tags=["audit"])


def _filtered(target_type, action_type, date_from, date_to):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if action_type:
        stmt = stmt.where(AuditLog.action_type == action_type)
    # Inclusive date range on created_at (docs/03 §16: ?from=...&to=...).
    if date_from:
        stmt = stmt.where(
            AuditLog.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        )
    if date_to:
        stmt = stmt.where(
            AuditLog.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        )
    return stmt


@router.get("")
def list_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.AUDIT_VIEW))],
    target_type: str | None = None,
    action_type: str | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: int = Query(100, ge=1, le=500),
):
    stmt = _filtered(target_type, action_type, date_from, date_to).limit(limit)
    rows = db.scalars(stmt).all()
    return ok([
        {"id": str(a.id), "user_id": str(a.user_id) if a.user_id else None,
         "action_type": a.action_type, "target_type": a.target_type,
         "target_id": str(a.target_id) if a.target_id else None,
         "created_at": a.created_at.isoformat() if a.created_at else None}
        for a in rows
    ])


@router.get("/export")
def export_audit_csv(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.AUDIT_VIEW))],
    target_type: str | None = None,
    action_type: str | None = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    limit: int = Query(10000, ge=1, le=100000),
):
    """CSV export of the audit trail (P1-003). Same filters as the list endpoint."""
    stmt = _filtered(target_type, action_type, date_from, date_to).limit(limit)
    rows = db.scalars(stmt).all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["created_at", "user_id", "action_type", "target_type",
                "target_id", "ip_address"])
    for a in rows:
        w.writerow([
            a.created_at.isoformat() if a.created_at else "",
            str(a.user_id) if a.user_id else "",
            a.action_type,
            a.target_type or "",
            str(a.target_id) if a.target_id else "",
            a.ip_address or "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )
