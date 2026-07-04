"""Generation service — the generation LOCK.

A generation job may only be created when its compliance check exists and is
`ok` or `conditional`, and belongs to the same project+model. This mirrors the
DB trigger (defense in depth): even if the trigger is dropped, the app refuses;
even if the app is bypassed, the DB refuses.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.compliance_engine import Status


class GenerationBlocked(Exception):
    """Raised when generation is attempted without a passing compliance check."""


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
