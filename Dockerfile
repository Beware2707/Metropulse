FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so source changes don't bust the layer cache.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic ./alembic

RUN useradd --create-home --uid 1000 metropulse
USER metropulse

EXPOSE 8000

# The worker service disables this in docker-compose (it serves no HTTP).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# --ws websockets enables permessage-deflate compression for /ws/live;
# --proxy-headers trusts X-Forwarded-* from the fronting load balancer.
CMD ["uvicorn", "metropulse.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--ws", "websockets", "--no-access-log", "--proxy-headers"]
