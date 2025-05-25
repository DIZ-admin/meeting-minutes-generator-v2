"""
Модуль конфигурации приложения
"""
import os
import json
from pathlib import Path
from typing import Optional, Dict, List, Any, Union

from pydantic_settings import BaseSettings
from pydantic import Field, validator

from .settings import (
    APP_NAME, APP_VERSION, BASE_DIR, SCHEMA_PATH, OUTPUT_DIR, 
    DEFAULT_LANG, REPLICATE_MODEL, REPLICATE_VERSION,
    DEFAULT_LLM_MODEL, CHUNK_TOKENS, OVERLAP_TOKENS,
    DEFAULT_TELEGRAM_PARSE_MODE, DEFAULT_LOG_LEVEL
)
from ..core.exceptions import ConfigError

class AppConfig(BaseSettings):
    """
    Централизованная конфигурация приложения с использованием Pydantic
    """
    # Базовые настройки
    app_name: str = Field(default=APP_NAME)
    app_version: str = Field(default=APP_VERSION)
    debug: bool = Field(default=False, env="APP_DEBUG")
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, env="LOG_LEVEL")
    
    # Пути
    base_dir: Path = Field(default_factory=lambda: BASE_DIR)
    schema_path: Path = Field(default_factory=lambda: SCHEMA_PATH)
    output_dir: Path = Field(default_factory=lambda: OUTPUT_DIR)
    cache_dir: Path = Field(default_factory=lambda: BASE_DIR / "cache")
    log_dir: Path = Field(default_factory=lambda: BASE_DIR / "logs")
    uploads_dir: Path = Field(default_factory=lambda: BASE_DIR / "uploads")
    prompt_templates_dir: Path = Field(default_factory=lambda: BASE_DIR / "app" / "templates" / "prompts")
    
    # ASR настройки
    default_lang: str = Field(default=DEFAULT_LANG, env="TRANSCRIPTION_LANG")
    replicate_api_token: Optional[str] = Field(default=None, env="REPLICATE_API_TOKEN")
    replicate_model: str = Field(default=REPLICATE_MODEL, env="REPLICATE_MODEL")
    replicate_version: str = Field(default=REPLICATE_VERSION, env="REPLICATE_VERSION")
    
    # OpenAI настройки
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    openai_model: str = Field(default=DEFAULT_LLM_MODEL, env="OPENAI_MODEL")
    
    # Telegram настройки
    telegram_bot_token: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, env="TELEGRAM_CHAT_ID")
    telegram_parse_mode: str = Field(default=DEFAULT_TELEGRAM_PARSE_MODE, env="TELEGRAM_PARSE_MODE")
    
    # Map-Reduce настройки
    chunk_tokens: int = Field(default=CHUNK_TOKENS, env="CHUNK_TOKENS")
    overlap_tokens: int = Field(default=OVERLAP_TOKENS, env="OVERLAP_TOKENS")
    
    class Config:
        """Настройки для Pydantic"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        
        # Разрешить дополнительные атрибуты
        extra = "ignore"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Создание директорий, если они не существуют
        directories_to_create = [
            ("output", self.output_dir),
            ("cache", self.cache_dir),
            ("logs", self.log_dir),
            ("uploads", self.uploads_dir),
            ("prompt_templates", self.prompt_templates_dir)
        ]
        
        for name, directory in directories_to_create:
            if directory is None:
                # Установка по умолчанию
                if name == "output":
                    directory = self.base_dir / "output"
                    self.output_dir = directory
                elif name == "cache":
                    directory = self.base_dir / "cache"
                    self.cache_dir = directory
                elif name == "logs":
                    directory = self.base_dir / "logs"
                    self.log_dir = directory
                elif name == "uploads":
                    directory = self.base_dir / "uploads"
                    self.uploads_dir = directory
                elif name == "prompt_templates":
                    directory = self.base_dir / "app" / "templates" / "prompts"
                    self.prompt_templates_dir = directory
            
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                # Логируем ошибку, но не останавливаем инициализацию
                print(f"Warning: Could not create {name} directory {directory}: {e}")
        
        # Валидируем критические настройки при инициализации
        self._validate_critical_config()
    
    def _validate_critical_config(self):
        """Валидирует критические настройки при инициализации"""
        errors = []
        
        # Проверяем наличие API ключей - но только если они не демо-значения
        if not self.openai_api_key or self.openai_api_key.startswith("demo_"):
            print("Warning: OPENAI_API_KEY not set - некоторые функции будут недоступны")
        if not self.replicate_api_token or self.replicate_api_token.startswith("demo_"):
            print("Warning: REPLICATE_API_TOKEN not set - функции транскрипции будут недоступны")
        
        # Проверяем базовые пути
        if not self.base_dir.exists():
            try:
                self.base_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create base directory: {e}")
        
        if errors:
            raise ConfigError(f"Critical configuration errors: {'; '.join(errors)}")
    
    def get_schema(self) -> Dict[str, Any]:
        """
        Загружает JSON схему протокола
        
        Returns:
            Dict[str, Any]: Словарь с JSON схемой
            
        Raises:
            FileNotFoundError: Если файл схемы не найден
        """
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema file not found at {self.schema_path}")
        
        with open(self.schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def get_output_dir_for_file(self, file_stem: str) -> Path:
        """
        Создает и возвращает директорию для выходных файлов конкретного аудиофайла
        
        Args:
            file_stem (str): Имя аудиофайла без расширения
            
        Returns:
            Path: Путь к директории
        """
        from datetime import datetime
        
        output_dir = self.output_dir / f"{file_stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    
    def validate_api_tokens(self) -> List[str]:
        """
        Проверяет наличие необходимых API токенов
        
        Returns:
            List[str]: Список отсутствующих токенов
        """
        missing_tokens = []
        
        if not self.replicate_api_token:
            missing_tokens.append("REPLICATE_API_TOKEN")
        
        if not self.openai_api_key:
            missing_tokens.append("OPENAI_API_KEY")
            
        return missing_tokens

# Создание экземпляра конфигурации
config = AppConfig()
