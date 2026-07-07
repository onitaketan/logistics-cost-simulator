"""Project-scoped data authorization (migration 0004).

RBAC (rbac.py) decides WHAT capability an action needs; this decides WHICH
projects a user may act on. `admin` and `legal` are governance/compliance roles
with system-wide visibility and are never gated here. Everyone else may act only
on projects they OWN or are a MEMBER of.

Enforcement is defense-in-depth alongside RBAC: a route first requires the
capability (e.g. GENERATE), then asserts project access.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project, ProjectMember

# System-wide roles: legal/compliance oversight must see every project, and
# admin operates the whole system. They bypass project membership.
GLOBAL_ROLES = {"admin", "legal"}


def is_global(role: str) -> bool:
    return role in GLOBAL_ROLES


def can_access_project(db: Session, user, project_id) -> bool:
    if is_global(user.role):
        return True
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        return False
    if project.owner_user_id is not None and str(project.owner_user_id) == str(user.id):
        return True
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
    )
    return member is not None


def assert_project_access(db: Session, user, project_id) -> None:
    if not can_access_project(db, user, project_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "この案件へのアクセス権がありません。"
        )


def accessible_project_ids(db: Session, user) -> set[str] | None:
    """Return the set of project ids the user may see, or None meaning ALL
    (global roles). Used to filter list endpoints."""
    if is_global(user.role):
        return None
    owned = db.scalars(
        select(Project.id).where(
            Project.owner_user_id == user.id, Project.deleted_at.is_(None)
        )
    ).all()
    # Join projects so soft-deleted ones are excluded here too — otherwise a
    # member would keep seeing a deleted project's generations/deliveries via the
    # list endpoints that trust this set directly (owned branch already filters).
    member_of = db.scalars(
        select(ProjectMember.project_id)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(ProjectMember.user_id == user.id, Project.deleted_at.is_(None))
    ).all()
    return {str(x) for x in owned} | {str(x) for x in member_of}
