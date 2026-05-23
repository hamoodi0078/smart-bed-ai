#!/usr/bin/env bash
# Docker entrypoint — runs Alembic migrations then starts the app.
set -e

echo "[entrypoint] Running database migrations..."
python -m alembic upgrade head || echo "[entrypoint] WARNING: alembic migration failed (DB may not be ready)"

echo "[entrypoint] Starting application..."
exec "$@"
