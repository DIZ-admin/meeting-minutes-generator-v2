"""
Базовый класс для адаптеров языковых моделей (LLM)
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union

class LLMAdapter(ABC):
    """
    Абстрактный класс для адаптеров языковых моделей (LLM)
    
    Все конкретные реализации LLM должны наследоваться от этого класса
    и реализовывать его абстрактные методы.
    """
    
    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Генерирует текст на основе промпта
        
        Args:
            prompt: Основной промпт для генерации
            system_message: Системное сообщение для контекста
            temperature: Температура семплирования (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе
            **kwargs: Дополнительные параметры для конкретной реализации
            
        Returns:
            Сгенерированный текст
            
        Raises:
            LLMError: Если произошла ошибка при генерации текста
        """
        pass
    
    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.3,
        schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Генерирует JSON на основе промпта
        
        Args:
            prompt: Основной промпт для генерации
            system_message: Системное сообщение для контекста
            temperature: Температура семплирования (0.0 - 1.0)
            schema: Опциональная JSON-схема для валидации ответа
            **kwargs: Дополнительные параметры для конкретной реализации
            
        Returns:
            Сгенерированный JSON как словарь Python
            
        Raises:
            LLMError: Если произошла ошибка при генерации JSON
            ValidationError: Если сгенерированный JSON не соответствует схеме
        """
        pass
    
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """
        Подсчитывает количество токенов в тексте
        
        Args:
            text: Текст для подсчета токенов
            
        Returns:
            Количество токенов
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
