FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libatlas-base-dev \
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

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DANAH_ENV=production \
    # Workers: default 4; override with GUNICORN_WORKERS env var
    GUNICORN_WORKERS=${GUNICORN_WORKERS:-4} \
    GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-120} \
    GUNICORN_KEEPALIVE=${GUNICORN_KEEPALIVE:-5}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=20s \
    CMD curl -f http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]

# Gunicorn with 4 async workers, request recycling to prevent memory leaks,
# and graceful shutdown timeout so in-flight requests complete.
CMD ["gunicorn", "api.app_factory:app", \
    "--workers", "4", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--timeout", "120", \
    "--keepalive", "5", \
    "--max-requests", "1000", \
    "--max-requests-jitter", "100", \
    "--graceful-timeout", "30", \
    "--access-logfile", "-", \
    "--error-logfile", "-"]
