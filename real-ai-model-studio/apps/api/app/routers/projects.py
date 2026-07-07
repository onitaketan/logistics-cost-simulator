from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import accessible_project_ids, assert_project_access, can_access_project, is_global
from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.model import Model
from app.models.project import Project, ProjectMember, ProjectModel, ProjectRequirement
from app.models.user import User
from app.schemas.common import ok
from app.schemas.dto import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    ModelAssign,
    ProjectCreate,
    ProjectMemberCreate,
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
    stmt = select(Project).where(Project.deleted_at.is_(None))
    # Data scope: non-global roles see only projects they own or belong to.
    allowed = accessible_project_ids(db, user)
    if allowed is not None:
        if not allowed:
            return ok([])
        stmt = stmt.where(Project.id.in_(allowed))
    stmt = stmt.limit(limit).offset(offset)
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
    # The creator is a member of their own project (so non-global creators keep
    # access via the same membership path).
    db.add(ProjectMember(project_id=p.id, user_id=user.id, role_in_project="owner"))
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
    assert_project_access(db, user, project_id)
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
    assert_project_access(db, user, project_id)
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
    assert_project_access(db, user, project_id)
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
    proj = db.get(Project, project_id)
    if not proj or proj.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "案件が見つかりません。")
    assert_project_access(db, user, project_id)
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
    proj = db.get(Project, project_id)
    if not proj or proj.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "案件が見つかりません。")
    assert_project_access(db, user, project_id)
    model = db.get(Model, body.model_id)
    if not model or model.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "モデルが見つかりません。")
    pm = ProjectModel(project_id=project_id, model_id=body.model_id, usage_role=body.usage_role)
    db.add(pm)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update",
                         target_type="project", target_id=project_id,
                         after={"assigned_model": body.model_id})
    db.commit()
    return ok({"id": str(pm.id)})


# ---- Project membership (data-scoped access, migration 0004) ----

def _may_manage_members(db: Session, user, project: Project) -> bool:
    """Who can change a project's team: a global role (admin/legal) or the owner."""
    if is_global(user.role):
        return True
    return project.owner_user_id is not None and str(project.owner_user_id) == str(user.id)


@router.get("/{project_id}/members")
def list_members(
    project_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_VIEW))],
):
    proj = db.get(Project, project_id)
    if not proj or proj.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "案件が見つかりません。")
    assert_project_access(db, user, project_id)
    rows = db.scalars(
        select(ProjectMember).where(ProjectMember.project_id == project_id)
    ).all()
    # join user display fields for the UI
    out = []
    for m in rows:
        u = db.get(User, m.user_id)
        out.append({
            "id": str(m.id), "user_id": str(m.user_id),
            "role_in_project": m.role_in_project,
            "name": u.name if u else None, "email": u.email if u else None,
            "is_owner": proj.owner_user_id is not None and str(proj.owner_user_id) == str(m.user_id),
        })
    return ok(out)


@router.post("/{project_id}/members")
def add_member(
    project_id: str,
    body: ProjectMemberCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_EDIT))],
):
    proj = db.get(Project, project_id)
    if not proj or proj.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "案件が見つかりません。")
    if not _may_manage_members(db, user, proj):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "メンバー管理の権限がありません（オーナーまたは管理者のみ）。")
    if body.user_id:
        target = db.get(User, body.user_id)
    else:
        target = db.scalar(select(User).where(User.email == body.email))
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ユーザーが見つかりません。")
    existing = db.scalar(select(ProjectMember).where(
        ProjectMember.project_id == project_id, ProjectMember.user_id == target.id))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "既にメンバーです。")
    m = ProjectMember(project_id=project_id, user_id=target.id,
                      role_in_project=body.role_in_project)
    db.add(m)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update",
                         target_type="project", target_id=project_id,
                         after={"added_member": str(target.id)})
    db.commit()
    return ok({"id": str(m.id), "user_id": str(target.id)})


@router.delete("/{project_id}/members/{user_id}")
def remove_member(
    project_id: str,
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.PROJECT_EDIT))],
):
    proj = db.get(Project, project_id)
    if not proj or proj.deleted_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "案件が見つかりません。")
    if not _may_manage_members(db, user, proj):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "メンバー管理の権限がありません（オーナーまたは管理者のみ）。")
    if proj.owner_user_id is not None and str(proj.owner_user_id) == str(user_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "オーナーはメンバーから外せません。")
    m = db.scalar(select(ProjectMember).where(
        ProjectMember.project_id == project_id, ProjectMember.user_id == user_id))
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "メンバーが見つかりません。")
    db.delete(m)
    db.flush()
    audit_service.record(db, user_id=user.id, action_type="update",
                         target_type="project", target_id=project_id,
                         after={"removed_member": user_id})
    db.commit()
    return ok({"removed": True, "user_id": user_id})
