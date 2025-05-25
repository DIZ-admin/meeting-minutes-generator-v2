"""
Утилиты для работы с аудиофайлами
"""
import os
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Any

try:
    from pydub import AudioSegment
except ImportError:
    # Установка pydub, если отсутствует
    import subprocess
    subprocess.check_call(["pip", "install", "pydub"])
    from pydub import AudioSegment

from ..core.exceptions import AudioProcessingError
from ..utils.logging import get_default_logger

logger = get_default_logger(__name__)

def get_audio_info(audio_path: Path) -> Dict[str, Any]:
    """
    Получает информацию об аудиофайле (длительность, битрейт, каналы и т.д.)
    
    Args:
        audio_path: Путь к аудиофайлу
        
    Returns:
        Словарь с информацией об аудиофайле
        
    Raises:
        FileNotFoundError: Если файл не найден
        AudioProcessingError: Если не удалось получить информацию об аудиофайле
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    try:
        # Загружаем аудиофайл с помощью pydub
        audio = AudioSegment.from_file(str(audio_path))
        
        # Собираем информацию
        info = {
            "path": str(audio_path),
            "filename": audio_path.name,
            "duration_ms": len(audio),
            "duration_sec": len(audio) / 1000,
            "channels": audio.channels,
            "sample_width": audio.sample_width,
            "frame_rate": audio.frame_rate,
            "frame_width": audio.frame_width,
            "file_size_bytes": os.path.getsize(audio_path)
        }
        
        return info
        
    except Exception as e:
        error_msg = f"Failed to get audio info: {e}"
        logger.error(error_msg, exc_info=True)
        raise AudioProcessingError(message=error_msg, file_path=str(audio_path)) from e

def convert_audio(
    input_path: Path,
    output_format: str = "wav",
    sample_rate: int = 16000,
    channels: int = 1
) -> Path:
    """
    Конвертирует аудиофайл в указанный формат
    
    Args:
        input_path: Путь к исходному аудиофайлу
        output_format: Целевой формат (wav, mp3, etc.)
        sample_rate: Частота дискретизации в Гц
        channels: Количество каналов (1 - моно, 2 - стерео)
        
    Returns:
        Путь к сконвертированному файлу
        
    Raises:
        FileNotFoundError: Если исходный файл не найден
        AudioProcessingError: Если не удалось сконвертировать аудиофайл
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    
    try:
        # Определяем имя выходного файла
        output_path = input_path.parent / f"{input_path.stem}_converted.{output_format}"
        
        # Загружаем аудиофайл с помощью pydub
        audio = AudioSegment.from_file(str(input_path))
        
        # Применяем конвертацию
        audio = audio.set_frame_rate(sample_rate)
        audio = audio.set_channels(channels)
        
        # Экспортируем результат
        audio.export(
            str(output_path),
            format=output_format
        )
        
        logger.info(f"Converted audio to {output_format}: {output_path}")
        return output_path
        
    except Exception as e:
        error_msg = f"Failed to convert audio: {e}"
        logger.error(error_msg, exc_info=True)
        raise AudioProcessingError(message=error_msg, file_path=str(input_path)) from e

