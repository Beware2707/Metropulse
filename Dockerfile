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

# --ws websockets enables permessage-deflate compression for /ws/live.
CMD ["uvicorn", "metropulse.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--ws", "websockets", "--no-access-log"]
