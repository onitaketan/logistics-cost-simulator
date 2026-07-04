"""Request/response DTOs for the MVP API surface (docs/03_api_spec.md).

Kept in one module for the scaffold; split per-domain as the surface grows.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, EmailStr, Field


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
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    role: str
    department: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    status: str | None = None
    department: str | None = None


# ---- Models ----
class ModelCreate(BaseModel):
    stage_name: str
    real_name: str
    agency_name: str | None = None
    agency_contact_name: str | None = None
    agency_contact_email: EmailStr | None = None
    birth_date: date | None = None
    adult_verified: bool = False
    notes: str | None = None


class ModelUpdate(BaseModel):
    stage_name: str | None = None
    agency_name: str | None = None
    status: str | None = None
    notes: str | None = None


class AdultVerify(BaseModel):
    adult_verified: bool = True


# ---- Contracts / permissions ----
class ContractCreate(BaseModel):
    contract_number: str
    contract_type: str = "base"
    contract_start: date
    contract_end: date
    renewal_type: str | None = None
    ai_generation_allowed: bool = False
    ai_training_allowed: bool = False
    synthetic_identity_allowed: bool = False
    post_contract_use_allowed: bool = False
    deletion_policy: str | None = None


class PermissionCreate(BaseModel):
    contract_id: str
    media_scope: list[str] = []
    region_scope: list[str] = []
    product_scope: list[str] = []
    prohibited_product_scope: list[str] = []
    swimwear_allowed: bool = False
    underwear_allowed: bool = False
    bath_allowed: str = "no"
    exposure_level_max: int = 0
    face_edit_allowed: bool = False
    body_edit_allowed: bool = False
    hair_edit_allowed: bool = False
    makeup_edit_allowed: bool = False
    age_appearance_change_allowed: bool = False
    video_allowed: bool = False
    secondary_use_allowed: bool = False
    overseas_allowed: bool = False
    approval_required_level: str = "legal"


# ---- Projects ----
class ProjectCreate(BaseModel):
    project_name: str
    client_name: str | None = None
    brand_name: str | None = None
    product_name: str | None = None
    product_category: str | None = None
    deadline: date | None = None


class RequirementCreate(BaseModel):
    media: list[str] = []
    region: list[str] = []
    usage_start: date | None = None
    usage_end: date | None = None
    output_type: str = "image"
    scene_type: str | None = None
    outfit_type: str = "normal"
    exposure_level: int = 0
    secondary_use: bool = False
    overseas: bool = False
    pose_description: str | None = None
    expression_description: str | None = None
    background_description: str | None = None


class ModelAssign(BaseModel):
    model_id: str
    usage_role: str = "main"


# ---- Compliance ----
class ComplianceCheckRequest(BaseModel):
    model_id: str
    # optional prompt allows term screening at check time
    prompt_text: str | None = None
    training_requested: bool = False


# ---- Generations ----
class GenerationCreate(BaseModel):
    project_id: str
    model_id: str
    compliance_check_id: str
    ai_engine_id: str | None = None
    prompt_text: str
    negative_prompt_text: str | None = None
    prompt_template_id: str | None = None
    generation_params: dict = {}


class OutputStatusUpdate(BaseModel):
    output_status: str


class ReviseRequest(BaseModel):
    revision_prompt: str
    target_area: str | None = None


# ---- Reviews / approvals / deliveries ----
class ReviewCreate(BaseModel):
    review_type: str
    status: str
    comment: str | None = None


class ApprovalCreate(BaseModel):
    approval_level: str
    approval_status: str
    approval_comment: str | None = None


class DeliveryCreate(BaseModel):
    project_id: str
    output_id: str
    delivered_to: str | None = None
    delivery_method: str = "download_link"
    usage_media: list[str] = []
    usage_region: list[str] = []
    usage_start: date | None = None
    usage_end: date | None = None
