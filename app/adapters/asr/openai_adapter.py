"""
Адаптер для ASR через OpenAI API (Whisper)
"""
import os
import time
import json
from pathlib import Path
from typing import List, Dict, Optional, Any, Union

import openai
from openai import OpenAI
from openai import APIError as OpenAI_APIError 
from openai import RateLimitError as OpenAI_RateLimitError
from openai import OpenAIError

from .base import ASRAdapter
from ...core.exceptions import ASRError, ConfigError
from ...utils.logging import get_default_logger
from ...config.config import config

logger = get_default_logger(__name__)

class OpenAIASRAdapter(ASRAdapter):
    """
    Адаптер для ASR через OpenAI API (Whisper)
    
    Использует модель Whisper через OpenAI API для транскрибации аудио.
    Примечание: OpenAI Whisper API не поддерживает диаризацию (распознавание спикеров),
    поэтому все сегменты будут иметь одинаковый speaker_id = "SPEAKER_00".
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "whisper-1",
        max_retries: int = 3,
        retry_delay: int = 5,
        timeout: int = 60
    ):
        """
        Инициализирует адаптер для OpenAI ASR
        
        Args:
            api_key: API ключ OpenAI (если None, берется из конфигурации)
            model: Модель Whisper для использования
            max_retries: Максимальное количество попыток при ошибке API
            retry_delay: Начальная задержка между попытками в секундах
            timeout: Таймаут для запросов к API в секундах
        
        Raises:
            ConfigError: Если API ключ не найден ни в параметрах, ни в конфигурации
        """
        self.api_key = api_key or config.openai_api_key
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        
        if not self.api_key:
            raise ConfigError(
                "OpenAI API key not found. Set OPENAI_API_KEY env variable or pass it directly."
            )
        
        # Инициализация клиента OpenAI
        self.client = OpenAI(api_key=self.api_key, timeout=self.timeout)
        
        logger.debug(f"Initialized OpenAIASRAdapter with model {self.model}")
    
    def transcribe(
        self, 
        audio_path: Path, 
        language: Optional[str] = None,
        response_format: str = "verbose_json",
        timestamp_granularities: List[str] = ["segment"],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Транскрибирует аудиофайл используя OpenAI API (Whisper)
        
        Args:
            audio_path: Путь к аудиофайлу
            language: Код языка (например, 'de', 'en', None для автоопределения)
            response_format: Формат ответа API
            timestamp_granularities: Уровни детализации временных меток
            **kwargs: Дополнительные параметры для OpenAI API
            
        Returns:
            Список сегментов с транскрипцией и таймкодами (без диаризации)
            
        Raises:
            FileNotFoundError: Если аудиофайл не найден
            ASRError: Если произошла ошибка при транскрибации
        """
        # Проверка существования аудиофайла
        if not audio_path.exists():
            error_msg = f"Audio file not found at {audio_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        logger.info(f"Starting transcription of {audio_path} with OpenAI ASR (Whisper)")
        logger.debug(f"Language: {language or 'auto'}")
        
        retry_count = 0
        current_delay = self.retry_delay
        last_exception = None
        
        while retry_count < self.max_retries:
            try:
                with open(audio_path, "rb") as audio_file:
                    # Подготовка параметров
                    request_params = {
                        "file": audio_file,
                        "model": self.model,
                        "response_format": response_format,
                        "timestamp_granularities": timestamp_granularities
                    }
                    
                    # Добавляем язык, если указан
                    if language:
                        request_params["language"] = language
                    
                    # Добавляем дополнительные параметры
                    request_params.update(kwargs)
                    
                    # Выполнение запроса к API
                    logger.debug(f"Calling OpenAI API with model {self.model}")
                    response = self.client.audio.transcriptions.create(**request_params)
                
                # Преобразование ответа в формат, совместимый с ReplicateASRAdapter
                if response_format == "verbose_json":
                    # Для verbose_json формата получаем объект JSON
                    result = response
                elif response_format == "json":
                    # Для json формата получаем словарь
                    result = response
                else:
                    # Для других форматов (text, srt, vtt) получаем строку
                    # Конвертируем в наш формат с одним сегментом
                    result = {"segments": [{"text": str(response)}]}
                
                # Преобразуем в формат сегментов
                segments = self._convert_to_segments(result)
                logger.info(f"Transcription complete: {len(segments)} segments")
                return segments
                
            except (OpenAIError, OpenAI_APIError, OpenAI_RateLimitError) as e:
                last_exception = e
                logger.warning(f"OpenAI API error (attempt {retry_count+1}/{self.max_retries}): {e}")
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
            api_name="OpenAI Whisper",
            api_response=str(last_exception),
        ) from last_exception
    
    def _convert_to_segments(self, result: Any) -> List[Dict[str, Any]]:
        """
        Преобразует ответ OpenAI API в формат сегментов, совместимый с ReplicateASRAdapter
        
        Args:
            result: Ответ от OpenAI API
            
        Returns:
            Список сегментов с транскрипцией и таймкодами
        """
        segments = []
        
        # Если формат уже verbose_json
        if hasattr(result, 'segments'):
            for idx, segment in enumerate(result.segments):
                segments.append({
                    "segment_id": idx,
                    "text": segment.text,
                    "start": segment.start,
                    "end": segment.end,
                    "speaker_id": "SPEAKER_00",  # OpenAI Whisper не поддерживает диаризацию
                    "confidence": getattr(segment, "confidence", 1.0)
                })
        # Если формат json
        elif isinstance(result, dict) and "segments" in result:
            for idx, segment in enumerate(result["segments"]):
                segments.append({
                    "segment_id": idx,
                    "text": segment["text"],
                    "start": segment.get("start", 0),
                    "end": segment.get("end", 0),
                    "speaker_id": "SPEAKER_00",  # OpenAI Whisper не поддерживает диаризацию
                    "confidence": segment.get("confidence", 1.0)
                })
        # Если нет сегментов, создаем один сегмент с полным текстом
        else:
            text = str(result)
            segments.append({
                "segment_id": 0,
                "text": text,
                "start": 0,
                "end": 0,
                "speaker_id": "SPEAKER_00",
                "confidence": 1.0
            })
        
        return segments
    
    def get_adapter_info(self) -> Dict[str, Any]:
        """
        Возвращает информацию об адаптере
        
        Returns:
            Словарь с информацией об адаптере
        """
        return {
            "name": "OpenAIASRAdapter",
            "provider": "OpenAI",
            "model": self.model,
            "features": ["timestamps"],
            "limitations": ["no_diarization"]  # OpenAI Whisper не поддерживает диаризацию
        }
