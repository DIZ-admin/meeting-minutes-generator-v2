#!/usr/bin/env python3
"""
Web File Processor - сервис для обработки файлов через веб-интерфейс
Изолирует бизнес-логику от FastAPI endpoints по аналогии с CLI Services
"""
import asyncio
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Tuple, List
from datetime import datetime

from app.core.services.pipeline import Pipeline
from app.core.exceptions import ASRError, LLMError, ConfigError
from app.utils.logging import get_default_logger

logger = get_default_logger(__name__)

class WebFileProcessor:
    """
    Сервис для обработки файлов через веб-интерфейс
    Изолирует бизнес-логику от FastAPI endpoints
    """
    
    def __init__(self, pipeline: Pipeline):
        """
        Инициализация процессора
        
        Args:
            pipeline: Экземпляр Pipeline для обработки
        """
        self.pipeline = pipeline
    
    async def process_audio_async(
        self,
        file_path: Path,
        output_dir: Optional[Path] = None,
        language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        skip_notifications: bool = False,
        progress_callback: Optional[Callable[[str, float, Optional[str]], None]] = None
    ) -> Tuple[bool, Optional[Path], Optional[Path], Optional[str]]:
        """
        Асинхронно обрабатывает аудиофайл
        
        Args:
            file_path: Путь к аудиофайлу
            output_dir: Директория для сохранения результатов
            language: Язык аудио
            metadata: Метаданные протокола
            skip_notifications: Пропустить отправку уведомлений
            progress_callback: Функция для обновления прогресса (stage, percent, message)
            
        Returns:
            Кортеж (успех, путь_к_md, путь_к_json, сообщение_об_ошибке)
        """
        try:
            logger.info(f"Processing audio file: {file_path}")
            
            if progress_callback:
                progress_callback("initializing", 0.05, "Инициализация конвейера")
            
            # Создаем функцию прогресса для pipeline
            def pipeline_progress_callback(stage: str, percent: float):
                if progress_callback:
                    progress_callback(stage, percent, None)
            
            # Запускаем обработку в executor для избежания блокировки
            loop = asyncio.get_event_loop()
            
            if progress_callback:
                result = await loop.run_in_executor(
                    None,
                    self._process_audio_sync_with_progress,
                    file_path, output_dir, language, metadata, skip_notifications, pipeline_progress_callback
                )
            else:
                result = await loop.run_in_executor(
                    None,
                    self._process_audio_sync,
                    file_path, output_dir, language, metadata, skip_notifications
                )
            
            md_file, json_file = result
            
            if progress_callback:
                progress_callback("completed", 1.0, "Обработка завершена")
            
            logger.info(f"Processing completed successfully")
            return True, md_file, json_file, None
            
        except FileNotFoundError as e:
            error_msg = f"File not found: {e}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback("error", 0.0, error_msg)
            return False, None, None, error_msg
            
        except ASRError as e:
            error_msg = f"ASR error: {e}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback("error", 0.0, error_msg)
            return False, None, None, error_msg
            
        except LLMError as e:
            error_msg = f"LLM error: {e}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback("error", 0.0, error_msg)
            return False, None, None, error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            if progress_callback:
                progress_callback("error", 0.0, error_msg)
            return False, None, None, error_msg
    
    def _process_audio_sync_with_progress(
        self,
        file_path: Path,
        output_dir: Optional[Path],
        language: Optional[str],
        metadata: Optional[Dict[str, Any]],
        skip_notifications: bool,
        progress_callback: Callable[[str, float], None]
    ) -> Tuple[Path, Path]:
        """Синхронная обработка с progress callback"""
        return self.pipeline.process_audio(
            audio_path=file_path,
            output_dir=output_dir,
            language=language,
            meeting_info=metadata or {},
            skip_notifications=skip_notifications,
            progress_callback=progress_callback
        )
    
    def _process_audio_sync(
        self,
        file_path: Path,
        output_dir: Optional[Path],
        language: Optional[str],
        metadata: Optional[Dict[str, Any]],
        skip_notifications: bool
    ) -> Tuple[Path, Path]:
        """Синхронная обработка без progress callback"""
        return self.pipeline.process_audio(
            audio_path=file_path,
            output_dir=output_dir,
            language=language,
            meeting_info=metadata or {},
            skip_notifications=skip_notifications
        )

    async def process_transcript_async(
        self,
        transcript_path: Path,
        output_dir: Optional[Path] = None,
        language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        skip_notifications: bool = False,
        progress_callback: Optional[Callable[[str, float, Optional[str]], None]] = None
    ) -> Tuple[bool, Optional[Path], Optional[Path], Optional[str]]:
        """
        Асинхронно обрабатывает JSON-файл транскрипта
        
        Returns:
            Кортеж (успех, путь_к_md, путь_к_json, сообщение_об_ошибке)
        """
        try:
            logger.info(f"Processing transcript file: {transcript_path}")
            
            if progress_callback:
                progress_callback("initializing", 0.05, "Инициализация конвейера")
            
            # Проверяем файл
            if not transcript_path.exists():
                error_msg = f"Transcript file not found: {transcript_path}"
                if progress_callback:
                    progress_callback("error", 0.0, error_msg)
                return False, None, None, error_msg
            
            if transcript_path.suffix.lower() != ".json":
                error_msg = f"File must have .json extension: {transcript_path}"
                if progress_callback:
                    progress_callback("error", 0.0, error_msg)
                return False, None, None, error_msg
            
            # Создаем функцию прогресса для pipeline
            def pipeline_progress_callback(stage: str, percent: float):
                if progress_callback:
                    progress_callback(stage, percent, None)
            
            # Запускаем обработку в executor
            loop = asyncio.get_event_loop()
            
            if progress_callback:
                result = await loop.run_in_executor(
                    None,
                    self._process_transcript_sync_with_progress,
                    transcript_path, output_dir, language, metadata, skip_notifications, pipeline_progress_callback
                )
            else:
                result = await loop.run_in_executor(
                    None,
                    self._process_transcript_sync,
                    transcript_path, output_dir, language, metadata, skip_notifications
                )
            
            md_file, json_file = result
            
            if progress_callback:
                progress_callback("completed", 1.0, "Обработка завершена")
            
            logger.info(f"Processing completed successfully")
            return True, md_file, json_file, None
            
        except Exception as e:
            error_msg = f"Error processing transcript: {e}"
            logger.error(error_msg, exc_info=True)
            if progress_callback:
                progress_callback("error", 0.0, error_msg)
            return False, None, None, error_msg
    
    def _process_transcript_sync_with_progress(
        self,
        transcript_path: Path,
        output_dir: Optional[Path],
        language: Optional[str],
        metadata: Optional[Dict[str, Any]],
        skip_notifications: bool,
        progress_callback: Callable[[str, float], None]
    ) -> Tuple[Path, Path]:
        """Синхронная обработка транскрипта с progress callback"""
        return self.pipeline.process_transcript_json(
            transcript_path=transcript_path,
            output_dir=output_dir,
            language=language,
            meeting_info=metadata or {},
            skip_notifications=skip_notifications,
            progress_callback=progress_callback
        )
    
    def _process_transcript_sync(
        self,
        transcript_path: Path,
        output_dir: Optional[Path],
        language: Optional[str],
        metadata: Optional[Dict[str, Any]],
        skip_notifications: bool
    ) -> Tuple[Path, Path]:
        """Синхронная обработка транскрипта без progress callback"""
        return self.pipeline.process_transcript_json(
            transcript_path=transcript_path,
            output_dir=output_dir,
            language=language,
            meeting_info=metadata or {},
            skip_notifications=skip_notifications
        )

