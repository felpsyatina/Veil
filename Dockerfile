# Единый образ для всех Python-сервисов проекта (bot, api, worker, migrate).
# Конкретный процесс, который запускается, определяется командой `command:`
# соответствующего сервиса в docker-compose.yml.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# postgresql-client нужен для pg_dump/pg_restore в задачах бэкапа (worker).
# curl — для healthcheck'ов контейнеров.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY scripts ./scripts

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /backups \
    && chown -R appuser:appuser /app /backups

USER appuser

# Реальная команда переопределяется в docker-compose.yml для каждого сервиса.
CMD ["python", "-m", "app.bot.main"]
