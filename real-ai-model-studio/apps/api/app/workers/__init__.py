"""Queue worker package (docs/06 §5).

Heavy image generation runs as a Celery task consumed by a separate worker
process, decoupled from the request/response cycle. In local/dev and tests the
Celery app runs in eager mode (settings.celery_task_always_eager=True), so
`.delay()` executes the task inline without a broker.
"""
