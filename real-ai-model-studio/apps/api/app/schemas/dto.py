"""Request/response DTOs for the MVP API surface (docs/03_api_spec.md).

Kept in one module for the scaffold; split per-domain as the surface grows.

Validation philosophy (see CLAUDE.md): fail-closed. Unknown / malformed input is
rejected here with a clear Japanese message rather than silently accepted. These
DTOs only tighten *input shape*; compliance decisions live in
services/compliance_engine.py and are never made here.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# ---- Shared enums (fixed value sets; keep in sync with docs/03_api_spec.md) ----
UserRole = Literal["admin", "legal", "sales", "creative", "approver", "viewer"]
UserStatus = Literal["active", "suspended"]
ContractType = Literal["base", "individual", "additional_consent"]
BathAllowed = Literal["yes", "no", "conditional"]
ApprovalRequiredLevel = Literal["internal", "legal", "agency", "person"]
OutputType = Literal["image", "video"]
ApprovalLevel = Literal["internal", "legal", "agency", "person", "admin"]
ApprovalStatus = Literal["approved", "conditional", "rejected", "revoked"]
OutputStatus = Literal["candidate", "selected", "approved", "rejected", "delivered"]
ReviewStatus = Literal["approved", "conditional", "revise", "rejected"]

# ---- Pagination (task 3) ----
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def clamp_limit(limit: int) -> int:
    """Clamp a caller-supplied page size into the allowed 1..MAX_LIMIT range."""
    return max(1, min(limit, MAX_LIMIT))


def _reject_blank(v: str | None) -> str | None:
    """Reject whitespace-only required strings (min_length lets ' ' through)."""
    if v is not None and not v.strip():
        raise ValueError("必須項目です。空欄にはできません。")
    return v


# ---- Auth ----
class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    otp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- Users ----
class UserCreate(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole
    department: str | None = None

    _v_name = field_validator("name")(_reject_blank)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    role: UserRole | None = None
    status: UserStatus | None = None
    department: str | None = None
    # Admin password reset (hashed server-side; never echoed back or audited).
    password: str | None = Field(default=None, min_length=8)

    _v_name = field_validator("name")(_reject_blank)


# ---- Models ----
class ModelCreate(BaseModel):
    stage_name: str = Field(min_length=1)
    real_name: str = Field(min_length=1)
    agency_name: str | None = None
    agency_contact_name: str | None = None
    agency_contact_email: EmailStr | None = None
    birth_date: date | None = None
    adult_verified: bool = False
    notes: str | None = None

    _v_stage = field_validator("stage_name")(_reject_blank)
    _v_real = field_validator("real_name")(_reject_blank)


class ModelUpdate(BaseModel):
    stage_name: str | None = Field(default=None, min_length=1)
    agency_name: str | None = None
    status: str | None = None
    notes: str | None = None

    _v_stage = field_validator("stage_name")(_reject_blank)


class AdultVerify(BaseModel):
    adult_verified: bool = True


# ---- Contracts / permissions ----
class ContractCreate(BaseModel):
    contract_number: str = Field(min_length=1)
    contract_type: ContractType = "base"
    contract_start: date
    contract_end: date
    renewal_type: str | None = None
    ai_generation_allowed: bool = False
    ai_training_allowed: bool = False
    synthetic_identity_allowed: bool = False
    post_contract_use_allowed: bool = False
    deletion_policy: str | None = None

    _v_number = field_validator("contract_number")(_reject_blank)

    @model_validator(mode="after")
    def _check_period(self) -> "ContractCreate":
        if self.contract_end < self.contract_start:
            raise ValueError("契約終了日は契約開始日以降にしてください。")
        return self


class PermissionCreate(BaseModel):
    contract_id: str = Field(min_length=1)
    media_scope: list[str] = []
    region_scope: list[str] = []
    product_scope: list[str] = []
    prohibited_product_scope: list[str] = []
    swimwear_allowed: bool = False
    underwear_allowed: bool = False
    bath_allowed: BathAllowed = "no"
    exposure_level_max: int = Field(default=0, ge=0, le=4)
    face_edit_allowed: bool = False
    body_edit_allowed: bool = False
    hair_edit_allowed: bool = False
    makeup_edit_allowed: bool = False
    age_appearance_change_allowed: bool = False
    video_allowed: bool = False
    secondary_use_allowed: bool = False
    overseas_allowed: bool = False
    approval_required_level: ApprovalRequiredLevel = "legal"


# ---- Projects ----
class ProjectCreate(BaseModel):
    project_name: str = Field(min_length=1)
    client_name: str | None = None
    brand_name: str | None = None
    product_name: str | None = None
    product_category: str | None = None
    deadline: date | None = None

    _v_name = field_validator("project_name")(_reject_blank)


class ProjectUpdate(BaseModel):
    project_name: str | None = Field(default=None, min_length=1)
    client_name: str | None = None
    brand_name: str | None = None
    product_name: str | None = None
    product_category: str | None = None
    project_status: str | None = None
    deadline: date | None = None

    _v_name = field_validator("project_name")(_reject_blank)


class RequirementCreate(BaseModel):
    media: list[str] = []
    region: list[str] = []
    usage_start: date | None = None
    usage_end: date | None = None
    output_type: OutputType = "image"
    scene_type: str | None = None
    outfit_type: str = "normal"
    exposure_level: int = Field(default=0, ge=0, le=5)
    secondary_use: bool = False
    overseas: bool = False
    pose_description: str | None = None
    expression_description: str | None = None
    background_description: str | None = None

    @model_validator(mode="after")
    def _check_period(self) -> "RequirementCreate":
        if self.usage_start and self.usage_end and self.usage_end < self.usage_start:
            raise ValueError("利用終了日は利用開始日以降にしてください。")
        return self


class ModelAssign(BaseModel):
    model_id: str = Field(min_length=1)
    usage_role: str = "main"


# ---- Compliance ----
class ComplianceCheckRequest(BaseModel):
    model_id: str = Field(min_length=1)
    # optional prompt allows term screening at check time
    prompt_text: str | None = None
    training_requested: bool = False


# ---- Generations ----
class GenerationCreate(BaseModel):
    project_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    compliance_check_id: str = Field(min_length=1)
    ai_engine_id: str | None = None
    prompt_text: str = Field(min_length=1)
    negative_prompt_text: str | None = None
    prompt_template_id: str | None = None
    generation_params: dict = {}

    _v_prompt = field_validator("prompt_text")(_reject_blank)


# ---- Prompt templates (P1-004) ----
class PromptTemplateCreate(BaseModel):
    name: str = Field(min_length=1)
    body: str = Field(min_length=1)
    negative_body: str | None = None
    tags: list[str] = []

    _v_name = field_validator("name")(_reject_blank)
    _v_body = field_validator("body")(_reject_blank)


class PromptTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    body: str | None = Field(default=None, min_length=1)
    negative_body: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None

    _v_name = field_validator("name")(_reject_blank)
    _v_body = field_validator("body")(_reject_blank)


class ApprovalRequestCreate(BaseModel):
    # External approval portal (P2-001/P2-002): only agency/person sign-off is
    # delegated outward; internal/legal/admin stay in-system.
    level: Literal["agency", "person"]
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    expires_in_days: int = Field(default=7, ge=1, le=90)


class PortalDecision(BaseModel):
    decision: Literal["approved", "conditional", "rejected"]
    comment: str | None = None
    approver_name: str | None = None


class OutputStatusUpdate(BaseModel):
    # Selection statuses ONLY. 'approved' can be reached solely through the
    # approval-completeness gate (POST /outputs/{id}/approvals) and 'delivered'
    # solely through delivery — allowing them here would let a single REVIEW-role
    # user bypass the multi-level approval chain (CLAUDE.md #3, docs/05 §9).
    output_status: Literal["candidate", "selected", "rejected"]


class ReviseRequest(BaseModel):
    revision_prompt: str = Field(min_length=1)
    target_area: str | None = None

    _v_prompt = field_validator("revision_prompt")(_reject_blank)


# ---- Reviews / approvals / deliveries ----
class ReviewCreate(BaseModel):
    review_type: str = Field(min_length=1)
    status: ReviewStatus
    comment: str | None = None

    _v_type = field_validator("review_type")(_reject_blank)


class ApprovalCreate(BaseModel):
    approval_level: ApprovalLevel
    approval_status: ApprovalStatus
    approval_comment: str | None = None


class DeliveryCreate(BaseModel):
    project_id: str = Field(min_length=1)
    output_id: str = Field(min_length=1)
    delivered_to: str | None = None
    delivery_method: str = "download_link"
    usage_media: list[str] = []
    usage_region: list[str] = []
    usage_start: date | None = None
    usage_end: date | None = None

    @model_validator(mode="after")
    def _check_period(self) -> "DeliveryCreate":
        if self.usage_start and self.usage_end and self.usage_end < self.usage_start:
            raise ValueError("利用終了日は利用開始日以降にしてください。")
        return self
