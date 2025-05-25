#!/usr/bin/env python3
"""
CLI приложение для генерации протоколов совещаний (refactored version)
Использует общий AudioFileProcessor для устранения дублирования кода
"""
import argparse
import sys
import os
from pathlib import Path

# Добавляем родительскую директорию в путь импорта
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

from app.core.services.pipeline import Pipeline
from app.core.exceptions import ConfigError
from app.utils.logging import get_default_logger
from app.config.config import config
from app.cli_services.file_processor import AudioFileProcessor, MetadataBuilder

logger = get_default_logger(__name__)

def parse_arguments():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(
        description="Generate meeting minutes from audio recordings",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Основные аргументы
    parser.add_argument("audio", help="Path to audio file or directory")
    parser.add_argument("--batch", action="store_true", help="Process all files in directory")
    parser.add_argument("--lang", help="Language code (default from env or 'de')")
    parser.add_argument("--output", help="Output directory")
    parser.add_argument("--skip_telegram", action="store_true", help="Skip Telegram notifications")
    
    # Метаданные совещания
    parser.add_argument("--title", help="Meeting title")
    parser.add_argument("--date", help="Meeting date (YYYY-MM-DD)")
    parser.add_argument("--location", help="Meeting location")
    parser.add_argument("--organizer", help="Meeting organizer")
    parser.add_argument("--participants", help="Comma-separated participants")
    parser.add_argument("--agenda", help="Comma-separated agenda items")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    return parser.parse_args()

def main():
    """Основная функция CLI-приложения"""
    # Парсим аргументы
    args = parse_arguments()
    
    # Настраиваем логирование
    if args.debug:
        os.environ["LOG_LEVEL"] = "DEBUG"
    
    try:
        # Инициализируем конвейер и процессор
        pipeline = Pipeline()
        processor = AudioFileProcessor(pipeline)
        
        # Подготавливаем пути и метаданные
        audio_path = Path(args.audio)
        output_dir = Path(args.output) if args.output else None
        metadata = MetadataBuilder.from_cli_args(**vars(args))
        
        # Определяем режим обработки
        if audio_path.is_dir() and args.batch:
            # Пакетная обработка директории
            success, results, message = processor.process_batch(
                directory_path=audio_path,
                output_dir=output_dir,
                language=args.lang,
                metadata=metadata,
                skip_notifications=args.skip_telegram
            )
            logger.info(message)
            
        else:
            # Обработка одиночного файла
            success, md_file, json_file, error_msg = processor.process_single_file(
                audio_path=audio_path,
                output_dir=output_dir,
                language=args.lang,
                metadata=metadata,
                skip_notifications=args.skip_telegram
            )
            
            if success:
                logger.info(f"Output files: MD={md_file}, JSON={json_file}")
            else:
                logger.error(error_msg)
        
        # Завершаем с соответствующим кодом
        sys.exit(0 if success else 1)
        
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(2)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(3)

if __name__ == "__main__":
    main()
