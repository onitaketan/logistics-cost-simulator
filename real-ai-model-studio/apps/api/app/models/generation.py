import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ComplianceCheck(Base):
    __tablename__ = "compliance_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"))
    check_status: Mapped[str] = mapped_column(String(16))
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    matched_permissions: Mapped[dict] = mapped_column(JSONB, default=dict)
    violations: Mapped[list] = mapped_column(JSONB, default=list)
    required_approvals: Mapped[list] = mapped_column(JSONB, default=list)
    check_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_version: Mapped[str] = mapped_column(String(32), default="v1")
    checked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIEngine(Base):
    __tablename__ = "ai_engines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64))
    adapter_key: Mapped[str] = mapped_column(String(32))
    training_capable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    negative_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"))
    # HARD GATE: not nullable — a generation cannot exist without a compliance check.
    compliance_check_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("compliance_checks.id"))
    ai_engine_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_engines.id"), nullable=True)
    prompt_text: Mapped[str] = mapped_column(Text)
    negative_prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_templates.id"), nullable=True)
    generation_params: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    generated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GenerationOutput(Base):
    __tablename__ = "generation_outputs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    generation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generations.id"))
    file_path: Mapped[str] = mapped_column(Text)
    file_hash: Mapped[str] = mapped_column(String(128))
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_status: Mapped[str] = mapped_column(String(16), default="candidate")
    visual_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    face_consistency_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watermark_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    c2pa_metadata_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
