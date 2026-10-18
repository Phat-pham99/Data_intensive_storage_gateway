from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.db.session import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Control plane for S3 object lifecycle management: metadata, policy "
        "decisions, and asynchronous job orchestration."
    ),
    lifespan=lifespan,
)


def _check_database() -> tuple[bool, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"error: {exc}"


def _check_redis() -> tuple[bool, str]:
    try:
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"error: {exc}"


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
    }


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness probe: the process is up."""

    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def readiness() -> JSONResponse:
    """Readiness probe: dependencies (Postgres, Redis) are reachable."""

    db_ok, db_detail = _check_database()
    redis_ok, redis_detail = _check_redis()
    checks: dict[str, Any] = {
        "database": db_detail,
        "redis": redis_detail,
    }
    healthy = db_ok and redis_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
