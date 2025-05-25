"""
Адаптер для ASR через Replicate API
"""
import os
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Union

try:
    import replicate
    from replicate.exceptions import ReplicateError
except ImportError:
    # Установка replicate, если отсутствует
    import subprocess
    subprocess.check_call(["pip", "install", "replicate"])
    import replicate
    from replicate.exceptions import ReplicateError

from .base import ASRAdapter
from ...core.exceptions import ASRError, ConfigError
from ...utils.logging import get_default_logger
from ...config.config import config

logger = get_default_logger(__name__)

class ReplicateASRAdapter(ASRAdapter):
    """
    Адаптер для ASR через Replicate API
    
    Использует модель whisper-diarization для транскрибации аудио с 
    распознаванием спикеров.
    """
    
    def __init__(
        self, 
        api_token: Optional[str] = None,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: int = 5
    ):
        """
        Инициализирует адаптер для Replicate ASR
        
        Args:
            api_token: Токен API Replicate (если None, берется из конфигурации)
            model_name: Имя модели (если None, берется из конфигурации)
            model_version: Версия модели (если None, берется из конфигурации)
            max_retries: Максимальное количество попыток при ошибке API
            retry_delay: Начальная задержка между попытками в секундах
        
        Raises:
            ConfigError: Если токен API не найден ни в параметрах, ни в конфигурации
        """
        # Проверяем, что токен передан напрямую или доступен в конфигурации
        if api_token is None and (not hasattr(config, 'replicate_api_token') or config.replicate_api_token is None):
            raise ConfigError(
                "Replicate API token not found. Set REPLICATE_API_TOKEN env variable or pass it directly."
            )
            
        self.api_token = api_token or config.replicate_api_token
        self.model_name = model_name or getattr(config, 'replicate_model', 'thomasmol/whisper-diarization')
        self.model_version = model_version or getattr(config, 'replicate_version', 'latest')
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Устанавливаем API токен, если он не None
        if self.api_token is not None:
            os.environ["REPLICATE_API_TOKEN"] = self.api_token
        
        # Формируем идентификатор модели
        self.model_identifier = f"{self.model_name}:{self.model_version}"
        
        logger.debug(f"Initialized ReplicateASRAdapter with model {self.model_identifier}")
    
    def transcribe(
        self, 
        audio_path: Path, 
        language: Optional[str] = None,
        num_speakers: Optional[int] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Транскрибирует аудиофайл используя Replicate API
        
        Args:
            audio_path: Путь к аудиофайлу
            language: Код языка (например, 'de', 'en', None для автоопределения)
            num_speakers: Количество спикеров (None для автоопределения)
            **kwargs: Дополнительные параметры для Replicate API
            
        Returns:
            Список сегментов с транскрипцией, информацией о спикерах и таймкодами
            
        Raises:
            FileNotFoundError: Если аудиофайл не найден
            ASRError: Если произошла ошибка при транскрибации
        """
        # Проверка существования аудиофайла
        if not audio_path.exists():
            error_msg = f"Audio file not found at {audio_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        logger.info(f"Starting transcription of {audio_path} with Replicate ASR")
        logger.debug(f"Language: {language or 'auto'}, Num speakers: {num_speakers or 'auto'}")
        
        retry_count = 0
        current_delay = self.retry_delay
        last_exception = None
        
        while retry_count < self.max_retries:
            try:
                with open(audio_path, "rb") as audio_file:
                    # Подготовка параметров
                    input_params = {
                        "file": audio_file,
                        "language": language or "",  # Пустая строка для автоопределения
                        "num_speakers": 2 if num_speakers is None else num_speakers,  # Явно указываем 2 говорящих
                    }
                    
                    # Добавляем дополнительные параметры
                    input_params.update(kwargs)
                    
                    # Выполнение запроса к API
                    logger.debug(f"Calling Replicate API with model {self.model_identifier}")
                    prediction = replicate.run(
                        self.model_identifier,
                        input=input_params,
                    )
                
                # Проверка результата
                if not prediction or "segments" not in prediction:
                    error_msg = f"Replicate API returned unexpected response: {prediction}"
                    logger.warning(error_msg)
                    # В случае пустого ответа возвращаем пустой список сегментов
                    return []
                
                segments = prediction["segments"]
                logger.info(f"Transcription complete: {len(segments)} segments")
                return segments
                
            except ReplicateError as e:
                last_exception = e
                logger.warning(f"Replicate API error (attempt {retry_count+1}/{self.max_retries}): {e}")
                retry_count += 1
                
                if retry_count < self.max_retries:
                    logger.info(f"Retrying in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= 2  # Экспоненциальное увеличение задержки
            
            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error during transcription: {e}", exc_info=True)
                retry_count += 1
                
                if retry_count < self.max_retries:
                    logger.info(f"Retrying in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= 2
        
        # Если все попытки исчерпаны и ни одна не удалась
        error_msg = f"Failed to transcribe audio after {self.max_retries} attempts"
        logger.error(error_msg)
        
        # Создаем и выбрасываем исключение с деталями
        raise ASRError(
            message=error_msg,
            details={"audio_path": str(audio_path), "language": language},
            api_name="Replicate",
            api_response=getattr(last_exception, "response", None),
        ) from last_exception
    
    def get_adapter_info(self) -> Dict[str, Any]:
        """
        Возвращает информацию об адаптере
        
        Returns:
            Словарь с информацией об адаптере
        """
        return {
            "name": "ReplicateASRAdapter",
            "provider": "Replicate",
            "model": self.model_name,
            "version": self.model_version,
            "features": ["diarization", "timestamps", "language_detection"]
        }
