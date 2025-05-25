"""
Настройки по умолчанию и константы для приложения
"""
from pathlib import Path

# Базовые настройки приложения
APP_NAME = "meeting-protocol-generator"
APP_VERSION = "0.2.0"

"""
Настройки по умолчанию и константы для приложения
"""
import os
from pathlib import Path

# Базовые настройки приложения
APP_NAME = "meeting-protocol-generator"
APP_VERSION = "0.2.0"

# Пути по умолчанию - используем переменные окружения если доступны
BASE_DIR = Path(__file__).parent.parent.parent  # Корневая директория проекта
SCHEMA_DIR = BASE_DIR / "schema"  # Директория с JSON схемами
SCHEMA_PATH = SCHEMA_DIR / "egl_protokoll.json"  # Путь к JSON схеме протокола

# Директории для данных - используем переменные окружения в Docker
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", BASE_DIR / "output"))  
UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", BASE_DIR / "uploads"))  
LOGS_DIR = Path(os.environ.get("LOGS_DIR", BASE_DIR / "logs"))  
CACHE_DIR = Path(os.environ.get("CACHE_DIR", BASE_DIR / "cache"))

TEMPLATES_DIR = BASE_DIR / "app" / "templates"  # Директория с шаблонами
PROMPTS_DIR = TEMPLATES_DIR / "prompts"  # Директория с шаблонами промптов
MARKDOWN_TEMPLATES_DIR = TEMPLATES_DIR / "markdown"  # Директория с шаблонами Markdown

# ASR настройки по умолчанию
DEFAULT_LANG = "de"  # Язык по умолчанию для ASR
REPLICATE_MODEL = "thomasmol/whisper-diarization"  # Модель Replicate по умолчанию
REPLICATE_VERSION = "1495a9cddc83b2203b0d8d3516e38b80fd1572ebc4bc5700ac1da56a9b3ed886"  # Версия модели

# LLM настройки по умолчанию
DEFAULT_LLM_MODEL = "gpt-4o"  # Модель OpenAI по умолчанию
DEFAULT_TEMPERATURE = 0.2  # Температура по умолчанию для промптов
DEFAULT_LLM_TIMEOUT = 120  # Таймаут для LLM запросов в секундах
DEFAULT_MAX_RETRIES = 3  # Максимальное количество попыток для LLM запросов

# Map-Reduce настройки
CHUNK_TOKENS = 550  # Размер чанка для Map-Reduce в токенах
OVERLAP_TOKENS = 100  # Перекрытие для чанков в токенах
ENCODING_NAME = "cl100k_base"  # Имя токенизатора для OpenAI моделей

# Notifications настройки
DEFAULT_TELEGRAM_PARSE_MODE = "Markdown"  # Режим парсинга для Telegram уведомлений

# Логирование
DEFAULT_LOG_LEVEL = "INFO"  # Уровень логирования по умолчанию
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"  # Формат логов
