import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Model(Base):
    __tablename__ = "models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage_name: Mapped[str] = mapped_column(String(128))
    real_name: Mapped[str] = mapped_column(String(128))
    agency_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agency_contact_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agency_contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    adult_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    adult_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    adult_verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="available")
    profile_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelContract(Base):
    __tablename__ = "model_contracts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"))
    contract_number: Mapped[str] = mapped_column(String(64))
    contract_type: Mapped[str] = mapped_column(String(32))
    contract_start: Mapped[date] = mapped_column(Date)
    contract_end: Mapped[date] = mapped_column(Date)
    renewal_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    contract_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    agency_approval_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_generation_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_training_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    synthetic_identity_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    post_contract_use_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    deletion_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelPermission(Base):
    __tablename__ = "model_permissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"))
    contract_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_contracts.id"))
    media_scope: Mapped[list] = mapped_column(JSONB, default=list)
    region_scope: Mapped[list] = mapped_column(JSONB, default=list)
    product_scope: Mapped[list] = mapped_column(JSONB, default=list)
    prohibited_product_scope: Mapped[list] = mapped_column(JSONB, default=list)
    swimwear_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    underwear_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    bath_allowed: Mapped[str] = mapped_column(String(12), default="no")
    exposure_level_max: Mapped[int] = mapped_column(Integer, default=0)
    face_edit_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    body_edit_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    hair_edit_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    makeup_edit_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    age_appearance_change_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    video_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    secondary_use_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    overseas_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_required_level: Mapped[str] = mapped_column(String(16), default="legal")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelAsset(Base):
    __tablename__ = "model_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id"))
    asset_type: Mapped[str] = mapped_column(String(16))
    file_path: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_hash: Mapped[str] = mapped_column(String(128))
    usage_type: Mapped[str] = mapped_column(String(16))
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    photographer_right_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
