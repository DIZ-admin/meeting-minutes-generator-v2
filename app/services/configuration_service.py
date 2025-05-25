#!/usr/bin/env python3
"""
Configuration Service - сервис для управления конфигурацией приложения
Применяет Service Layer pattern для configuration management
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

from app.utils.logging import get_default_logger
from app.config.config import config

logger = get_default_logger(__name__)

@dataclass
class ConfigurationSnapshot:
    """Снимок конфигурации в определенный момент времени"""
    timestamp: datetime
    environment: str
    version: str
    settings: Dict[str, Any]
    validation_status: bool
    errors: List[str]

class ConfigurationService:
    """
    Сервис для управления конфигурацией приложения
    Обеспечивает централизованное управление настройками
    """
    
    def __init__(self):
        """Инициализация сервиса конфигурации"""
        self.logger = get_default_logger(self.__class__.__name__)
        self._config_cache: Optional[Dict[str, Any]] = None
        self._last_reload: Optional[datetime] = None
        self._config_snapshots: List[ConfigurationSnapshot] = []
    
    def get_current_config(self) -> Dict[str, Any]:
        """
        Получает текущую конфигурацию
        
        Returns:
            Словарь с текущими настройками
        """
        try:
            # Используем кешированную конфигурацию если доступна
            if self._config_cache is None or self._should_reload_config():
                self._reload_config()
            
            return self._config_cache.copy() if self._config_cache else {}
            
        except Exception as e:
            self.logger.error(f"Error getting current config: {e}")
            return {}
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Получает значение конфигурации по ключу
        
        Args:
            key: Ключ конфигурации (поддерживает dot notation)
            default: Значение по умолчанию
            
        Returns:
            Значение конфигурации или default
        """
        try:
            current_config = self.get_current_config()
            
            # Обрабатываем dot notation
            keys = key.split('.')
            value = current_config
            
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            
            return value
            
        except Exception as e:
            self.logger.error(f"Error getting config value for key '{key}': {e}")
            return default
    
    def validate_configuration(self) -> Tuple[bool, List[str]]:
        """
        Валидирует текущую конфигурацию
        
        Returns:
            Кортеж (валидна, список_ошибок)
        """
        errors = []
        
        try:
            # Проверяем обязательные настройки
            required_settings = [
                'OPENAI_API_KEY'
            ]
            
            current_config = self.get_current_config()
            
            for setting in required_settings:
                value = self.get_config_value(setting)
                if value is None or (isinstance(value, str) and not value.strip()):
                    errors.append(f"Required setting '{setting}' is missing or empty")
            
            # Проверяем API ключи (только наличие, не валидность)
            api_key = self.get_config_value('OPENAI_API_KEY')
            if api_key and len(str(api_key)) < 10:
                errors.append("OPENAI_API_KEY appears to be invalid (too short)")
            
            is_valid = len(errors) == 0
            
            if is_valid:
                self.logger.info("Configuration validation passed")
            else:
                self.logger.warning(f"Configuration validation failed with {len(errors)} errors")
            
            return is_valid, errors
            
        except Exception as e:
            error_msg = f"Error during configuration validation: {e}"
            self.logger.error(error_msg)
            errors.append(error_msg)
            return False, errors
    
    def create_snapshot(self) -> ConfigurationSnapshot:
        """
        Создает снимок текущей конфигурации
        
        Returns:
            Снимок конфигурации
        """
        try:
            current_config = self.get_current_config()
            is_valid, validation_errors = self.validate_configuration()
            
            snapshot = ConfigurationSnapshot(
                timestamp=datetime.now(),
                environment=os.getenv('ENVIRONMENT', 'development'),
                version=getattr(config, 'app_version', 'unknown'),
                settings=current_config,
                validation_status=is_valid,
                errors=validation_errors
            )
            
            # Сохраняем снимок в истории
            self._config_snapshots.append(snapshot)
            
            # Ограничиваем количество снимков
            if len(self._config_snapshots) > 10:
                self._config_snapshots = self._config_snapshots[-10:]
            
            self.logger.info(f"Created configuration snapshot at {snapshot.timestamp}")
            return snapshot
            
        except Exception as e:
            self.logger.error(f"Error creating configuration snapshot: {e}")
            return ConfigurationSnapshot(
                timestamp=datetime.now(),
                environment='unknown',
                version='unknown',
                settings={},
                validation_status=False,
                errors=[str(e)]
            )
    
    def _should_reload_config(self) -> bool:
        """Определяет, нужно ли перезагружать конфигурацию"""
        # В development режиме перезагружаем чаще
        if os.getenv('ENVIRONMENT') == 'development':
            return True
        
        # В production перезагружаем реже
        if self._last_reload is None:
            return True
        
        # Перезагружаем каждые 5 минут
        return (datetime.now() - self._last_reload).seconds > 300
    
    def _reload_config(self):
        """Перезагружает конфигурацию"""
        try:
            # Собираем конфигурацию из различных источников
            self._config_cache = {
                'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
                'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
                'ENVIRONMENT': os.getenv('ENVIRONMENT', 'development'),
                'LOG_LEVEL': os.getenv('LOG_LEVEL', 'INFO'),
                'app': {
                    'version': getattr(config, 'app_version', 'unknown')
                }
            }
            
            self._last_reload = datetime.now()
            self.logger.debug("Configuration reloaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}")
            self._config_cache = {}

# Глобальный экземпляр для использования в приложении
_configuration_service = ConfigurationService()

def get_configuration_service() -> ConfigurationService:
    """Dependency для получения сервиса конфигурации"""
    return _configuration_service
