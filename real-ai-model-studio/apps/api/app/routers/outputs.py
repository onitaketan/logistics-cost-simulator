"""Outputs: selection, revision, review, approval, and gated download."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm, has_permission
from app.core.security import CurrentUser, CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import ComplianceCheck, Generation, GenerationOutput
from app.models.workflow import Approval, OutputReview
from app.schemas.common import ok
from app.schemas.dto import ApprovalCreate, OutputStatusUpdate, ReviewCreate, ReviseRequest
from app.services import audit_service
from app.services.approval_service import ApprovalRecord, evaluate_approvals
from app.services.storage_service import signed_url

# which RBAC permission each approval level demands
_LEVEL_PERM = {
    "internal": Perm.APPROVE_INTERNAL,
    "legal": Perm.APPROVE_LEGAL,
    "agency": Perm.APPROVE_LEGAL,   # agency/person sign-off recorded by legal in MVP (no external portal yet)
    "person": Perm.APPROVE_LEGAL,
    "admin": Perm.APPROVE_ADMIN,
}

router = APIRouter(prefix="/outputs", tags=["outputs"])


def _get_output(db: Session, output_id: str) -> GenerationOutput:
    o = db.get(GenerationOutput, output_id)
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画像が見つかりません。")
    return o


def require_review_or_view(user: CurrentUserDep) -> CurrentUser:
    """Read access to reviews/approvals: reviewers or anyone who can view models."""
    if has_permission(user.role, Perm.REVIEW) or has_permission(user.role, Perm.MODEL_VIEW):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"role '{user.role}' lacks permission '{Perm.REVIEW}' or '{Perm.MODEL_VIEW}'",
    )


@router.patch("/{output_id}/status")
def set_status(
    output_id: str,
    body: OutputStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.REVIEW))],
):
    o = _get_output(db, output_id)
    before = o.output_status
    o.output_status = body.output_status
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update", target_type="output",
                         target_id=output_id, before={"status": before}, after={"status": o.output_status})
    db.commit()
    return ok({"id": output_id, "output_status": o.output_status})


@router.post("/{output_id}/revise")
def revise(
    output_id: str,
    body: ReviseRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.GENERATE))],
):
    _get_output(db, output_id)
    # Revision re-uses the parent generation's compliance check; a new generation
    # row is created by the generation flow. Here we only record intent (scaffold).
    audit_service.record(db, user_id=user.id, action_type="generate", target_type="output",
                         target_id=output_id, after={"revision": body.revision_prompt})
    db.commit()
    return ok({"queued": True, "note": "revision uses parent compliance check"})


@router.post("/{output_id}/reviews")
def add_review(
    output_id: str,
    body: ReviewCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.REVIEW))],
):
    _get_output(db, output_id)
    r = OutputReview(output_id=output_id, reviewer_id=user.id, **body.model_dump())
    db.add(r)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="review", target_type="output",
                         target_id=output_id, after={"status": body.status})
    db.commit()
    return ok({"id": str(r.id)})


@router.post("/{output_id}/approvals")
def add_approval(
    output_id: str,
    body: ApprovalCreate,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUserDep,
):
    # Per-level authorization: legal-level approvals require the legal permission, etc.
    needed = _LEVEL_PERM.get(body.approval_level, Perm.APPROVE_INTERNAL)
    if not has_permission(user.role, needed):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"'{body.approval_level}' 承認の権限がありません。")

    o = _get_output(db, output_id)
    a = Approval(output_id=output_id, approver_id=user.id, **body.model_dump())
    db.add(a)
    db.flush()

    # Resolve the approval levels required by this output's compliance check.
    generation = db.get(Generation, o.generation_id)
    check = db.get(ComplianceCheck, generation.compliance_check_id) if generation else None
    required = list(check.required_approvals or []) if check else []

    records = [
        ApprovalRecord(level=r.approval_level, status=r.approval_status)
        for r in db.scalars(select(Approval).where(Approval.output_id == output_id)).all()
    ]
    fully_approved, missing = evaluate_approvals(required, records)

    if any(r.status in ("rejected", "revoked") for r in records):
        o.output_status = "rejected"
    elif fully_approved:
        o.output_status = "approved"
    # else: stays candidate/selected — not yet fully approved
    db.flush()

    audit_service.record(db, user_id=user.id, action_type="approve", target_type="output",
                         target_id=output_id,
                         after={"level": body.approval_level, "status": body.approval_status,
                                "fully_approved": fully_approved, "missing": missing})
    db.commit()
    return ok({"id": str(a.id), "output_status": o.output_status,
               "required_approvals": required, "missing_approvals": missing})


@router.get("/{output_id}/reviews")
def list_reviews(
    output_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_review_or_view)],
):
    rows = db.scalars(
        select(OutputReview)
        .where(OutputReview.output_id == output_id)
        .order_by(OutputReview.created_at.asc())
    ).all()
    return ok([
        {
            "id": str(r.id),
            "review_type": r.review_type,
            "status": r.status,
            "comment": r.comment,
            "reviewer_id": str(r.reviewer_id) if r.reviewer_id else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ])


@router.get("/{output_id}/approvals")
def list_approvals(
    output_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_review_or_view)],
):
    rows = db.scalars(
        select(Approval)
        .where(Approval.output_id == output_id)
        .order_by(Approval.approved_at.asc())
    ).all()
    return ok([
        {
            "id": str(a.id),
            "approval_level": a.approval_level,
            "approval_status": a.approval_status,
            "approval_comment": a.approval_comment,
            "approver_id": str(a.approver_id) if a.approver_id else None,
            "approved_at": a.approved_at.isoformat() if a.approved_at else None,
        }
        for a in rows
    ])


@router.get("/{output_id}/download")
def download(
    output_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.DOWNLOAD))],
):
    o = _get_output(db, output_id)
    if o.output_status not in ("approved", "delivered"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "未承認の画像はダウンロードできません。")
    url = signed_url(o.file_path)
    audit_service.record(db, user_id=user.id, action_type="download", target_type="output",
                         target_id=output_id, after={"file_hash": o.file_hash})
    db.commit()
    return ok({"download_url": url, "expires_in": "short-lived"})
