"""Prompt template management (P1-004, docs/06 §6).

Reusable prompt scaffolds that Creative selects at generation time to seed the
prompt/negative-prompt. Templates are screened against the prohibited-term
dictionary on create/update — a stored template must never carry a banned
instruction that would later be sent to an engine (docs/05 §7). Soft-disable via
is_active rather than hard delete, so historical generations keep a resolvable
prompt_template_id.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import PromptTemplate
from app.schemas.common import ok
from app.schemas.dto import PromptTemplateCreate, PromptTemplateUpdate
from app.services import audit_service
from app.services.prompt_filter import screen

router = APIRouter(prefix="/prompt-templates", tags=["prompt-templates"])


def _out(t: PromptTemplate) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "body": t.body,
        "negative_body": t.negative_body,
        "tags": list(t.tags or []),
        "is_active": t.is_active,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _reject_prohibited(*texts: str | None) -> None:
    hits: set[str] = set()
    for text_ in texts:
        hits |= {f for f in screen(text_) if f.startswith("prohibited:")}
    if hits:
        terms = ", ".join(sorted(h.split(":", 1)[1] for h in hits))
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"禁止語句を含むテンプレートは登録できません（{terms}）。",
        )


@router.get("")
def list_templates(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_VIEW))],
    active_only: bool = Query(True),
):
    stmt = select(PromptTemplate)
    if active_only:
        stmt = stmt.where(PromptTemplate.is_active.is_(True))
    stmt = stmt.order_by(PromptTemplate.created_at.desc())
    return ok([_out(t) for t in db.scalars(stmt).all()])


@router.post("")
def create_template(
    body: PromptTemplateCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.GENERATE))],
):
    _reject_prohibited(body.body, body.negative_body)
    t = PromptTemplate(**body.model_dump())
    db.add(t)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="create",
                         target_type="prompt_template", target_id=str(t.id),
                         after={"name": t.name})
    db.commit()
    return ok(_out(t))


@router.get("/{template_id}")
def get_template(
    template_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_VIEW))],
):
    t = db.get(PromptTemplate, template_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "テンプレートが見つかりません。")
    return ok(_out(t))


@router.patch("/{template_id}")
def update_template(
    template_id: str,
    body: PromptTemplateUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.GENERATE))],
):
    t = db.get(PromptTemplate, template_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "テンプレートが見つかりません。")
    changes = body.model_dump(exclude_unset=True)
    # Re-screen the resulting body/negative even if only one field changed.
    _reject_prohibited(changes.get("body", t.body), changes.get("negative_body", t.negative_body))
    for k, v in changes.items():
        setattr(t, k, v)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update",
                         target_type="prompt_template", target_id=template_id,
                         after={"fields": sorted(changes.keys())})
    db.commit()
    return ok(_out(t))


@router.delete("/{template_id}")
def disable_template(
    template_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.GENERATE))],
):
    """Soft-disable (is_active=false) so past generations keep a valid FK."""
    t = db.get(PromptTemplate, template_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "テンプレートが見つかりません。")
    t.is_active = False
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="delete",
                         target_type="prompt_template", target_id=template_id,
                         before={"name": t.name})
    db.commit()
    return ok({"id": template_id, "disabled": True})
