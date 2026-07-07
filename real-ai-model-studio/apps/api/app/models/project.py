import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_name: Mapped[str] = mapped_column(String(255))
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    project_status: Mapped[str] = mapped_column(String(16), default="draft")
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectRequirement(Base):
    __tablename__ = "project_requirements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    media: Mapped[list] = mapped_column(JSONB, default=list)
    region: Mapped[list] = mapped_column(JSONB, default=list)
    usage_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    usage_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    output_type: Mapped[str] = mapped_column(String(16), default="image")
    scene_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outfit_type: Mapped[str] = mapped_column(String(32), default="normal")
    exposure_level: Mapped[int] = mapped_column(Integer, default=0)
    secondary_use: Mapped[bool] = mapped_column(Boolean, default=False)
    overseas: Mapped[bool] = mapped_column(Boolean, default=False)
    pose_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    expression_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    background_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_files: Mapped[list] = mapped_column(JSONB, default=list)
    client_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectMember(Base):
    """Which users may act on a project (data-scoped auth, migration 0004).

    admin/legal are system-wide and are NOT gated by this table; for everyone
    else, access = owner OR a row here."""

    __tablename__ = "project_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role_in_project: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProjectModel(Base):
    __tablename__ = "project_models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"))
    usage_role: Mapped[str] = mapped_column(String(32), default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
