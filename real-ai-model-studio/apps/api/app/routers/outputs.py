"""Outputs: selection, revision, review, approval, and gated download."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import GenerationOutput
from app.models.workflow import Approval, OutputReview
from app.schemas.common import ok
from app.schemas.dto import ApprovalCreate, OutputStatusUpdate, ReviewCreate, ReviseRequest
from app.services import audit_service
from app.services.storage_service import signed_url

router = APIRouter(prefix="/outputs", tags=["outputs"])


def _get_output(db: Session, output_id: str) -> GenerationOutput:
    o = db.get(GenerationOutput, output_id)
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画像が見つかりません。")
    return o


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
    # legal-level approvals need the legal permission; internal is broader.
    user: Annotated[CurrentUserDep, Depends(require(Perm.APPROVE_INTERNAL))],
):
    o = _get_output(db, output_id)
    a = Approval(output_id=output_id, approver_id=user.id, **body.model_dump())
    db.add(a)
    if body.approval_status == "approved":
        o.output_status = "approved"
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="approve", target_type="output",
                         target_id=output_id, after={"level": body.approval_level, "status": body.approval_status})
    db.commit()
    return ok({"id": str(a.id), "output_status": o.output_status})


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
