from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.project import Project, ProjectModel, ProjectRequirement
from app.schemas.common import ok
from app.schemas.dto import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    ModelAssign,
    ProjectCreate,
    ProjectUpdate,
    RequirementCreate,
)
from app.services import audit_service

router = APIRouter(prefix="/projects", tags=["projects"])


def _out(p: Project) -> dict:
    return {"id": str(p.id), "project_name": p.project_name, "client_name": p.client_name,
            "product_category": p.product_category, "project_status": p.project_status,
            "risk_level": p.risk_level, "deadline": str(p.deadline) if p.deadline else None}


@router.get("")
def list_projects(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_VIEW))],
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    stmt = select(Project).where(Project.deleted_at.is_(None)).limit(limit).offset(offset)
    rows = db.scalars(stmt).all()
    return ok([_out(p) for p in rows])


@router.post("")
def create_project(
    body: ProjectCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_EDIT))],
):
    p = Project(owner_user_id=user.id, **body.model_dump())
    db.add(p)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="create",
                         target_type="project", target_id=str(p.id), after=_out(p))
    db.commit()
    return ok(_out(p))


@router.get("/{project_id}")
def get_project(
    project_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_VIEW))],
):
    p = db.get(Project, project_id)
    if not p or p.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "案件が見つかりません。")
    return ok(_out(p))


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_EDIT))],
):
    p = db.get(Project, project_id)
    if not p or p.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "案件が見つかりません。")
    before = _out(p)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update",
                         target_type="project", target_id=project_id,
                         before=before, after=_out(p))
    db.commit()
    return ok(_out(p))


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_EDIT))],
):
    """Soft-delete a project (CLAUDE.md: 削除は原則 soft delete)."""
    p = db.get(Project, project_id)
    if not p or p.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "案件が見つかりません。")
    p.deleted_at = datetime.now(timezone.utc)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="delete",
                         target_type="project", target_id=project_id,
                         before={"project_name": p.project_name})
    db.commit()
    return ok({"id": project_id, "deleted": True})


@router.post("/{project_id}/requirements")
def set_requirements(
    project_id: str,
    body: RequirementCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_EDIT))],
):
    if not db.get(Project, project_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "案件が見つかりません。")
    r = ProjectRequirement(project_id=project_id, **body.model_dump())
    db.add(r)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="create",
                         target_type="project", target_id=project_id, after={"requirement_id": str(r.id)})
    db.commit()
    return ok({"id": str(r.id)})


@router.post("/{project_id}/models")
def assign_model(
    project_id: str,
    body: ModelAssign,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_EDIT))],
):
    pm = ProjectModel(project_id=project_id, model_id=body.model_id, usage_role=body.usage_role)
    db.add(pm)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update",
                         target_type="project", target_id=project_id,
                         after={"assigned_model": body.model_id})
    db.commit()
    return ok({"id": str(pm.id)})
