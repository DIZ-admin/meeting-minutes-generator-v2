#!/usr/bin/env python3
"""
CLI приложение для генерации протоколов совещаний
"""
import argparse
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

# Добавляем родительскую директорию в путь импорта
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

from app.core.services.pipeline import Pipeline
from app.core.exceptions import ASRError, LLMError, ConfigError
from app.utils.logging import get_default_logger
from app.config.config import config

logger = get_default_logger(__name__)

def parse_arguments():
    """
    Парсинг аргументов командной строки
    
    Returns:
        Результат парсинга аргументов
    """
    parser = argparse.ArgumentParser(
        description="Generate meeting minutes from audio recordings",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Основные аргументы
    parser.add_argument(
        "audio",
        help="Path to audio file (wav/m4a/mp3) or directory with audio files"
    )
    
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Process all audio files in the directory (if audio is a directory)"
    )
    
    parser.add_argument(
        "--lang",
        help="Language code (e.g. 'de' for German, default from env var or 'de')"
    )
    
    parser.add_argument(
        "--output",
        help="Output directory (default: ./output/[filename])"
    )
    
    parser.add_argument(
        "--skip_telegram",
        action="store_true",
        help="Skip sending notifications to Telegram"
    )
    
    # Дополнительные аргументы
    parser.add_argument(
        "--title",
        help="Meeting title (default: extracted from filename)"
    )
    
    parser.add_argument(
        "--date",
        help="Meeting date in YYYY-MM-DD format (default: extracted from filename or current date)"
    )
    
    parser.add_argument(
        "--location",
        help="Meeting location (default: 'Online Meeting')"
    )
    
    parser.add_argument(
        "--organizer",
        help="Meeting organizer (default: empty)"
    )
    
    parser.add_argument(
        "--participants",
        help="Comma-separated list of participants"
    )
    
    parser.add_argument(
        "--agenda",
        help="Comma-separated list of agenda items"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    return parser.parse_args()

def prepare_metadata(args) -> Dict[str, Any]:
    """
    Подготавливает метаданные протокола из аргументов командной строки
    
    Args:
        args: Результат парсинга аргументов командной строки
        
    Returns:
        Словарь с метаданными протокола
    """
    metadata = {}
    
    # Базовая информация
    if args.title:
        metadata["title"] = args.title
    
    if args.date:
        metadata["date"] = args.date
    
    if args.location:
        metadata["location"] = args.location
    
    if args.organizer:
        metadata["organizer"] = args.organizer
    
    # Автор
    metadata["author"] = "AI Assistant"
    
    return metadata

def process_single_file(
    pipeline: Pipeline,
    audio_path: Path,
    output_dir: Optional[Path],
    language: Optional[str],
    metadata: Dict[str, Any],
    skip_notifications: bool
) -> bool:
    """
    Обрабатывает один аудиофайл
    
    Args:
        pipeline: Экземпляр Pipeline
        audio_path: Путь к аудиофайлу
        output_dir: Директория для сохранения результатов
        language: Язык аудио
        metadata: Метаданные протокола
        skip_notifications: Пропустить отправку уведомлений
        
    Returns:
        True, если обработка выполнена успешно, иначе False
    """
    try:
        logger.info(f"Processing audio file: {audio_path}")
        
        # Обрабатываем аудиофайл
        md_file, json_file = pipeline.process_audio(
            audio_path=audio_path,
            output_dir=output_dir,
            language=language,
            metadata=metadata,
            skip_notifications=skip_notifications
        )
        
        logger.info(f"Processing completed successfully")
        logger.info(f"Output files:")
        logger.info(f"  - Markdown: {md_file}")
        logger.info(f"  - JSON: {json_file}")
        
        return True
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return False
        
    except ASRError as e:
        logger.error(f"ASR error: {e}")
        return False
        
    except LLMError as e:
        logger.error(f"LLM error: {e}")
        return False
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return False

def process_batch(
    pipeline: Pipeline,
    directory_path: Path,
    output_dir: Optional[Path],
    language: Optional[str],
    metadata: Optional[Dict[str, Any]],
    skip_notifications: bool
) -> bool:
    """
    Обрабатывает все аудиофайлы в директории
    
    Args:
        pipeline: Экземпляр Pipeline
        directory_path: Путь к директории с аудиофайлами
        output_dir: Директория для сохранения результатов
        language: Язык аудио
        metadata: Общие метаданные для всех протоколов
        skip_notifications: Пропустить отправку уведомлений
        
    Returns:
        True, если все файлы обработаны успешно, иначе False
    """
    try:
        logger.info(f"Processing audio files in directory: {directory_path}")
        
        # Собираем все аудиофайлы в директории
        audio_extensions = [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"]
        audio_files = [
            path for path in directory_path.iterdir()
            if path.is_file() and path.suffix.lower() in audio_extensions
        ]
        
        if not audio_files:
            logger.warning(f"No audio files found in directory: {directory_path}")
            return False
        
        logger.info(f"Found {len(audio_files)} audio files")
        
        # Обрабатываем каждый файл
        results = pipeline.process_batch(
            audio_files=audio_files,
            output_dir=output_dir,
            language=language,
            metadata=metadata,
            skip_notifications=skip_notifications
        )
        
        # Проверяем результаты
        if not results:
            logger.warning("No files were processed successfully")
            return False
        
        logger.info(f"Successfully processed {len(results)} out of {len(audio_files)} files")
        
        return len(results) == len(audio_files)
        
    except Exception as e:
        logger.error(f"Unexpected error during batch processing: {e}", exc_info=True)
        return False

def main():
    """
    Основная функция CLI-приложения
    """
    # Парсим аргументы командной строки
    args = parse_arguments()
    
    # Настраиваем логирование
    if args.debug:
        os.environ["LOG_LEVEL"] = "DEBUG"
    
    # Инициализируем конвейер
    try:
        pipeline = Pipeline()
        
        # Подготавливаем пути
        audio_path = Path(args.audio)
        output_dir = Path(args.output) if args.output else None
        
        # Подготавливаем метаданные протокола
        metadata = prepare_metadata(args)
        
        # Определяем режим обработки (одиночный файл или пакетный)
        if audio_path.is_dir() and args.batch:
            # Пакетная обработка всех файлов в директории
            success = process_batch(
                pipeline=pipeline,
                directory_path=audio_path,
                output_dir=output_dir,
                language=args.lang,
                metadata=metadata,
                skip_notifications=args.skip_telegram
            )
        else:
            # Обработка одиночного файла
            success = process_single_file(
                pipeline=pipeline,
                audio_path=audio_path,
                output_dir=output_dir,
                language=args.lang,
                metadata=metadata,
                skip_notifications=args.skip_telegram
            )
        
        # Завершаем программу с соответствующим кодом
        sys.exit(0 if success else 1)
        
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(2)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(3)

if __name__ == "__main__":
    main()
