FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libopenblas-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

COPY . .

RUN mkdir -p runtime_data output_audio local_music data

COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Build-time defaults — override at runtime with -e GUNICORN_WORKERS=8
ARG GUNICORN_WORKERS=4
ARG GUNICORN_TIMEOUT=120
ARG GUNICORN_KEEPALIVE=5

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DANAH_ENV=production \
    GUNICORN_WORKERS=${GUNICORN_WORKERS} \
    GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT} \
    GUNICORN_KEEPALIVE=${GUNICORN_KEEPALIVE}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=20s \
    CMD curl -f http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]

# Shell form so ${GUNICORN_WORKERS} is expanded at container start.
# Override at runtime: docker run -e GUNICORN_WORKERS=8 ...
CMD gunicorn api.app_factory:app \
    --workers ${GUNICORN_WORKERS} \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT:-8000} \
    --timeout ${GUNICORN_TIMEOUT} \
    --keepalive ${GUNICORN_KEEPALIVE} \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile -
