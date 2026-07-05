"""Celery application, configured from app settings.

Run a worker with:

    celery -A app.workers.celery_app worker -l info

In local/dev and tests ``celery_task_always_eager`` is True, so tasks dispatched
with ``.delay()`` execute inline in the calling process and no broker/worker is
needed. Set it False (and point the broker/backend at a real Redis) to run the
generation jobs asynchronously via the ``worker`` service.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "real_ai_model_studio",
    broker=_settings.effective_celery_broker_url,
    backend=_settings.effective_celery_result_backend,
    include=["app.workers.generation_worker"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_always_eager=_settings.celery_task_always_eager,
    # In eager mode, surface task exceptions to the caller instead of swallowing
    # them; the task itself is written to never raise past its own body.
    task_eager_propagates=True,
    timezone="UTC",
    enable_utc=True,
)
