"""Outputs: selection, revision, review, approval, and gated download."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import assert_project_access
from app.core.rbac import Perm, has_permission
from app.core.security import CurrentUser, CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import ComplianceCheck, Generation, GenerationOutput
from app.models.workflow import Approval, OutputReview
from app.schemas.common import ok
from app.schemas.dto import ApprovalCreate, OutputStatusUpdate, ReviewCreate, ReviseRequest
from app.services import audit_service, generation_service
from app.services.approval_service import recompute_output_status as evaluate_approvals_status
from app.services.storage_service import signed_url

# which RBAC permission each approval level demands
_LEVEL_PERM = {
    "internal": Perm.APPROVE_INTERNAL,
    "legal": Perm.APPROVE_LEGAL,
    # agency/person can ALSO be recorded externally via the approval portal
    # (routers/approval_portal.py, approver_id NULL). This in-system path lets a
    # legal-permission user record them directly when a portal round-trip isn't used.
    "agency": Perm.APPROVE_LEGAL,
    "person": Perm.APPROVE_LEGAL,
    "admin": Perm.APPROVE_ADMIN,
}

router = APIRouter(prefix="/outputs", tags=["outputs"])


def _get_output(db: Session, output_id: str) -> GenerationOutput:
    o = db.get(GenerationOutput, output_id)
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画像が見つかりません。")
    return o


def _assert_output_access(db: Session, user, o: GenerationOutput) -> None:
    """Data scope: the caller must have access to the output's project."""
    generation = db.get(Generation, o.generation_id)
    if generation is not None:
        assert_project_access(db, user, generation.project_id)


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
    _assert_output_access(db, user, o)
    before = o.output_status
    # Selection endpoint must not walk back a terminal approval/delivery state.
    # 'approved' is reached only through the multi-level approval gate and
    # 'delivered' only through delivery; regressing them here would silently
    # invalidate that chain and let an already-delivered asset re-enter review
    # without a fresh approval (docs/05 §9).
    if before in ("approved", "delivered"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "承認済み/納品済みの画像はこの操作で選定ステータスに戻せません。",
        )
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
    """Revision generation (P1-006): a NEW generation job that reuses the parent's
    compliance check. All three gates still apply — the request-time gate here,
    the DB trigger at INSERT, and the worker's execution-time re-validation — so
    a revision can never outlive a revoked/expired permission."""
    from app.services.generation_service import ComplianceCheckRef

    o = _get_output(db, output_id)
    _assert_output_access(db, user, o)
    parent = db.get(Generation, o.generation_id)
    if parent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "元の生成ジョブが見つかりません。")

    check = db.get(ComplianceCheck, parent.compliance_check_id)
    ref = None
    if check:
        ref = ComplianceCheckRef(
            id=str(check.id), project_id=str(check.project_id),
            model_id=str(check.model_id), check_status=check.check_status,
        )
    # Raises GenerationBlocked -> app-level 422 envelope, same as /generations.
    generation_service.assert_generation_allowed(
        ref, project_id=str(parent.project_id), model_id=str(parent.model_id)
    )
    # Screen the revision prompt too — a revision must not smuggle in a prohibited
    # instruction the parent check never saw (docs/05 §7).
    generation_service.assert_prompt_clean(body.revision_prompt, parent.negative_prompt_text)

    params = dict(parent.generation_params or {})
    if body.target_area:
        params["revision_target_area"] = body.target_area
    params["revision_of_output"] = output_id

    revision = Generation(
        project_id=parent.project_id,
        model_id=parent.model_id,
        compliance_check_id=parent.compliance_check_id,
        ai_engine_id=parent.ai_engine_id,
        prompt_text=body.revision_prompt,
        negative_prompt_text=parent.negative_prompt_text,
        generation_params=params,
        output_count=int(params.get("output_count", 1)),
        status="queued",
        generated_by=user.id,
    )
    db.add(revision)
    # Commit BEFORE enqueue (DB trigger validates at INSERT; the eager worker
    # opens its own session and must see the row).
    db.commit()

    generation_service.enqueue_generation(revision.id)
    db.refresh(revision)

    audit_service.record(db, user_id=user.id, action_type="generate", target_type="output",
                         target_id=output_id,
                         after={"revision_generation_id": str(revision.id),
                                "revision_prompt": body.revision_prompt})
    db.commit()
    return ok({"generation_id": str(revision.id), "status": revision.status})


@router.post("/{output_id}/reviews")
def add_review(
    output_id: str,
    body: ReviewCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.REVIEW))],
):
    _assert_output_access(db, user, _get_output(db, output_id))
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
    _assert_output_access(db, user, o)

    # Separation of duties (docs/05 §9): the required approval levels (legal /
    # agency / person …) exist so that DISTINCT parties sign off. Because several
    # levels share one RBAC permission in the MVP, a single user could otherwise
    # satisfy multiple levels alone and collapse the multi-party gate. Refuse an
    # approval when the same user has already recorded a *different* level on this
    # output.
    existing = db.scalars(
        select(Approval).where(Approval.output_id == output_id)
    ).all()
    conflict = next(
        (e for e in existing
         if str(e.approver_id) == str(user.id) and e.approval_level != body.approval_level),
        None,
    )
    if conflict is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "同一ユーザーが複数の承認レベルを兼任することはできません（職務分掌）。",
        )

    a = Approval(output_id=output_id, approver_id=user.id, **body.model_dump())
    db.add(a)
    db.flush()

    # Drive the shared completeness gate (same logic the external portal uses).
    output_status, required, missing = evaluate_approvals_status(db, o)

    audit_service.record(db, user_id=user.id, action_type="approve", target_type="output",
                         target_id=output_id,
                         after={"level": body.approval_level, "status": body.approval_status,
                                "fully_approved": not missing, "missing": missing})
    db.commit()
    return ok({"id": str(a.id), "output_status": output_status,
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


@router.get("/{output_id}/preview")
def preview(
    output_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.REVIEW))],
):
    """Short-lived signed URL so a reviewer can SEE a candidate image.

    Review必ずしも承認済みではない画像を目視確認する必要がある（docs/05 §10）ため、
    ダウンロード（承認後のみ）とは別に、閲覧専用の署名URLを発行する。ただし未承認画像の
    実体（本人の肖像）を閲覧できるのはレビュー権限者に限る — 単なる閲覧ロール(viewer)には
    許可しない（docs/06 §2）。アクセスは監査ログ(view)に記録される。
    """
    o = _get_output(db, output_id)
    _assert_output_access(db, user, o)
    if o.file_path.startswith("mock://"):
        # Mock engine outputs have no stored bytes — nothing to preview.
        return ok({"preview_url": None})
    url = signed_url(o.file_path)
    audit_service.record(db, user_id=user.id, action_type="view", target_type="output",
                         target_id=output_id, after={"purpose": "review_preview"})
    db.commit()
    return ok({"preview_url": url})


@router.get("/{output_id}/download")
def download(
    output_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.DOWNLOAD))],
):
    o = _get_output(db, output_id)
    _assert_output_access(db, user, o)
    if o.output_status not in ("approved", "delivered"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "未承認の画像はダウンロードできません。")
    url = signed_url(o.file_path)
    audit_service.record(db, user_id=user.id, action_type="download", target_type="output",
                         target_id=output_id, after={"file_hash": o.file_hash})
    db.commit()
    return ok({"download_url": url, "expires_in": "short-lived"})
