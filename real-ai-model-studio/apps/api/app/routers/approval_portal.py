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

from app.core.access import assert_project_access
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


def _assert_output_project_access(db: Session, user, output: GenerationOutput) -> None:
    generation = db.get(Generation, output.generation_id)
    if generation is not None:
        assert_project_access(db, user, generation.project_id)


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
    _assert_output_project_access(db, user, output)
    # A link only makes sense for an output still open for approval. Refuse when
    # already approved/delivered OR reviewer-rejected — otherwise an external
    # 'approved' could resurrect a rejected asset (recompute has no rejected
    # Approval row to block on).
    if output.output_status not in ("candidate", "selected"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "この画像は承認受付状態ではありません。")
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
    output = db.get(GenerationOutput, output_id)
    if not output:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画像が見つかりません。")
    _assert_output_project_access(db, user, output)
    rows = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.output_id == output_id)
        .order_by(ApprovalRequest.created_at.desc())
    ).all()
    return ok([_request_out(r) for r in rows])


@router.post("/outputs/{output_id}/approval-requests/{request_id}/revoke")
def revoke_request(
    output_id: str,
    request_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.APPROVE_LEGAL))],
):
    """Kill a still-pending link (mis-issued / leaked / wrong recipient) before it
    expires. A decided link cannot be revoked (the decision already stands)."""
    ar = db.get(ApprovalRequest, request_id)
    if not ar or str(ar.output_id) != str(output_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "承認リンクが見つかりません。")
    output = db.get(GenerationOutput, ar.output_id)
    if output is not None:
        _assert_output_project_access(db, user, output)
    if ar.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "決定済み/失効済みのリンクは取り消せません。")
    ar.status = "revoked"
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update",
                         target_type="approval_request", target_id=request_id,
                         after={"status": "revoked"})
    db.commit()
    return ok({"id": request_id, "revoked": True})


# ---- Public: token-scoped portal (NO auth) ----

@router.get("/portal/approvals/{token}")
def portal_view(token: str, db: Annotated[Session, Depends(get_db)]):
    ar = approval_portal.resolve(db, token)
    if not ar:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "リンクが無効です。")
    open_ = approval_portal.is_open(ar)

    # Record every resolved-token view (open, closed, expired, or mock) — all
    # access to the person's image/context must be auditable (CLAUDE.md #5).
    audit_service.record(db, user_id=None, action_type="view",
                         target_type="approval_request", target_id=str(ar.id),
                         after={"purpose": "portal_view", "open": open_})
    db.commit()

    # A closed/expired link discloses nothing beyond that it is closed — no
    # project name, output id, or preview (defence in depth; the token holder
    # already had it, but a dead link should not keep leaking internal naming).
    if not open_:
        return ok({"level": None, "output_id": None, "preview_url": None,
                   "project_name": "", "status": ar.status,
                   "expires_at": ar.expires_at.isoformat() if ar.expires_at else None,
                   "already_decided": True})

    output = db.get(GenerationOutput, ar.output_id)
    generation = db.get(Generation, output.generation_id) if output else None
    project = db.get(Project, generation.project_id) if generation else None
    preview = None
    if output and not output.file_path.startswith("mock://"):
        preview = signed_url(output.file_path)
    return ok({
        "level": ar.level,
        "output_id": str(ar.output_id),
        "preview_url": preview,
        "project_name": project.project_name if project else "",
        "status": ar.status,
        "expires_at": ar.expires_at.isoformat() if ar.expires_at else None,
        "already_decided": False,
    })


@router.post("/portal/approvals/{token}")
def portal_decide(token: str, body: PortalDecision, db: Annotated[Session, Depends(get_db)]):
    ar = approval_portal.resolve(db, token)
    if not ar:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "リンクが無効です。")

    # Serialize ALL approval writes on this output so single-use, the state
    # machine, and the separation-of-duties check are race-free (row lock).
    output = db.execute(
        select(GenerationOutput).where(GenerationOutput.id == ar.output_id).with_for_update()
    ).scalar_one_or_none()
    if not output:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "画像が見つかりません。")
    db.refresh(ar)  # fresh status under the lock (a peer decision may have landed)

    if not approval_portal.is_open(ar):
        raise HTTPException(status.HTTP_409_CONFLICT, "このリンクは既に使用済みか期限切れです。")
    if output.output_status not in ("candidate", "selected"):
        raise HTTPException(status.HTTP_409_CONFLICT, "この画像は承認受付状態ではありません。")

    # Separation of duties (docs/05 §9): the external approval is accountable to
    # the internal user who issued the link (created_by). Refuse if that same
    # internal actor is already responsible for a DIFFERENT level on this output
    # — whether recorded in-system or via another external link. This prevents a
    # single internal user from single-handedly satisfying a multi-party gate.
    if ar.created_by is not None:
        others = db.scalars(select(Approval).where(Approval.output_id == ar.output_id)).all()
        if any(str(a.approver_id) == str(ar.created_by) and a.approval_level != ar.level
               for a in others):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "同一の発行者が複数の承認レベルを担うことはできません（職務分掌）。",
            )

    who = (body.approver_name or ar.contact_name or "external").strip()
    comment = f"[外部承認:{who}] {body.comment or ''}".strip()
    # approver_id = the accountable internal issuer (NOT NULL) so the shared SoD
    # rule sees external rows too; the external human's name is in approver_name.
    db.add(Approval(output_id=str(ar.output_id), approver_id=ar.created_by,
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
