# Сборка бота «Сохрано».
# Слой с зависимостями кешируется отдельно: код меняется чаще requirements.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Moscow

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# Файлы вложений живут в томе, а не в образе.
RUN mkdir -p /app/media
VOLUME ["/app/media"]

# Схема применяется перед стартом: перезапуск контейнера сам догоняет миграции.
CMD ["sh", "-c", "alembic upgrade head && python -m app"]
