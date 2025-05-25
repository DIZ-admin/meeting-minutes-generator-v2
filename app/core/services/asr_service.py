"""
Сервис для распознавания речи (ASR)
"""
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Type, Union

from ...adapters.asr.base import ASRAdapter
from ...adapters.asr.replicate_adapter import ReplicateASRAdapter
from ...adapters.asr.openai_adapter import OpenAIASRAdapter
from ...core.exceptions import ASRError, ConfigError
from ...utils.logging import get_default_logger
from ...utils.cache import get_cache, generate_content_hash, cache_asr_result, get_cached_asr_result
from ...config.config import config

logger = get_default_logger(__name__)

class ASRService:
    """
    Сервис для распознавания речи, который использует различные адаптеры ASR.
    
    Предоставляет унифицированный интерфейс для транскрибации аудио с помощью
    различных провайдеров ASR.
    """
    
    def __init__(
        self, 
        adapter: Optional[ASRAdapter] = None,
        adapter_type: str = "replicate"
    ):
        """
        Инициализирует сервис ASR с заданным адаптером
        
        Args:
            adapter: Адаптер ASR для использования. Если None, создается адаптер
                  на основе adapter_type
            adapter_type: Тип адаптера для создания, если adapter=None.
                        Возможные значения: "replicate", "openai"
        
        Raises:
            ConfigError: Если не удалось создать адаптер по умолчанию
            ValueError: Если указан неизвестный тип адаптера
        """
        if adapter:
            self.adapter = adapter
        else:
            try:
                if adapter_type.lower() == "replicate":
                    # Создаем адаптер Replicate
                    self.adapter = ReplicateASRAdapter()
                    logger.debug("Using ReplicateASRAdapter")
                elif adapter_type.lower() == "openai":
                    # Создаем адаптер OpenAI
                    self.adapter = OpenAIASRAdapter()
                    logger.debug("Using OpenAIASRAdapter")
                else:
                    error_msg = f"Unknown adapter type: {adapter_type}. Supported types: replicate, openai"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
            except ConfigError as e:
                error_msg = f"Failed to initialize ASR adapter: {e}"
                logger.error(error_msg)
                raise ConfigError(error_msg) from e
        
        logger.info(f"ASRService initialized with {type(self.adapter).__name__}")
    
    def transcribe(
        self, 
        audio_path: Union[str, Path], 
        language: Optional[str] = None,
        use_cache: bool = True,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Транскрибирует аудиофайл, используя текущий адаптер ASR
        
        Args:
            audio_path: Путь к аудиофайлу (строка или объект Path)
            language: Код языка (например, 'de', 'en', None для автоопределения)
            use_cache: Использовать кеширование для этого запроса
            **kwargs: Дополнительные параметры для адаптера
            
        Returns:
            Список сегментов с транскрипцией
            
        Raises:
            FileNotFoundError: Если аудиофайл не найден
            ASRError: Если произошла ошибка при транскрибации
        """
        # Преобразуем строку пути в объект Path, если необходимо
        if isinstance(audio_path, str):
            audio_path = Path(audio_path)
        
        # Если язык не указан, используем язык по умолчанию из конфигурации
        if language is None:
            language = config.default_lang
            logger.debug(f"Using default language: {language}")
        
        # Логируем начало транскрибации
        logger.info(f"Starting transcription of {audio_path}")
        
        # Попытаемся получить результат из кеша, если кеширование включено
        cache_key = None
        if use_cache:
            try:
                # Генерируем ключ кеша на основе пути к файлу и параметров
                file_hash = generate_content_hash(str(audio_path))
                cache_params = {"language": language, **kwargs}
                cache_key = f"{file_hash}_{hash(str(sorted(cache_params.items())))}"
                
                # Проверяем кеш
                cached_result = get_cached_asr_result(cache_key)
                if cached_result is not None:
                    logger.info(f"Using cached transcription result for {audio_path}")
                    return cached_result
                    
            except Exception as e:
                logger.warning(f"Cache lookup failed for {audio_path}: {e}")
                # Продолжаем без кеша в случае ошибки
        
        try:
            # Делегируем работу адаптеру
            segments = self.adapter.transcribe(audio_path, language=language, **kwargs)
            
            # Сохраняем результат в кеш, если кеширование включено
            if use_cache and cache_key:
                try:
                    cache_asr_result(cache_key, segments)
                    logger.debug(f"Cached transcription result for {audio_path}")
                except Exception as e:
                    logger.warning(f"Failed to cache transcription result: {e}")
            
            logger.info(f"Transcription complete: {len(segments)} segments")
            return segments
            
        except ASRError as e:
            # Просто пробрасываем ASRError дальше
            logger.error(f"ASR error during transcription: {e}")
            raise
            
        except Exception as e:
            # Оборачиваем прочие исключения в ASRError
            error_msg = f"Unexpected error during transcription: {e}"
            logger.error(error_msg, exc_info=True)
            
            raise ASRError(
                message=error_msg,
                details={"audio_path": str(audio_path), "language": language},
            ) from e
    
    def change_adapter(self, adapter: ASRAdapter) -> None:
        """
        Изменяет текущий адаптер ASR
        
        Args:
            adapter: Новый адаптер ASR для использования
        """
        self.adapter = adapter
        logger.info(f"Changed ASR adapter to {type(adapter).__name__}")
    
    def get_adapter_info(self) -> Dict[str, Any]:
        """
        Возвращает информацию о текущем адаптере
        
        Returns:
            Словарь с информацией о текущем адаптере
        """
        return self.adapter.get_adapter_info()
