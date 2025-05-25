#!/usr/bin/env python3
"""
Скрипт для запуска веб-интерфейса
"""
import sys
import os
from pathlib import Path

# Добавляем родительскую директорию в путь импорта
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

from app.web import start

if __name__ == "__main__":
    # Запускаем веб-сервер
    start()
