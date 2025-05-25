"""
Базовый класс для адаптеров уведомлений
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Optional, Any, Union

class NotificationAdapter(ABC):
    """
    Абстрактный класс для адаптеров уведомлений
    
    Все конкретные реализации адаптеров уведомлений должны наследоваться от этого класса
    и реализовывать его абстрактные методы.
    """
    
    @abstractmethod
    def send_message(self, text: str, **kwargs) -> bool:
        """
        Отправляет текстовое сообщение
        
        Args:
            text: Текст сообщения
            **kwargs: Дополнительные параметры для конкретной реализации
            
        Returns:
            True, если сообщение отправлено успешно, иначе False
            
        Raises:
            NotificationError: Если произошла ошибка при отправке сообщения
        """
        pass
    
    @abstractmethod
    def send_file(self, file_path: Union[str, Path], caption: Optional[str] = None, **kwargs) -> bool:
        """
        Отправляет файл
        
        Args:
            file_path: Путь к файлу
            caption: Подпись к файлу
            **kwargs: Дополнительные параметры для конкретной реализации
            
        Returns:
            True, если файл отправлен успешно, иначе False
            
        Raises:
            NotificationError: Если произошла ошибка при отправке файла
            FileNotFoundError: Если файл не найден
        """
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """
        Проверяет, настроен ли адаптер
        
        Returns:
            True, если адаптер настроен, иначе False
        """
        pass
    
    @abstractmethod
    def get_adapter_info(self) -> Dict[str, Any]:
        """
        Возвращает информацию об адаптере
        
        Returns:
            Словарь с информацией об адаптере (имя, версия, провайдер и т.д.)
        """
        pass
