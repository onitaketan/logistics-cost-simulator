import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutputReview(Base):
    __tablename__ = "output_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    output_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generation_outputs.id"))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    output_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generation_outputs.id"))
    approver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approval_level: Mapped[str] = mapped_column(String(16))
    approval_status: Mapped[str] = mapped_column(String(16))
    approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovalRequest(Base):
    """External approval portal request (P2-001/P2-002). Only the token hash is
    stored; the raw token lives only in the issued link."""

    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    output_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generation_outputs.id"))
    level: Mapped[str] = mapped_column(String(16))            # agency | person
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    contact_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|decided|revoked
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    output_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generation_outputs.id"))
    delivered_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    usage_media: Mapped[list] = mapped_column(JSONB, default=list)
    usage_region: Mapped[list] = mapped_column(JSONB, default=list)
    usage_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    usage_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    delivered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
