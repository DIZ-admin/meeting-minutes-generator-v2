"""
Сервис для отправки уведомлений
"""
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Type

from ...adapters.notifications.base import NotificationAdapter
from ...adapters.notifications.telegram_adapter import TelegramNotificationAdapter
from ...core.exceptions import NotificationError, ConfigError
from ...utils.logging import get_default_logger
from ...config.config import config

logger = get_default_logger(__name__)

class NotificationService:
    """
    Сервис для отправки уведомлений через различные каналы
    
    Предоставляет унифицированный интерфейс для отправки уведомлений
    с использованием различных адаптеров.
    """
    
    def __init__(
        self, 
        default_adapter: Optional[NotificationAdapter] = None,
        adapters: Optional[List[NotificationAdapter]] = None
    ):
        """
        Инициализирует сервис уведомлений
        
        Args:
            default_adapter: Адаптер по умолчанию для отправки уведомлений
            adapters: Список дополнительных адаптеров для использования
            
        Raises:
            ConfigError: Если не удалось создать адаптер по умолчанию
        """
        self.adapters = adapters or []
        
        # Если передан адаптер по умолчанию, используем его
        if default_adapter:
            self.default_adapter = default_adapter
            if default_adapter not in self.adapters:
                self.adapters.append(default_adapter)
        else:
            # Иначе пытаемся создать TelegramNotificationAdapter как адаптер по умолчанию
            try:
                self.default_adapter = TelegramNotificationAdapter()
                if self.default_adapter.is_configured():
                    logger.debug("Using TelegramNotificationAdapter as default")
                    if self.default_adapter not in self.adapters:
                        self.adapters.append(self.default_adapter)
                else:
                    logger.warning("TelegramNotificationAdapter is not configured, no default adapter")
                    self.default_adapter = None
            except Exception as e:
                logger.warning(f"Failed to initialize default notification adapter: {e}")
                self.default_adapter = None
        
        # Проверяем, есть ли хоть один настроенный адаптер
        self.has_configured_adapters = any(adapter.is_configured() for adapter in self.adapters)
        
        if not self.has_configured_adapters:
            logger.warning("No configured notification adapters available")
        else:
            logger.info(f"NotificationService initialized with {len(self.adapters)} adapters")
            logger.debug(f"Available adapters: {', '.join(type(a).__name__ for a in self.adapters if a.is_configured())}")
    
    def is_enabled(self) -> bool:
        """
        Проверяет, включены ли уведомления
        
        Returns:
            True, если есть хотя бы один настроенный адаптер, иначе False
        """
        return self.has_configured_adapters and self.default_adapter is not None
    
    def send_message(
        self, 
        text: str, 
        adapter: Optional[NotificationAdapter] = None,
        **kwargs
    ) -> bool:
        """
        Отправляет текстовое сообщение через указанный адаптер
        
        Args:
            text: Текст сообщения
            adapter: Адаптер для отправки (если None, используется адаптер по умолчанию)
            **kwargs: Дополнительные параметры для адаптера
            
        Returns:
            True, если сообщение отправлено успешно, иначе False
            
        Raises:
            NotificationError: Если произошла ошибка при отправке сообщения
            ConfigError: Если адаптер не указан и нет адаптера по умолчанию
        """
        # Выбираем адаптер
        notification_adapter = self._get_adapter(adapter)
        
        logger.debug(f"Sending message using {type(notification_adapter).__name__}")
        
        try:
            # Отправляем сообщение через выбранный адаптер
            return notification_adapter.send_message(text, **kwargs)
        except Exception as e:
            error_msg = f"Error sending message: {e}"
            logger.error(error_msg, exc_info=True)
            
            # Пробрасываем исключение дальше
            if isinstance(e, NotificationError):
                raise
            else:
                raise NotificationError(message=error_msg) from e
    
    def send_file(
        self, 
        file_path: Union[str, Path], 
        caption: Optional[str] = None, 
        adapter: Optional[NotificationAdapter] = None,
        **kwargs
    ) -> bool:
        """
        Отправляет файл через указанный адаптер
        
        Args:
            file_path: Путь к файлу
            caption: Подпись к файлу
            adapter: Адаптер для отправки (если None, используется адаптер по умолчанию)
            **kwargs: Дополнительные параметры для адаптера
            
        Returns:
            True, если файл отправлен успешно, иначе False
            
        Raises:
            NotificationError: Если произошла ошибка при отправке файла
            ConfigError: Если адаптер не указан и нет адаптера по умолчанию
            FileNotFoundError: Если файл не найден
        """
        # Преобразуем путь к файлу в объект Path
        if isinstance(file_path, str):
            file_path = Path(file_path)
        
        # Проверяем существование файла
        if not file_path.exists():
            error_msg = f"File not found: {file_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # Выбираем адаптер
        notification_adapter = self._get_adapter(adapter)
        
        logger.debug(f"Sending file {file_path} using {type(notification_adapter).__name__}")
        
        try:
            # Отправляем файл через выбранный адаптер
            return notification_adapter.send_file(file_path, caption, **kwargs)
        except Exception as e:
            error_msg = f"Error sending file: {e}"
            logger.error(error_msg, exc_info=True)
            
            # Пробрасываем исключение дальше
            if isinstance(e, NotificationError):
                raise
            else:
                raise NotificationError(message=error_msg) from e
    
    def add_adapter(self, adapter: NotificationAdapter) -> None:
        """
        Добавляет новый адаптер в список доступных адаптеров
        
        Args:
            adapter: Адаптер для добавления
        """
        if adapter not in self.adapters:
            self.adapters.append(adapter)
            
            # Обновляем флаг наличия настроенных адаптеров
            if adapter.is_configured():
                self.has_configured_adapters = True
                
            logger.debug(f"Added {type(adapter).__name__} to notification adapters")
    
    def set_default_adapter(self, adapter: NotificationAdapter) -> None:
        """
        Устанавливает адаптер по умолчанию
        
        Args:
            adapter: Адаптер для использования по умолчанию
        """
        self.default_adapter = adapter
        
        # Добавляем адаптер в список, если его там еще нет
        if adapter not in self.adapters:
            self.adapters.append(adapter)
            
            # Обновляем флаг наличия настроенных адаптеров
            if adapter.is_configured():
                self.has_configured_adapters = True
                
        logger.debug(f"Set {type(adapter).__name__} as default notification adapter")
    
    def get_available_adapters(self) -> List[Dict[str, Any]]:
        """
        Возвращает информацию о доступных адаптерах
        
        Returns:
            Список словарей с информацией об адаптерах
        """
        adapters_info = []
        
        for adapter in self.adapters:
            adapter_info = adapter.get_adapter_info()
            adapter_info["is_default"] = adapter is self.default_adapter
            adapters_info.append(adapter_info)
            
        return adapters_info
    
    def has_available_adapters(self) -> bool:
        """
        Проверяет, есть ли хотя бы один настроенный адаптер
        
        Returns:
            True, если есть хотя бы один настроенный адаптер, иначе False
        """
        return self.has_configured_adapters
    
    def _get_adapter(self, adapter: Optional[NotificationAdapter] = None) -> NotificationAdapter:
        """
        Выбирает адаптер для отправки уведомлений
        
        Args:
            adapter: Адаптер для использования (если None, используется адаптер по умолчанию)
            
        Returns:
            Адаптер для отправки уведомлений
            
        Raises:
            ConfigError: Если адаптер не указан и нет адаптера по умолчанию
        """
        if adapter:
            return adapter
            
        if self.default_adapter and self.default_adapter.is_configured():
            return self.default_adapter
            
        # Ищем первый настроенный адаптер
        for adapter in self.adapters:
            if adapter.is_configured():
                logger.debug(f"Using {type(adapter).__name__} as fallback adapter")
                return adapter
                
        # Если нет настроенных адаптеров, выбрасываем исключение
        error_msg = "No configured notification adapter available"
        logger.error(error_msg)
        raise ConfigError(error_msg)
