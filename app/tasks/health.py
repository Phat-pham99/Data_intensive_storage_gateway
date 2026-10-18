from __future__ import annotations

from app.celery_app import celery_app


@celery_app.task(name="health.ping")
def ping() -> str:
    """Trivial task used to verify the worker is consuming the broker."""

    return "pong"
