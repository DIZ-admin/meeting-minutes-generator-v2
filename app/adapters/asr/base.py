"""
Базовый класс для адаптеров ASR (Automatic Speech Recognition)
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Optional, Any, Union

class ASRAdapter(ABC):
    """
    Абстрактный класс для адаптеров ASR (Automatic Speech Recognition)
    
    Все конкретные реализации ASR должны наследоваться от этого класса
    и реализовывать его абстрактные методы.
    """
    
    @abstractmethod
    def transcribe(self, audio_path: Path, language: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Транскрибирует аудиофайл в текст с распознаванием спикеров
        
        Args:
            audio_path: Путь к аудиофайлу
            language: Код языка (например, 'de', 'en')
            **kwargs: Дополнительные параметры для конкретной реализации
            
        Returns:
            Список сегментов транскрипции с информацией о спикерах и таймштампах
            
        Raises:
            FileNotFoundError: Если аудиофайл не найден
            ASRError: Если произошла ошибка при транскрибации
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
