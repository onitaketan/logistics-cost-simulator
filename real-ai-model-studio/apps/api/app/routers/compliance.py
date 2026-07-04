"""Compliance check endpoint — assembles inputs and runs the pure engine.

This is where DB state is translated into the engine's typed inputs. The engine
itself never touches the DB (so it stays testable); this router is the only
adapter between persistence and judgement.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import Perm
from app.core.security import CurrentUserDep, require
from app.db.session import get_db
from app.models.generation import ComplianceCheck
from app.models.model import Model, ModelContract, ModelPermission
from app.models.project import Project, ProjectRequirement
from app.schemas.common import ok
from app.schemas.dto import ComplianceCheckRequest
from app.services import audit_service, compliance_engine as ce
from app.services.prompt_filter import screen

router = APIRouter(prefix="/projects", tags=["compliance"])


def _latest_contract(db: Session, model_id: str) -> ModelContract | None:
    return db.scalar(
        select(ModelContract)
        .where(ModelContract.model_id == model_id)
        .order_by(ModelContract.contract_end.desc())
    )


def _permission_for(db: Session, contract_id) -> ModelPermission | None:
    return db.scalar(select(ModelPermission).where(ModelPermission.contract_id == contract_id))


@router.post("/{project_id}/compliance-check")
def run_check(
    project_id: str,
    body: ComplianceCheckRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUserDep, Depends(require(Perm.COMPLIANCE_RUN))],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "案件が見つかりません。")
    requirement = db.scalar(
        select(ProjectRequirement).where(ProjectRequirement.project_id == project_id)
    )
    if not requirement:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "案件要件が未登録です。")

    model = db.get(Model, body.model_id)
    if not model:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "モデルが見つかりません。")
    contract = _latest_contract(db, body.model_id)
    if not contract:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "契約が未登録です。")
    permission = _permission_for(db, contract.id)
    if not permission:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "許諾範囲が未登録です。")

    flags = screen(body.prompt_text)

    result = ce.evaluate(
        model=ce.ModelInput(
            adult_verified=model.adult_verified,
            birth_date=model.birth_date,
            status=model.status,
        ),
        contract=ce.ContractInput(
            contract_end=contract.contract_end,
            ai_generation_allowed=contract.ai_generation_allowed,
            ai_training_allowed=contract.ai_training_allowed,
            post_contract_use_allowed=contract.post_contract_use_allowed,
        ),
        permission=ce.PermissionInput(
            media_scope=set(permission.media_scope or []),
            region_scope=set(permission.region_scope or []),
            product_scope=set(permission.product_scope or []),
            prohibited_product_scope=set(permission.prohibited_product_scope or []),
            swimwear_allowed=permission.swimwear_allowed,
            underwear_allowed=permission.underwear_allowed,
            bath_allowed=permission.bath_allowed,
            exposure_level_max=permission.exposure_level_max,
            overseas_allowed=permission.overseas_allowed,
            secondary_use_allowed=permission.secondary_use_allowed,
            video_allowed=permission.video_allowed,
            age_appearance_change_allowed=permission.age_appearance_change_allowed,
            approval_required_level=permission.approval_required_level,
        ),
        requirement=ce.RequirementInput(
            media=set(requirement.media or []),
            region=set(requirement.region or []),
            product_category=project.product_category or "",
            output_type=requirement.output_type,
            outfit_type=requirement.outfit_type,
            exposure_level=requirement.exposure_level,
            usage_end=requirement.usage_end,
            secondary_use=requirement.secondary_use,
            overseas=requirement.overseas,
            training_requested=body.training_requested,
            prompt_flags=flags,
        ),
        today=date.today(),
    )

    check = ComplianceCheck(
        project_id=project_id,
        model_id=body.model_id,
        check_status=result.status.value,
        risk_level=result.risk_level.value,
        matched_permissions={"contract_id": str(contract.id), "permission_id": str(permission.id)},
        violations=[{"field": v.field, "message": v.message, "result": v.result.value}
                    for v in result.violations],
        required_approvals=result.required_approvals,
        check_summary=result.summary,
        checked_by=user.id,
    )
    db.add(check)
    db.flush()
    audit_service.record(
        db, user_id=user.id, action_type="create", target_type="compliance_check",
        target_id=str(check.id), after={"status": result.status.value},
    )
    db.commit()

    payload = result.as_dict()
    payload["compliance_check_id"] = str(check.id)
    return ok(payload)
