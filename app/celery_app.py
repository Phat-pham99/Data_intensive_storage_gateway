from __future__ import annotations

from celery import Celery

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "data_lifecycle_gateway",
    broker=_settings.broker_url,
    backend=_settings.result_backend,
    include=["app.tasks.health"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