class WebTaskManager:
    """
    Менеджер задач для веб-интерфейса
    Управляет фоновыми задачами обработки
    """
    
    def __init__(self):
        """Инициализация менеджера задач"""
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.logger = get_default_logger(self.__class__.__name__)
    
    def create_task(self, task_type: str = "audio_processing") -> str:
        """
        Создает новую задачу
        
        Args:
            task_type: Тип задачи
            
        Returns:
            ID задачи
        """
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "id": task_id,
            "type": task_type,
            "status": "created",
            "progress": 0.0,
            "message": "Задача создана",
            "created_at": datetime.now(),
            "result": None,
            "error": None
        }
        
        self.logger.info(f"Created task {task_id} of type {task_type}")
        return task_id
    
    def update_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        result: Optional[Any] = None,
        error: Optional[str] = None
    ):
        """
        Обновляет статус задачи
        
        Args:
            task_id: ID задачи
            status: Новый статус
            progress: Прогресс (0.0-1.0)
            message: Сообщение о статусе
            result: Результат выполнения
            error: Сообщение об ошибке
        """
        if task_id not in self.tasks:
            self.logger.warning(f"Attempt to update non-existent task {task_id}")
            return
        
        task = self.tasks[task_id]
        
        if status:
            task["status"] = status
        if progress is not None:
            task["progress"] = progress
        if message:
            task["message"] = message
        if result is not None:
            task["result"] = result
        if error:
            task["error"] = error
            task["status"] = "error"
        
        task["updated_at"] = datetime.now()
        
        self.logger.debug(f"Updated task {task_id}: status={task.get('status')}, progress={task.get('progress')}")
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о задаче
        
        Args:
            task_id: ID задачи
            
        Returns:
            Информация о задаче или None
        """
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """
        Получает информацию о всех задачах
        
        Returns:
            Список всех задач
        """
        return list(self.tasks.values())
    
    def delete_task(self, task_id: str) -> bool:
        """
        Удаляет задачу
        
        Args:
            task_id: ID задачи
            
        Returns:
            True если задача была удалена
        """
        if task_id in self.tasks:
            del self.tasks[task_id]
            self.logger.info(f"Deleted task {task_id}")
            return True
        return False
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """
        Очищает старые задачи
        
        Args:
            max_age_hours: Максимальный возраст задач в часах
        """
        now = datetime.now()
        tasks_to_delete = []
        
        for task_id, task in self.tasks.items():
            created_at = task.get("created_at", now)
            age_hours = (now - created_at).total_seconds() / 3600
            
            if age_hours > max_age_hours:
                tasks_to_delete.append(task_id)
        
        for task_id in tasks_to_delete:
            self.delete_task(task_id)
        
        if tasks_to_delete:
            self.logger.info(f"Cleaned up {len(tasks_to_delete)} old tasks")

class WebMetadataBuilder:
    """
    Сервис для построения метаданных из веб-форм
    """
    
    @staticmethod
    def from_web_form(
        title: Optional[str] = None,
        date: Optional[str] = None,
        location: Optional[str] = None,
        organizer: Optional[str] = None,
        participants: Optional[str] = None,
        agenda: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Построить метаданные из веб-формы
        
        Returns:
            Словарь метаданных
        """
        metadata = {}
        
        if title:
            metadata["title"] = title.strip()
        
        if date:
            metadata["date"] = date.strip()
        
        if location:
            metadata["location"] = location.strip()
        
        if organizer:
            metadata["organizer"] = organizer.strip()
        
        if participants and participants.strip():
            # Разделяем участников по запятой или новой строке
            parts = participants.replace('\n', ',').split(',')
            cleaned_parts = [p.strip() for p in parts if p.strip()]
            if cleaned_parts:
                metadata["participants"] = cleaned_parts
        
        if agenda and agenda.strip():
            # Разделяем повестку по запятой или новой строке
            items = agenda.replace('\n', ',').split(',')
            cleaned_items = [item.strip() for item in items if item.strip()]
            if cleaned_items:
                metadata["agenda"] = cleaned_items
        
        # Добавляем дополнительные параметры
        for key, value in kwargs.items():
            if value:
                metadata[key] = value
        
        # Автор всегда AI Assistant
        metadata["author"] = "AI Assistant"
        
        return metadata

# Глобальные экземпляры для использования в FastAPI
_task_manager = WebTaskManager()

def get_task_manager() -> WebTaskManager:
    """Dependency для получения менеджера задач"""
    return _task_manager

def get_web_file_processor() -> WebFileProcessor:
    """Dependency для получения веб-процессора файлов"""
    pipeline = Pipeline()
    return WebFileProcessor(pipeline)
