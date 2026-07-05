"""Celery task that runs an image-generation job off the request path.

Lifecycle: queued (inserted by the API) -> running -> completed | failed.
The client already polls GET /generations/{id} then /generations/{id}/outputs,
so this queued->running->completed flow is supported end-to-end.

SAFETY: time passes between enqueue and execution, so before touching the AI
adapter the task re-validates compliance via
``generation_service.revalidate_before_run`` (the THIRD checkpoint, alongside
the request-time gate and the DB trigger). If that fails the job is marked
``failed`` and audited; NO outputs are produced. The task never raises past its
own body.
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.services import audit_service, generation_service
from app.services.generation_service import GenerationBlocked
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.generation_worker.run_generation_job")
def run_generation_job(generation_id: str) -> dict:
    # Lazy imports keep the module import-cycle-free and mirror the router.
    from app.db.session import SessionLocal
    from app.models.generation import AIEngine, Generation, GenerationOutput
    from app.services.ai_engines import get_adapter
    from app.services.storage_service import compute_hash

    db = SessionLocal()
    try:
        generation = db.get(Generation, generation_id)
        if generation is None:
            return {"generation_id": generation_id, "status": "not_found"}

        # THIRD checkpoint — re-validate before doing any work or marking running.
        # Checking first also avoids fighting the DB gate: if the check flipped to
        # ng, even an UPDATE to 'running' would be rejected by the trigger.
        try:
            generation_service.revalidate_before_run(db, generation_id)
        except GenerationBlocked as exc:
            _record_failure(generation_id, str(exc))
            return {"generation_id": generation_id, "status": "failed"}

        generation.status = "running"
        db.flush()

        adapter_key = get_settings().ai_engine
        if generation.ai_engine_id:
            engine = db.get(AIEngine, generation.ai_engine_id)
            if engine is not None:
                adapter_key = engine.adapter_key
        adapter = get_adapter(adapter_key)

        # Adapter methods are async; bridge via asyncio.run. Safe because this runs
        # on a worker thread / process with no already-running event loop.
        images = asyncio.run(
            adapter.generate_image(
                generation.prompt_text, generation.generation_params or {}
            )
        )

        for img in images:
            db.add(
                GenerationOutput(
                    generation_id=generation.id,
                    file_path=img.file_path,
                    file_hash=compute_hash(img.file_path.encode()),
                    width=img.width,
                    height=img.height,
                    output_status="candidate",
                )
            )
        generation.status = "completed"
        db.flush()

        audit_service.record(
            db,
            user_id=generation.generated_by,
            action_type="generate",
            target_type="output",
            target_id=str(generation.id),
            after={
                "compliance_check_id": str(generation.compliance_check_id),
                "count": len(images),
            },
        )
        db.commit()
        return {"generation_id": generation_id, "status": "completed", "count": len(images)}
    except Exception as exc:  # noqa: BLE001 — a task failure must not raise past here
        db.rollback()
        _record_failure(generation_id, f"generation failed: {exc}")
        return {"generation_id": generation_id, "status": "failed"}
    finally:
        db.close()


def _record_failure(generation_id: str, reason: str) -> None:
    """Mark the job failed (best effort) and always write an audit log.

    Kept in two independent transactions: the DB generation-gate trigger can
    reject the status UPDATE if the compliance check itself flipped to ng, but
    the failure MUST still be audited. No outputs are ever produced on this path.
    """
    from app.db.session import SessionLocal
    from app.models.generation import Generation

    # 1) Best-effort status='failed'. May be blocked by the DB gate — that is
    #    acceptable: the important invariant is that no outputs exist.
    db = SessionLocal()
    try:
        generation = db.get(Generation, generation_id)
        if generation is not None and generation.status != "completed":
            generation.status = "failed"
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()

    # 2) Audit the failure in its own transaction so it survives regardless.
    db = SessionLocal()
    try:
        generation = db.get(Generation, generation_id)
        user_id = generation.generated_by if generation is not None else None
        audit_service.record(
            db,
            user_id=user_id,
            action_type="generate",
            target_type="output",
            target_id=str(generation_id),
            after={"status": "failed", "reason": reason},
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()
