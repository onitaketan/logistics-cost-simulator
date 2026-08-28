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

        # Load consented reference photos (img2img basis) as base64 for the
        # adapter. Ownership/consent were validated at request time; re-checked
        # here (defense in depth) since time passed and rows may have changed.
        params = dict(generation.generation_params or {})
        refs_b64 = _load_reference_images_b64(db, generation)
        if refs_b64:
            params["reference_images_b64"] = refs_b64

        # Adapter methods are async; bridge via asyncio.run. Safe because this runs
        # on a worker thread / process with no already-running event loop.
        images = asyncio.run(
            adapter.generate_image(generation.prompt_text, params)
        )

        for i, img in enumerate(images):
            # Persist the REAL image into our own storage (encrypted, hashed).
            # A provider URL is temporary and must never be our stored file
            # (CLAUDE.md #6; file_hash rule). Mock keeps a placeholder path.
            file_path, file_hash = _persist_image(img, str(generation.id), i)
            db.add(
                GenerationOutput(
                    generation_id=generation.id,
                    file_path=file_path,
                    file_hash=file_hash,
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


def _load_reference_images_b64(db, generation) -> list[str]:
    """Resolve generation_params.reference_asset_ids to base64 image payloads.

    Execution-time consent gate (defense in depth alongside the request-time
    checks): only the generation's OWN model's, consented, generation-eligible,
    non-deleted assets are loaded. Anything that fails re-validation is skipped
    fail-closed rather than sent to an engine.
    """
    import base64

    from app.models.model import ModelAsset
    from app.services.storage_service import read as storage_read

    ids = (generation.generation_params or {}).get("reference_asset_ids") or []
    out: list[str] = []
    for aid in ids[:4]:
        asset = db.get(ModelAsset, aid)
        if (
            asset is None
            or asset.deleted_at is not None
            or str(asset.model_id) != str(generation.model_id)
            or not asset.consent_confirmed
            or asset.usage_type not in ("reference", "training")
            or asset.asset_type == "ng"
        ):
            continue
        try:
            out.append(base64.b64encode(storage_read(asset.file_path)).decode())
        except Exception:  # unreadable file: skip, never crash the generation
            continue
    return out


def _persist_image(img, generation_id: str, index: int) -> tuple[str, str]:
    """Store a produced image and return (stored_uri, sha256_of_bytes).

    Resolution order for the real bytes:
      1. ``img.data`` — bytes the provider returned inline (e.g. gpt-image-1 b64);
      2. ``img.source_url`` or an http(s) ``img.file_path`` — download the bytes;
      3. neither (the mock engine) — keep the placeholder path and hash the path.
    Real bytes are written through ``storage_service.store`` so they land in the
    configured backend (local / S3 / R2) encrypted, and the hash is of the actual
    image content — not of a URL string.
    """
    from app.services.storage_service import compute_hash, store

    raw = img.data
    if raw is None:
        url = img.source_url
        if url is None and isinstance(img.file_path, str) and img.file_path.startswith(
            ("http://", "https://")
        ):
            url = img.file_path
        if url:
            import httpx

            resp = httpx.get(url, timeout=60.0)
            resp.raise_for_status()
            raw = resp.content

    if raw is None:
        # Mock / no real bytes: keep the placeholder path, hash the path string.
        return img.file_path, compute_hash(img.file_path.encode())

    uri, file_hash = store(raw, key=f"generations/{generation_id}/{index}.png", encrypt=True)
    return uri, file_hash


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
