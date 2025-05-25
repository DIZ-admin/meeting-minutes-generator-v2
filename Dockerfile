# Первый этап: сборка зависимостей
FROM python:3.11-slim AS builder

WORKDIR /build

# Устанавливаем зависимости для компиляции
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        build-essential \
        python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы зависимостей и исходный код для установки
COPY pyproject.toml uv.lock ./
COPY app ./app
COPY schema ./schema
COPY README.md ./

# Устанавливаем uv для эффективной установки зависимостей
RUN pip install --no-cache-dir uv

# Устанавливаем зависимости в отдельную директорию
RUN mkdir -p /install
RUN uv pip install --system --target=/install .

# Второй этап: сборка финального образа
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем необходимые системные зависимости
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Копируем установленные зависимости из первого этапа
COPY --from=builder /install /usr/local/lib/python3.11/site-packages

# Копируем исходный код
COPY app ./app
COPY schema ./schema
COPY config ./config
COPY README.md ./
COPY run_web.py ./

# Создаем директории для данных
RUN mkdir -p /data/logs /data/output /data/uploads /data/cache /app/tasks /app/logs

# Устанавливаем права доступа 777 для директорий, чтобы веб-сервер мог записывать в них
RUN chmod -R 777 /data /app/tasks /app/logs

# Устанавливаем переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OUTPUT_DIR=/data/output \
    LOGS_DIR=/data/logs \
    CACHE_DIR=/data/cache

# Устанавливаем непривилегированного пользователя
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /data /app/tasks /app/logs
# Для веб-интерфейса не используем пользователя appuser, чтобы избежать проблем с правами доступа
# USER appuser

# Проверка работоспособности
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import sys, importlib.util; sys.exit(0 if importlib.util.find_spec('app') else 1)"

# Точка входа для CLI
ENTRYPOINT ["python", "-m", "app.cli"]

# Запускается по умолчанию без аргументов, выводит справку
CMD ["--help"]
