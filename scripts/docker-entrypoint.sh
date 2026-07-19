#!/usr/bin/env bash
# Docker entrypoint — runs Alembic migrations then starts the app.
set -e

echo "[entrypoint] Running database migrations..."
if ! python -m alembic upgrade head; then
  env_lower=$(echo "${DANAH_ENV:-development}" | tr '[:upper:]' '[:lower:]')
  if [ "$env_lower" = "production" ]; then
    echo "[entrypoint] FATAL: alembic migration failed in production — refusing to start" >&2
    exit 1
  fi
  echo "[entrypoint] WARNING: alembic migration failed (DB may not be ready)"
fi

echo "[entrypoint] Starting application..."
exec "$@"
