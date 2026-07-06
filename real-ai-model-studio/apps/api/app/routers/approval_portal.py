"""External approval portal endpoints (P2-001/P2-002).

Two authenticated endpoints let an internal legal-level user issue and list
approval links for an output; two PUBLIC (token-scoped, no JWT) endpoints let the
external agency/person view the image and record a decision. A portal decision
writes a normal `approvals` row (approver_id NULL = external) and flows through
the same approval-completeness gate as in-system approvals.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import ComplianceCheck, Generation, GenerationOutput
from app.models.project import Project
from app.models.workflow import Approval, ApprovalRequest
from app.schemas.common import ok
from app.schemas.dto import ApprovalRequestCreate, PortalDecision
from app.services import approval_portal, audit_service
from app.services.approval_service import recompute_output_status
from app.services.storage_service import signed_url

router = APIRouter(tags=["approval-portal"])


def _required_levels(db: Session, output: GenerationOutput) -> list[str]:
    generation = db.get(Generation, output.generation_id)
    check = db.get(ComplianceCheck, generation.compliance_check_id) if generation else None
    return list(check.required_approvals or []) if check else []


def _request_out(ar: ApprovalRequest) -> dict:
    return {
        "id": str(ar.id),
        "level": ar.level,
        "status": ar.status,
        "contact_name": ar.contact_name,
        "contact_email": ar.contact_email,
        "expires_at": ar.expires_at.isoformat() if ar.expires_at else None,
        "created_at": ar.created_at.isoformat() if ar.created_at else None,
        "decided_at": ar.decided_at.isoformat() if ar.decided_at else None,
    }


# ---- Authenticated: issue / list (internal legal-level user) ----

@router.post("/outputs/{output_id}/approval-requests")
def issue_request(
    output_id: str,
    body: ApprovalRequestCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.APPROVE_LEGAL))],
):
    output = db.get(GenerationOutput, output_id)
    if not output:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画像が見つかりません。")
    if output.output_status in ("approved", "delivered"):
        raise HTTPException(status.HTTP_409_CONFLICT, "既に承認/納品済みの画像です。")
    # Only issue a link for a level this output's compliance check actually
    # requires — an unrequested external sign-off has no meaning (docs/05 §9).
    if body.level not in _required_levels(db, output):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"この案件は'{body.level}'承認を必要としません。")

    ar, token = approval_portal.issue(
        db, output_id=output_id, level=body.level,
        contact_name=body.contact_name, contact_email=body.contact_email,
        expires_in_days=body.expires_in_days, created_by=user.id,
    )
    audit_service.record(db, user_id=user.id, action_type="create",
                         target_type="approval_request", target_id=str(ar.id),
                         after={"level": ar.level, "output_id": output_id})
    db.commit()
    return ok({
        "id": str(ar.id),
        "token": token,  # returned ONCE — embedded in the portal link
        "portal_path": f"/portal/approvals/{token}",
        "level": ar.level,
        "expires_at": ar.expires_at.isoformat(),
    })


@router.get("/outputs/{output_id}/approval-requests")
def list_requests(
    output_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.REVIEW))],
):
    rows = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.output_id == output_id)
        .order_by(ApprovalRequest.created_at.desc())
    ).all()
    return ok([_request_out(r) for r in rows])


# ---- Public: token-scoped portal (NO auth) ----

@router.get("/portal/approvals/{token}")
def portal_view(token: str, db: Annotated[Session, Depends(get_db)]):
    ar = approval_portal.resolve(db, token)
    if not ar:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "リンクが無効です。")
    output = db.get(GenerationOutput, ar.output_id)
    generation = db.get(Generation, output.generation_id) if output else None
    project = db.get(Project, generation.project_id) if generation else None

    open_ = approval_portal.is_open(ar)
    preview = None
    if open_ and output and not output.file_path.startswith("mock://"):
        preview = signed_url(output.file_path)
        audit_service.record(db, user_id=None, action_type="view",
                             target_type="approval_request", target_id=str(ar.id),
                             after={"purpose": "portal_view"})
        db.commit()
    return ok({
        "level": ar.level,
        "output_id": str(ar.output_id),
        "preview_url": preview,
        "project_name": project.project_name if project else "",
        "status": ar.status,
        "expires_at": ar.expires_at.isoformat() if ar.expires_at else None,
        "already_decided": not open_,
    })


@router.post("/portal/approvals/{token}")
def portal_decide(token: str, body: PortalDecision, db: Annotated[Session, Depends(get_db)]):
    ar = approval_portal.resolve(db, token)
    if not ar:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "リンクが無効です。")
    if not approval_portal.is_open(ar):
        raise HTTPException(status.HTTP_409_CONFLICT, "このリンクは既に使用済みか期限切れです。")

    output = db.get(GenerationOutput, ar.output_id)
    if not output:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画像が見つかりません。")

    who = (body.approver_name or ar.contact_name or "external").strip()
    comment = f"[外部承認:{who}] {body.comment or ''}".strip()
    # External approval: approver_id is NULL by design; identity is captured in the
    # request row + comment. Flows through the same completeness gate.
    db.add(Approval(output_id=str(ar.output_id), approver_id=None,
                    approval_level=ar.level, approval_status=body.decision,
                    approval_comment=comment))
    ar.status = "decided"
    ar.decision = body.decision
    ar.decision_comment = body.comment
    ar.approver_name = body.approver_name
    ar.decided_at = datetime.now(timezone.utc)
    db.flush()

    output_status, _required, missing = recompute_output_status(db, output)
    audit_service.record(db, user_id=None, action_type="approve",
                         target_type="output", target_id=str(ar.output_id),
                         after={"level": ar.level, "status": body.decision,
                                "external": True, "missing": missing})
    db.commit()
    return ok({"output_status": output_status, "recorded": True})
