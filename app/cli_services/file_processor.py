#!/usr/bin/env python3
"""
Общий сервис для обработки файлов через CLI
Объединяет логику, которая дублировалась между cli.py и cli_typer.py
"""
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Tuple
from datetime import datetime

from app.core.services.pipeline import Pipeline
from app.core.exceptions import ASRError, LLMError, ConfigError
from app.utils.logging import get_default_logger

logger = get_default_logger(__name__)

class AudioFileProcessor:
    """
    Сервис для обработки аудиофайлов через Pipeline
    Изолирует бизнес-логику от UI-логики
    """
    
    def __init__(self, pipeline: Pipeline):
        """Инициализация процессора"""
        self.pipeline = pipeline
    
    def process_single_file(
        self,
        audio_path: Path,
        output_dir: Optional[Path] = None,
        language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        skip_notifications: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Tuple[bool, Optional[Path], Optional[Path], Optional[str]]:
        """Обрабатывает один аудиофайл"""
        try:
            logger.info(f"Processing audio file: {audio_path}")
            
            # Обрабатываем аудиофайл
            if progress_callback:
                md_file, json_file = self.pipeline.process_audio(
                    audio_path=audio_path,
                    output_dir=output_dir,
                    language=language,
                    meeting_info=metadata or {},
                    skip_notifications=skip_notifications,
                    progress_callback=progress_callback
                )
            else:
                md_file, json_file = self.pipeline.process_audio(
                    audio_path=audio_path,
                    output_dir=output_dir,
                    language=language,
                    meeting_info=metadata or {},
                    skip_notifications=skip_notifications
                )
            
            logger.info(f"Processing completed successfully")
            return True, md_file, json_file, None
            
        except FileNotFoundError as e:
            error_msg = f"File not found: {e}"
            logger.error(error_msg)
            return False, None, None, error_msg
        except ASRError as e:
            error_msg = f"ASR error: {e}"
            logger.error(error_msg)
            return False, None, None, error_msg
        except LLMError as e:
            error_msg = f"LLM error: {e}"
            logger.error(error_msg)
            return False, None, None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return False, None, None, error_msg

    def process_batch(
        self,
        directory_path: Path,
        output_dir: Optional[Path] = None,
        language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        skip_notifications: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> Tuple[bool, List[Tuple[Path, bool, Optional[str]]], str]:
        """
        Обрабатывает все аудиофайлы в директории
        
        Returns:
            Кортеж (общий_успех, результаты_по_файлам, итоговое_сообщение)
        """
        try:
            logger.info(f"Processing audio files in directory: {directory_path}")
            
            # Проверяем существование директории
            if not directory_path.exists() or not directory_path.is_dir():
                error_msg = f"Directory not found: {directory_path}"
                return False, [], error_msg
            
            # Собираем все аудиофайлы в директории
            audio_extensions = [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"]
            audio_files = [
                path for path in directory_path.iterdir()
                if path.is_file() and path.suffix.lower() in audio_extensions
            ]
            
            if not audio_files:
                warning_msg = f"No audio files found in directory: {directory_path}"
                logger.warning(warning_msg)
                return False, [], warning_msg
            
            logger.info(f"Found {len(audio_files)} audio files")
            
            # Результаты обработки
            results = []
            success_count = 0
            
            # Обрабатываем каждый файл
            for i, audio_file in enumerate(audio_files):
                if progress_callback:
                    progress_callback(f"Processing {audio_file.name}", i, len(audio_files))
                
                # Создаем индивидуальную директорию для каждого файла
                file_output_dir = None
                if output_dir:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    file_output_dir = output_dir / f"{audio_file.stem}_{timestamp}"
                
                # Обрабатываем файл
                success, md_file, json_file, error_msg = self.process_single_file(
                    audio_path=audio_file,
                    output_dir=file_output_dir,
                    language=language,
                    metadata=metadata.copy() if metadata else {},
                    skip_notifications=skip_notifications
                )
                
                results.append((audio_file, success, error_msg))
                if success:
                    success_count += 1
            
            # Итоговый callback для прогресса
            if progress_callback:
                progress_callback("Completed", len(audio_files), len(audio_files))
            
            # Формируем итоговое сообщение
            if success_count == len(audio_files):
                summary_msg = f"All files ({success_count}/{len(audio_files)}) processed successfully"
                logger.info(summary_msg)
                return True, results, summary_msg
            else:
                summary_msg = f"Processed {success_count}/{len(audio_files)} files successfully"
                logger.warning(summary_msg)
                return success_count > 0, results, summary_msg
                
        except Exception as e:
            error_msg = f"Unexpected error during batch processing: {e}"
            logger.error(error_msg, exc_info=True)
            return False, [], error_msg

    def process_transcript_file(
        self,
        transcript_path: Path,
        output_dir: Optional[Path] = None,
        language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        skip_notifications: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Tuple[bool, Optional[Path], Optional[Path], Optional[str]]:
        """
        Обрабатывает JSON-файл транскрипта
        
        Returns:
            Кортеж (успех, путь_к_md, путь_к_json, сообщение_об_ошибке)
        """
        try:
            logger.info(f"Processing transcript file: {transcript_path}")
            
            # Проверяем существование файла
            if not transcript_path.exists():
                error_msg = f"Transcript file not found: {transcript_path}"
                return False, None, None, error_msg
            
            # Проверяем расширение файла
            if transcript_path.suffix.lower() != ".json":
                error_msg = f"File must have .json extension: {transcript_path}"
                return False, None, None, error_msg
            
            # Обрабатываем JSON-файл транскрипта
            if progress_callback:
                md_file, json_file = self.pipeline.process_transcript_json(
                    transcript_path=transcript_path,
                    output_dir=output_dir,
                    language=language,
                    meeting_info=metadata or {},
                    skip_notifications=skip_notifications,
                    progress_callback=progress_callback
                )
            else:
                md_file, json_file = self.pipeline.process_transcript_json(
                    transcript_path=transcript_path,
                    output_dir=output_dir,
                    language=language,
                    meeting_info=metadata or {},
                    skip_notifications=skip_notifications
                )
            
            logger.info(f"Processing completed successfully")
            logger.info(f"Output files: MD={md_file}, JSON={json_file}")
            
            return True, md_file, json_file, None
            
        except Exception as e:
            error_msg = f"Error processing transcript: {e}"
            logger.error(error_msg, exc_info=True)
            return False, None, None, error_msg

class MetadataBuilder:
    """Сервис для построения метаданных протокола"""
    
    @staticmethod
    def from_cli_args(**kwargs) -> Dict[str, Any]:
        """Построить метаданные из аргументов CLI"""
        metadata = {}
        
        if kwargs.get("title"):
            metadata["title"] = kwargs["title"]
        if kwargs.get("date"):
            metadata["date"] = kwargs["date"]
        if kwargs.get("location"):
            metadata["location"] = kwargs["location"]
        if kwargs.get("organizer"):
            metadata["organizer"] = kwargs["organizer"]
        
        # Участники и повестка
        if kwargs.get("participants"):
            if isinstance(kwargs["participants"], str):
                metadata["participants"] = [p.strip() for p in kwargs["participants"].split(",")]
            else:
                metadata["participants"] = kwargs["participants"]
        
        if kwargs.get("agenda"):
            if isinstance(kwargs["agenda"], str):
                metadata["agenda"] = [a.strip() for a in kwargs["agenda"].split(",")]
            else:
                metadata["agenda"] = kwargs["agenda"]
        
        metadata["author"] = "AI Assistant"
        return metadata

def get_audio_files_in_directory(directory_path: Path) -> List[Path]:
    """Получить список всех аудиофайлов в директории"""
    audio_extensions = [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"]
    audio_files = []
    
    if directory_path.exists() and directory_path.is_dir():
        for ext in audio_extensions:
            audio_files.extend(directory_path.glob(f"*{ext}"))
            audio_files.extend(directory_path.glob(f"*{ext.upper()}"))
    
    return sorted(audio_files)
