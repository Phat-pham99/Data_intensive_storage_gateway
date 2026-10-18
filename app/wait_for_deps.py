from __future__ import annotations

import sys
import time

import redis
from sqlalchemy import text

from app.config import get_settings
from app.db.session import engine

MAX_ATTEMPTS = 30
DELAY_SECONDS = 2


def _check_database() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"database not ready: {exc}")
        return False


def _check_redis() -> bool:
    try:
        client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
        client.ping()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"redis not ready: {exc}")
        return False


def main() -> int:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        db_ok = _check_database()
        redis_ok = _check_redis()
        if db_ok and redis_ok:
            print("dependencies ready")
            return 0
        print(f"attempt {attempt}/{MAX_ATTEMPTS} failed, retrying in {DELAY_SECONDS}s")
        time.sleep(DELAY_SECONDS)
    print("dependencies did not become ready in time")
    return 1


if __name__ == "__main__":
    sys.exit(main())
