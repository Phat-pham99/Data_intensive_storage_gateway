#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-false}" == "true" ]]; then
    echo "Running database migrations..."
    alembic upgrade head
fi

if [[ "${WAIT_FOR_DEPS:-false}" == "true" ]]; then
    echo "Waiting for dependencies..."
    python -m app.wait_for_deps
fi

exec "$@"