def split_audio(
    input_path: Path,
    segment_length_ms: int = 10 * 60 * 1000,  # 10 минут
    overlap_ms: int = 5000,  # 5 секунд
    output_dir: Optional[Path] = None
) -> List[Path]:
    """
    Разбивает аудиофайл на сегменты указанной длины с перекрытием
    
    Args:
        input_path: Путь к исходному аудиофайлу
        segment_length_ms: Длина сегмента в миллисекундах
        overlap_ms: Длина перекрытия в миллисекундах
        output_dir: Директория для сохранения сегментов
                  (если None, используется директория исходного файла)
        
    Returns:
        Список путей к сегментам
        
    Raises:
        FileNotFoundError: Если исходный файл не найден
        AudioProcessingError: Если не удалось разбить аудиофайл
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    
    try:
        # Определяем директорию для сохранения сегментов
        if output_dir is None:
            output_dir = input_path.parent / f"{input_path.stem}_segments"
        
        # Создаем директорию, если она не существует
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Загружаем аудиофайл с помощью pydub
        audio = AudioSegment.from_file(str(input_path))
        
        # Если длина аудио меньше длины сегмента, возвращаем исходный файл
        if len(audio) <= segment_length_ms:
            logger.info(f"Audio file is shorter than segment length, skipping splitting")
            return [input_path]
        
        # Разбиваем аудио на сегменты
        segments = []
        start = 0
        segment_index = 1
        
        while start < len(audio):
            # Определяем конец сегмента
            end = min(start + segment_length_ms, len(audio))
            
            # Выделяем сегмент
            segment = audio[start:end]
            
            # Определяем имя сегмента
            segment_path = output_dir / f"{input_path.stem}_segment_{segment_index}.{input_path.suffix}"
            
            # Экспортируем сегмент
            segment.export(str(segment_path), format=input_path.suffix.lstrip('.'))
            
            # Добавляем путь к сегменту в список
            segments.append(segment_path)
            
            # Обновляем начало следующего сегмента (с учетом перекрытия)
            start = end - overlap_ms
            
            # Если достигли конца аудио, выходим из цикла
            if end == len(audio):
                break
            
            segment_index += 1
        
        logger.info(f"Split audio into {len(segments)} segments")
        return segments
        
    except Exception as e:
        error_msg = f"Failed to split audio: {e}"
        logger.error(error_msg, exc_info=True)
        raise AudioProcessingError(message=error_msg, file_path=str(input_path)) from e

def detect_silence(
    input_path: Path,
    min_silence_len: int = 1000,  # 1 секунда
    silence_thresh: int = -40,  # dBFS
    keep_silence: int = 500  # 0.5 секунды
) -> List[Tuple[int, int]]:
    """
    Обнаруживает участки тишины в аудиофайле
    
    Args:
        input_path: Путь к аудиофайлу
        min_silence_len: Минимальная длина тишины в миллисекундах
        silence_thresh: Порог тишины в dBFS
        keep_silence: Сколько миллисекунд тишины сохранять с обеих сторон
        
    Returns:
        Список кортежей (start_ms, end_ms) с началом и концом тишины
        
    Raises:
        FileNotFoundError: Если файл не найден
        AudioProcessingError: Если не удалось обнаружить тишину
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    
    try:
        # Загружаем аудиофайл с помощью pydub
        audio = AudioSegment.from_file(str(input_path))
        
        # Обнаруживаем тишину
        from pydub.silence import detect_silence as pydub_detect_silence
        
        silence_ranges = pydub_detect_silence(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=silence_thresh,
            keep_silence=keep_silence
        )
        
        logger.debug(f"Detected {len(silence_ranges)} silence ranges")
        return silence_ranges
        
    except Exception as e:
        error_msg = f"Failed to detect silence: {e}"
        logger.error(error_msg, exc_info=True)
        raise AudioProcessingError(message=error_msg, file_path=str(input_path)) from e

def trim_audio(
    input_path: Path,
    start_ms: int = 0,
    end_ms: Optional[int] = None,
    output_path: Optional[Path] = None
) -> Path:
    """
    Обрезает аудиофайл по указанным временным меткам
    
    Args:
        input_path: Путь к исходному аудиофайлу
        start_ms: Начало обрезки в миллисекундах
        end_ms: Конец обрезки в миллисекундах (если None, то до конца аудио)
        output_path: Путь для сохранения обрезанного аудио
                   (если None, то создается автоматически)
        
    Returns:
        Путь к обрезанному аудиофайлу
        
    Raises:
        FileNotFoundError: Если исходный файл не найден
        AudioProcessingError: Если не удалось обрезать аудиофайл
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    
    try:
        # Загружаем аудиофайл с помощью pydub
        audio = AudioSegment.from_file(str(input_path))
        
        # Определяем конец обрезки, если не указан
        if end_ms is None:
            end_ms = len(audio)
        
        # Обрезаем аудио
        trimmed_audio = audio[start_ms:end_ms]
        
        # Определяем путь для сохранения, если не указан
        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_trimmed{input_path.suffix}"
        
        # Экспортируем обрезанное аудио
        trimmed_audio.export(str(output_path), format=input_path.suffix.lstrip('.'))
        
        logger.info(f"Trimmed audio from {start_ms}ms to {end_ms}ms: {output_path}")
        return output_path
        
    except Exception as e:
        error_msg = f"Failed to trim audio: {e}"
        logger.error(error_msg, exc_info=True)
        raise AudioProcessingError(message=error_msg, file_path=str(input_path)) from e
