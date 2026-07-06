"""Compliance check endpoint — assembles inputs and runs the pure engine.

This is where DB state is translated into the engine's typed inputs. The engine
itself never touches the DB (so it stays testable); this router is the only
adapter between persistence and judgement.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
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
from app.services.prompt_filter import screen_with_model_ng

router = APIRouter(prefix="/projects", tags=["compliance"])


def _latest_contract(db: Session, model_id: str, today: date) -> ModelContract | None:
    """Pick the contract that actually governs generation right now.

    Ordering purely by ``contract_end`` DESC would prefer whichever contract ends
    furthest in the future — which may not be in effect yet, while an in-force
    contract is ignored. Prefer a contract whose period covers ``today``
    (``start <= today <= end``), taking the most recently started of those. Only
    if none is currently in force do we fall back to the latest-ending contract,
    so the engine still sees a contract to flag as expired (NG) rather than
    reporting "no contract".
    """
    contracts = list(db.scalars(
        select(ModelContract).where(ModelContract.model_id == model_id)
    ).all())
    if not contracts:
        return None
    active = [c for c in contracts if c.contract_start <= today <= c.contract_end]
    if active:
        return max(active, key=lambda c: c.contract_start)
    return max(contracts, key=lambda c: c.contract_end)


def _permission_for(db: Session, contract_id) -> ModelPermission | None:
    return db.scalar(select(ModelPermission).where(ModelPermission.contract_id == contract_id))


def _model_ng_rules(db: Session, model_id: str) -> list[tuple[str, str]]:
    """Load (rule_type, value) NG rules for a model.

    ``model_ng_rules`` has no ORM mapping in this service, so read it directly.
    Returns an empty list when the model has no NG rules (fail-open here only in
    the sense that the base permission rules still apply — the engine remains the
    authority).
    """
    rows = db.execute(
        text("SELECT rule_type, value FROM model_ng_rules WHERE model_id = :m"),
        {"m": str(model_id)},
    ).all()
    return [(r[0], r[1]) for r in rows]


def _screen_and_collect_ng(
    rules: list[tuple[str, str]],
    prompt_text: str | None,
    requirement: ProjectRequirement,
    product_category: str,
) -> tuple[set[str], set[str]]:
    """Screen the prompt and collect model NG hits.

    Returns ``(prompt_flags, model_ng_hits)``:
      * prompt_flags — prohibited/warn flags for the engine (docs 05 §7/§8).
      * model_ng_hits — model-specific NG labels the engine records as NG:
          - ng_word  matched against the prompt text (via prompt_filter)
          - ng_pose  matched against pose / expression descriptions
          - ng_scene matched against scene type / background description
          - ng_product matched against the project's product category
    """
    ng_words = {v for (t, v) in rules if t == "ng_word"}
    # Screen the free-text requirement descriptions alongside the prompt: pose /
    # expression / scene / background text can carry prohibited or warning terms
    # even when the prompt field is clean (docs/05 §7/§8). Join them so a single
    # screen pass covers every author-supplied description that steers the image.
    screened_text = " ".join(
        t for t in (
            prompt_text,
            requirement.pose_description,
            requirement.expression_description,
            requirement.scene_type,
            requirement.background_description,
        ) if t
    )
    flags = screen_with_model_ng(screened_text, ng_words)
    prompt_flags = {f for f in flags if not f.startswith("ng_word:")}
    hits = {f for f in flags if f.startswith("ng_word:")}

    def _text_hits(values: set[str], *fields: str | None) -> set[str]:
        joined = " ".join(f for f in fields if f).lower()
        return {v for v in values if v and v.lower() in joined}

    for v in _text_hits(
        {v for (t, v) in rules if t == "ng_pose"},
        requirement.pose_description, requirement.expression_description,
    ):
        hits.add(f"ng_pose:{v}")
    for v in _text_hits(
        {v for (t, v) in rules if t == "ng_scene"},
        requirement.scene_type, requirement.background_description,
    ):
        hits.add(f"ng_scene:{v}")
    for v in _text_hits(
        {v for (t, v) in rules if t == "ng_product"},
        product_category,
    ):
        hits.add(f"ng_product:{v}")
    return prompt_flags, hits


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
    if not model or model.deleted_at:
        # A soft-deleted model (e.g. consent withdrawn) must not pass compliance,
        # so no fresh passing check — and therefore no generation — can reference it.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "モデルが見つかりません。")
    today = date.today()
    contract = _latest_contract(db, body.model_id, today)
    if not contract:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "契約が未登録です。")
    permission = _permission_for(db, contract.id)
    if not permission:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "許諾範囲が未登録です。")

    ng_rules = _model_ng_rules(db, body.model_id)
    prompt_flags, model_ng_hits = _screen_and_collect_ng(
        ng_rules, body.prompt_text, requirement, project.product_category or ""
    )

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
            prompt_flags=prompt_flags,
            model_ng_hits=model_ng_hits,
        ),
        today=today,
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
