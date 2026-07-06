"""Generation service — the generation LOCK.

A generation job may only be created when its compliance check exists and is
`ok` or `conditional`, and belongs to the same project+model. This mirrors the
DB trigger (defense in depth): even if the trigger is dropped, the app refuses;
even if the app is bypassed, the DB refuses.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.compliance_engine import Status
from app.services.prompt_filter import screen


class GenerationBlocked(Exception):
    """Raised when generation is attempted without a passing compliance check."""


def assert_prompt_clean(*texts: str | None) -> None:
    """Fail-closed prompt screening at the generation boundary (docs/05 §7).

    The compliance check screens the prompt supplied at check time, but the
    prompt/negative-prompt/revision-prompt actually sent to the engine can differ
    from it — a passing check must never become a licence to send an arbitrary,
    unscreened prompt. Re-screen every text that reaches the engine and refuse
    outright on any prohibited term (minors, explicit nudity, sexual acts,
    coercion, crime, etc.). Warning terms are NOT blocked here — those are the
    compliance check's Conditional path — only hard prohibitions.
    """
    hits: set[str] = set()
    for t in texts:
        hits |= {f for f in screen(t) if f.startswith("prohibited:")}
    if hits:
        terms = ", ".join(sorted(h.split(":", 1)[1] for h in hits))
        raise GenerationBlocked(f"禁止語句が含まれるため生成できません（{terms}）。")


@dataclass(frozen=True)
class ComplianceCheckRef:
    id: str
    project_id: str
    model_id: str
    check_status: str


def assert_generation_allowed(
    check: ComplianceCheckRef | None, *, project_id: str, model_id: str
) -> None:
    if check is None:
        raise GenerationBlocked("コンプライアンス判定が存在しません。")
    if check.project_id != project_id or check.model_id != model_id:
        raise GenerationBlocked("判定が案件/モデルと一致しません。")
    if check.check_status not in (Status.OK.value, Status.CONDITIONAL.value):
        raise GenerationBlocked(
            f"判定ステータスが '{check.check_status}' のため生成できません。"
        )


async def run_generation(adapter, prompt: str, params: dict) -> list:
    """Invoke the AI adapter. Callers MUST have passed assert_generation_allowed."""
    return await adapter.generate_image(prompt, params)


def _resolve_contract(db, check, model_id):
    """Resolve the contract the compliance check was evaluated against.

    The check records the contract id in ``matched_permissions``; fall back to the
    model's latest contract (mirrors compliance router's ``_latest_contract``).
    """
    from sqlalchemy import select

    from app.models.model import ModelContract

    contract_id = None
    if isinstance(check.matched_permissions, dict):
        contract_id = check.matched_permissions.get("contract_id")
    if contract_id:
        contract = db.get(ModelContract, contract_id)
        if contract is not None:
            return contract
    return db.scalar(
        select(ModelContract)
        .where(ModelContract.model_id == model_id)
        .order_by(ModelContract.contract_end.desc())
    )


def revalidate_before_run(db, generation_id) -> None:
    """THIRD compliance checkpoint — run at execution time inside the worker.

    Time passes between enqueue and execution, so the worker must NOT trust the
    enqueue-time gate. This re-reads state from the DB and refuses if anything
    changed since the job was queued:

      1. the compliance check must still be ``ok`` or ``conditional``;
      2. the linked contract must still be valid (``contract_end`` >= today) and
         ``ai_generation_allowed`` must still be true.

    Raises ``GenerationBlocked`` on any failure; returns ``None`` when safe to run.
    The existing request-time gate and DB trigger remain — this is additive.
    """
    from datetime import date

    from app.models.generation import ComplianceCheck, Generation

    generation = db.get(Generation, generation_id)
    if generation is None:
        raise GenerationBlocked("生成ジョブが見つかりません。")

    check = db.get(ComplianceCheck, generation.compliance_check_id)
    if check is None:
        raise GenerationBlocked("コンプライアンス判定が存在しません。")
    # Force a fresh read: the row may have been flipped (e.g. ok -> ng) after enqueue.
    db.refresh(check)
    if check.check_status not in (Status.OK.value, Status.CONDITIONAL.value):
        raise GenerationBlocked(
            f"判定ステータスが '{check.check_status}' のため生成できません。"
        )
    if check.project_id != generation.project_id or check.model_id != generation.model_id:
        raise GenerationBlocked("判定が案件/モデルと一致しません。")

    contract = _resolve_contract(db, check, generation.model_id)
    if contract is None:
        raise GenerationBlocked("契約が存在しません。")
    db.refresh(contract)
    if contract.contract_end < date.today():
        raise GenerationBlocked("契約期間が終了しています。")
    if not contract.ai_generation_allowed:
        raise GenerationBlocked("AI生成が契約上許可されていません。")


def enqueue_generation(generation_id) -> None:
    """Dispatch the generation job to the Celery worker.

    In eager mode (settings.celery_task_always_eager=True, the local/dev/test
    default) ``.delay()`` runs the task inline in-process, so the generation row
    reaches a terminal state before this returns. In production it is picked up
    by the ``worker`` service. Imported lazily to avoid an import cycle.
    """
    from app.workers.generation_worker import run_generation_job

    run_generation_job.delay(str(generation_id))
