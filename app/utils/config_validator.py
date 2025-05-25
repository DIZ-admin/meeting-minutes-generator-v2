"""
Утилиты для валидации конфигурации приложения
"""
import os
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..core.exceptions import ConfigError
from ..utils.logging import get_default_logger
from ..config.config import config

logger = get_default_logger(__name__)

def is_config_healthy() -> bool:
    """
    Проверяет, что конфигурация приложения валидна и система готова к работе
    
    Returns:
        bool: True, если конфигурация валидна, иначе False
    """
    validator = ConfigValidator()
    try:
        result = validator.validate_all()
        return len(validator.errors) == 0
    except Exception as e:
        logger.error(f"Ошибка при проверке конфигурации: {e}")
        return False

def get_config_health_status() -> Dict[str, Any]:
    """
    Возвращает детальную информацию о состоянии конфигурации
    
    Returns:
        Dict[str, Any]: Словарь с информацией о состоянии конфигурации
    """
    validator = ConfigValidator()
    try:
        result = validator.validate_all()
        return {
            "healthy": len(validator.errors) == 0,
            "errors": validator.errors,
            "warnings": validator.warnings,
            "details": result
        }
    except Exception as e:
        logger.error(f"Ошибка при проверке конфигурации: {e}")
        return {
            "healthy": False,
            "errors": [str(e)],
            "warnings": [],
            "details": {}
        }

class ConfigValidator:
    """Валидатор конфигурации приложения"""
    
    def __init__(self, config_obj=None):
        """
        Инициализация валидатора
        
        Args:
            config_obj: Объект конфигурации для валидации. Если None, использует глобальный config
        """
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.config = config_obj or config
    
    def validate_all(self) -> Dict[str, Any]:
        """
        Валидирует всю конфигурацию приложения
        
        Returns:
            Dict с результатами валидации
            
        Raises:
            ConfigError: Если найдены критические ошибки конфигурации
        """
        self.errors.clear()
        self.warnings.clear()
        
        # Валидируем API ключи
        self._validate_api_keys()
        
        # Валидируем пути и директории
        self._validate_paths()
        
        # Валидируем настройки моделей
        self._validate_model_settings()
        
        # Валидируем настройки уведомлений
        self._validate_notification_settings()
        
        # Валидируем настройки логирования
        self._validate_logging_settings()
        
        # Собираем результаты
        result = {
            "valid": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self._generate_summary()
        }
        
        # Логируем результаты
        if self.errors:
            logger.error(f"Configuration validation failed with {len(self.errors)} errors")
        if self.warnings:
            logger.warning(f"Configuration has {len(self.warnings)} warnings")
        if len(self.errors) == 0 and len(self.warnings) == 0:
            logger.info("Configuration validation passed successfully")
        
        # Выбрасываем исключение при критических ошибках
        if self.errors:
            raise ConfigError(f"Configuration validation failed: {'; '.join(self.errors)}")
        
        return result
    
    def _validate_api_keys(self) -> None:
        """Валидирует API ключи"""
        # Проверяем наличие обязательных API ключей
        api_keys = {
            "OpenAI API Key": self.config.openai_api_key,
            "Replicate API Token": self.config.replicate_api_token
        }
        
        for key_name, key_value in api_keys.items():
            if not key_value or key_value == "your_api_key_here":
                self.errors.append(f"Missing or invalid {key_name}")
            elif len(key_value) < 10:  # Минимальная длина для API ключа
                self.warnings.append(f"{key_name} seems too short")
        
        # Проверяем опциональные ключи
        optional_keys = {
            "Telegram Bot Token": getattr(self.config, 'telegram_bot_token', None),
            "Telegram Chat ID": getattr(self.config, 'telegram_chat_id', None)
        }
        
        for key_name, key_value in optional_keys.items():
            if key_value and len(str(key_value)) < 5:
                self.warnings.append(f"{key_name} seems invalid")
    
    def _validate_paths(self) -> None:
        """Валидирует пути и директории"""
        # Список критических директорий
        critical_dirs = [
            ("output", self.config.output_dir),
            ("cache", self.config.cache_dir),
            ("logs", self.config.log_dir)
        ]
        
        for dir_name, dir_path in critical_dirs:
            if not dir_path:
                self.errors.append(f"Missing {dir_name} directory path")
                continue
                
            path_obj = Path(dir_path)
            if not path_obj.exists():
                try:
                    path_obj.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created {dir_name} directory: {dir_path}")
                except Exception as e:
                    self.errors.append(f"Cannot create {dir_name} directory {dir_path}: {e}")
            elif not path_obj.is_dir():
                self.errors.append(f"{dir_name} path {dir_path} is not a directory")
            elif not os.access(path_obj, os.W_OK):
                self.errors.append(f"{dir_name} directory {dir_path} is not writable")
        
        # Проверяем опциональные директории
        optional_dirs = [
            ("uploads", getattr(self.config, 'uploads_dir', None)),
            ("templates", getattr(self.config, 'template_dir', None))
        ]
        
        for dir_name, dir_path in optional_dirs:
            if dir_path:
                path_obj = Path(dir_path)
                if not path_obj.exists():
                    self.warnings.append(f"Optional {dir_name} directory {dir_path} does not exist")
    
    def _validate_model_settings(self) -> None:
        """Валидирует настройки моделей"""
        # Проверяем настройки моделей
        model_settings = [
            ("Default language", self.config.default_lang),
            ("ASR model", getattr(self.config, 'asr_model', None)),
            ("LLM model", getattr(self.config, 'llm_model', None))
        ]
        
        for setting_name, setting_value in model_settings:
            if not setting_value:
                self.warnings.append(f"Missing {setting_name} setting")
        
        # Проверяем допустимые языки
        if self.config.default_lang and self.config.default_lang not in ['de', 'en', 'ru']:
            self.warnings.append(f"Unusual default language: {self.config.default_lang}")
    
    def _validate_notification_settings(self) -> None:
        """Валидирует настройки уведомлений"""
        # Проверяем настройки Telegram
        has_telegram_token = hasattr(self.config, 'telegram_bot_token') and self.config.telegram_bot_token
        has_telegram_chat = hasattr(self.config, 'telegram_chat_id') and self.config.telegram_chat_id
        
        if has_telegram_token and not has_telegram_chat:
            self.warnings.append("Telegram bot token provided but chat ID is missing")
        elif has_telegram_chat and not has_telegram_token:
            self.warnings.append("Telegram chat ID provided but bot token is missing")
        elif not has_telegram_token and not has_telegram_chat:
            self.warnings.append("Telegram notifications are not configured")
    
    def _validate_logging_settings(self) -> None:
        """Валидирует настройки логирования"""
        # Проверяем уровень логирования
        log_level = getattr(self.config, 'log_level', 'INFO')
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        
        if log_level not in valid_levels:
            self.warnings.append(f"Invalid log level: {log_level}")
        
        # Проверяем формат логирования
        log_format = getattr(self.config, 'log_format', None)
        if not log_format:
            self.warnings.append("Log format is not specified")
    
    def _generate_summary(self) -> str:
        """Генерирует краткое резюме валидации"""
        if len(self.errors) == 0 and len(self.warnings) == 0:
            return "Configuration is valid and ready for production"
        elif len(self.errors) == 0:
            return f"Configuration is valid with {len(self.warnings)} warnings"
        else:
            return f"Configuration has {len(self.errors)} errors and {len(self.warnings)} warnings"
