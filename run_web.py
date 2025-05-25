#!/usr/bin/env python
"""
Скрипт для запуска веб-интерфейса генератора протоколов совещаний
"""
import os
import uvicorn
import logging
from pathlib import Path

# Инициализация логирования
from app.utils.logging import setup_logging_from_yaml

# Создаем директорию для логов
# Определяем путь к директории логов
logs_dir = os.environ.get('LOGS_DIR', '/data/logs')
Path(logs_dir).mkdir(exist_ok=True, parents=True)

# Настраиваем логирование
try:
    setup_logging_from_yaml()
except Exception as e:
    print(f"Error initializing logging: {e}")
    # Используем стандартную конфигурацию
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler()
        ]
    )

from app.web.main import app

if __name__ == "__main__":
    # Определяем порт (по умолчанию 8000 или из переменной окружения)
    port = int(os.environ.get("PORT", 8000))
    
    # Запускаем сервер
    uvicorn.run(
        "app.web.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
