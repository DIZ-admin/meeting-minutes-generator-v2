"""
API маршруты для веб-интерфейса
"""
import os
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

from fastapi import APIRouter, File, UploadFile, Form, BackgroundTasks, HTTPException, Depends, Request, Query, Path as PathParam
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import ValidationError as PydanticValidationError

from ..core.services.pipeline import Pipeline
from ..core.exceptions import ASRError, LLMError, NotificationError, ConfigError, ValidationError
from ..utils.logging import get_default_logger
from ..config.config import config
from ..utils.cache import get_cache
from ..utils.metrics import get_metrics_collector, track_active_tasks
from .models import (
    UploadResponse, 
    StatusResponse, 
    Protocol, 
    ProtocolResponse, 
    ErrorResponse, 
    MeetingInfo, 
    ProcessingStatus,
    TasksResponse,
    ProtocolsResponse
)

logger = get_default_logger(__name__)

# Создаем роутер для API
router = APIRouter(prefix="/api/v1", tags=["API"])

# Словарь для хранения информации о задачах
tasks_info: Dict[str, Dict[str, Any]] = {}

# Инициализируем конвейер
pipeline = Pipeline()

# Инициализируем кеш
cache = get_cache()

# Инициализируем сборщик метрик
metrics_collector = get_metrics_collector()

def update_task_status(
    task_id: str, 
    status: ProcessingStatus, 
    progress: float = 0.0, 
    message: str = "", 
    result: Optional[Dict[str, Any]] = None
) -> None:
    """
    Обновляет статус задачи в словаре tasks_info
    
    Args:
        task_id: Идентификатор задачи
        status: Статус задачи
        progress: Прогресс выполнения (0-100)
        message: Сообщение о статусе
        result: Результат выполнения задачи
    """
    if task_id not in tasks_info:
        tasks_info[task_id] = {}
    
    tasks_info[task_id].update({
        "status": status,
        "progress": progress,
        "message": message,
        "updated_at": datetime.now().isoformat()
    })
    
    if result:
        tasks_info[task_id]["result"] = result
    
    # Обновляем метрики
    metrics_collector.task_status_update(task_id, status.value, progress)
    track_active_tasks(tasks_info)
    
    logger.debug(f"Updated task {task_id}: status={status}, progress={progress}, message={message}")

async def process_audio_task(
    task_id: str,
    file_path: Path,
    output_dir: Path,
    metadata: Dict[str, Any],
    language: Optional[str] = None,
    skip_notifications: bool = False
) -> None:
    """
    Фоновая задача для обработки аудиофайла
    
    Args:
        task_id: Идентификатор задачи
        file_path: Путь к аудиофайлу
        output_dir: Директория для сохранения результатов
        metadata: Метаданные протокола
        language: Язык аудио
        skip_notifications: Пропустить отправку уведомлений
    """
    try:
        # Обновляем статус задачи
        update_task_status(
            task_id=task_id,
            status=ProcessingStatus.PROCESSING,
            progress=5.0,
            message="Начало обработки аудиофайла"
        )
        
        # Определяем функцию обратного вызова для отслеживания прогресса
        def progress_callback(stage: str, progress_value: float) -> None:
            # Преобразуем прогресс в диапазон 5-95%
            normalized_progress = 5.0 + progress_value * 0.9
            update_task_status(
                task_id=task_id,
                status=ProcessingStatus.PROCESSING,
                progress=normalized_progress,
                message=f"Обработка: {stage}"
            )
        
        # Обрабатываем аудиофайл
        result = pipeline.process_audio_file(
            audio_path=file_path,
            output_dir=output_dir,
            language=language,
            meeting_info=metadata,
            skip_notifications=skip_notifications,
            progress_callback=progress_callback
        )
        
        # Обновляем статус задачи
        update_task_status(
            task_id=task_id,
            status=ProcessingStatus.COMPLETED,
            progress=100.0,
            message="Обработка завершена успешно",
            result={
                "protocol": result.to_dict() if hasattr(result, "to_dict") else result,
                "output_dir": str(output_dir),
                "files": {
                    "json": str(output_dir / f"{metadata.get('date', datetime.now().strftime('%Y-%m-%d'))}_{metadata.get('title', 'protocol')}.json"),
                    "md": str(output_dir / f"{metadata.get('date', datetime.now().strftime('%Y-%m-%d'))}_{metadata.get('title', 'protocol')}.md")
                }
            }
        )
        
        logger.info(f"Task {task_id} completed successfully")
        
    except (ASRError, LLMError, NotificationError, ConfigError, ValidationError) as e:
        # Обрабатываем известные ошибки
        logger.error(f"Task {task_id} failed with error: {str(e)}")
        update_task_status(
            task_id=task_id,
            status=ProcessingStatus.FAILED,
            progress=0.0,
            message=f"Ошибка: {str(e)}"
        )
    except Exception as e:
        # Обрабатываем неизвестные ошибки
        logger.exception(f"Task {task_id} failed with unexpected error: {str(e)}")
        update_task_status(
            task_id=task_id,
            status=ProcessingStatus.FAILED,
            progress=0.0,
            message=f"Неизвестная ошибка: {str(e)}"
        )

async def process_transcript_task(
    task_id: str,
    file_path: Path,
    output_dir: Path,
    metadata: Dict[str, Any],
    language: Optional[str] = None,
    skip_notifications: bool = False
) -> None:
    """
    Фоновая задача для обработки JSON-файла транскрипта
    
    Args:
        task_id: Идентификатор задачи
        file_path: Путь к JSON-файлу транскрипта
        output_dir: Директория для сохранения результатов
        metadata: Метаданные протокола
        language: Язык транскрипта
        skip_notifications: Пропустить отправку уведомлений
    """
    try:
        # Обновляем статус задачи
        update_task_status(
            task_id=task_id,
            status=ProcessingStatus.PROCESSING,
            progress=10.0,
            message="Начало обработки транскрипта"
        )
        
        # Определяем функцию обратного вызова для отслеживания прогресса
        def progress_callback(stage: str, progress_value: float) -> None:
            # Преобразуем прогресс в диапазон 10-95%
            normalized_progress = 10.0 + progress_value * 0.85
            update_task_status(
                task_id=task_id,
                status=ProcessingStatus.PROCESSING,
                progress=normalized_progress,
                message=f"Обработка: {stage}"
            )
        
        # Обрабатываем JSON-файл транскрипта
        result = pipeline.process_transcript_json(
            transcript_path=file_path,
            output_dir=output_dir,
            language=language,
            meeting_info=metadata,
            skip_notifications=skip_notifications,
            progress_callback=progress_callback
        )
        
        # Обновляем статус задачи
        update_task_status(
            task_id=task_id,
            status=ProcessingStatus.COMPLETED,
            progress=100.0,
            message="Обработка завершена успешно",
            result={
                "protocol": result.to_dict() if hasattr(result, "to_dict") else result,
                "output_dir": str(output_dir),
                "files": {
                    "json": str(output_dir / f"{metadata.get('date', datetime.now().strftime('%Y-%m-%d'))}_{metadata.get('title', 'protocol')}.json"),
                    "md": str(output_dir / f"{metadata.get('date', datetime.now().strftime('%Y-%m-%d'))}_{metadata.get('title', 'protocol')}.md")
                }
            }
        )
        
        logger.info(f"Task {task_id} completed successfully")
        
    except (LLMError, NotificationError, ConfigError, ValidationError) as e:
        # Обрабатываем известные ошибки
        logger.error(f"Task {task_id} failed with error: {str(e)}")
        update_task_status(
            task_id=task_id,
            status=ProcessingStatus.FAILED,
            progress=0.0,
            message=f"Ошибка: {str(e)}"
        )
    except Exception as e:
        # Обрабатываем неизвестные ошибки
        logger.exception(f"Task {task_id} failed with unexpected error: {str(e)}")
        update_task_status(
            task_id=task_id,
            status=ProcessingStatus.FAILED,
            progress=0.0,
            message=f"Неизвестная ошибка: {str(e)}"
        )

@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Загрузка аудиофайла для обработки",
    description="Загружает аудиофайл и начинает процесс его обработки",
    responses={
        202: {"description": "Файл принят к обработке", "model": UploadResponse},
        400: {"description": "Некорректный запрос", "model": ErrorResponse},
        415: {"description": "Неподдерживаемый формат файла", "model": ErrorResponse}
    }
)
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Аудиофайл (.mp3, .wav, .m4a) или JSON-транскрипт"),
    is_transcript: bool = Form(False, description="Флаг, указывающий, что файл является JSON-транскриптом"),
    meeting_info: Optional[str] = Form(None, description="Информация о встрече в формате JSON"),
    language: Optional[str] = Form(None, description="Язык аудио/транскрипта (ru, en, de)"),
    skip_notifications: bool = Form(False, description="Пропустить отправку уведомлений")
) -> UploadResponse:
    """
    Загрузка и обработка аудиофайла или JSON-файла транскрипта
    """
    # Проверяем, что конфигурация корректна
    from ..utils.config_validator import is_config_healthy
    if not is_config_healthy():
        raise HTTPException(
            status_code=500,
            detail="Некорректная конфигурация приложения. Проверьте настройки и API-ключи."
        )
    
    # Генерируем уникальный идентификатор задачи
    task_id = str(uuid.uuid4())
    
    # Парсим информацию о встрече
    metadata = {}
    if meeting_info:
        try:
            metadata = json.loads(meeting_info)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Некорректный формат информации о встрече. Ожидается JSON."
            )
    
    # Проверяем, что metadata - это словарь
    if not isinstance(metadata, dict):
        raise HTTPException(
            status_code=400,
            detail="Некорректный формат информации о встрече. Ожидается JSON-объект."
        )
    
    # Проверяем формат файла
    file_extension = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    
    if is_transcript:
        # Проверяем, что файл - это JSON
        if file_extension != ".json":
            raise HTTPException(
                status_code=415,
                detail="Неподдерживаемый формат файла. Ожидается JSON-файл транскрипта."
            )
    else:
        # Проверяем, что файл - это аудиофайл
        if file_extension not in [".mp3", ".wav", ".m4a"]:
            raise HTTPException(
                status_code=415,
                detail="Неподдерживаемый формат аудиофайла. Поддерживаются форматы: .mp3, .wav, .m4a"
            )
    
    # Создаем директории для сохранения файлов
    uploads_dir = Path(config.uploads_dir)
    output_dir = Path(config.output_dir) / task_id
    
    uploads_dir.mkdir(exist_ok=True, parents=True)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Сохраняем файл
    file_path = uploads_dir / f"{task_id}{file_extension}"
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # Обновляем метаданные
    if "title" not in metadata or not metadata["title"]:
        metadata["title"] = os.path.splitext(file.filename)[0] if file.filename else "Untitled Meeting"
    
    if "date" not in metadata or not metadata["date"]:
        metadata["date"] = datetime.now().strftime("%Y-%m-%d")
    
    # Добавляем задачу в фоновые задачи
    if is_transcript:
        background_tasks.add_task(
            process_transcript_task,
            task_id=task_id,
            file_path=file_path,
            output_dir=output_dir,
            metadata=metadata,
            language=language,
            skip_notifications=skip_notifications
        )
    else:
        background_tasks.add_task(
            process_audio_task,
            task_id=task_id,
            file_path=file_path,
            output_dir=output_dir,
            metadata=metadata,
            language=language,
            skip_notifications=skip_notifications
        )
    
    # Инициализируем информацию о задаче
    tasks_info[task_id] = {
        "task_id": task_id,
        "file_name": file.filename,
        "file_path": str(file_path),
        "output_dir": str(output_dir),
        "is_transcript": is_transcript,
        "metadata": metadata,
        "language": language,
        "skip_notifications": skip_notifications,
        "status": ProcessingStatus.PENDING,
        "progress": 0.0,
        "message": "Задача поставлена в очередь",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    
    # Обновляем метрики
    metrics_collector.task_created(task_id)
    track_active_tasks(tasks_info)
    
    # Возвращаем ответ
    return UploadResponse(
        task_id=task_id,
        message="Файл принят к обработке",
        status=ProcessingStatus.PENDING
    )

@router.get(
    "/status/{task_id}",
    response_model=StatusResponse,
    summary="Получение статуса обработки аудиофайла",
    description="Возвращает текущий статус обработки аудиофайла",
    responses={
        200: {"description": "Статус обработки", "model": StatusResponse},
        404: {"description": "Задача не найдена", "model": ErrorResponse}
    }
)
async def get_task_status(
    task_id: str = PathParam(..., description="Идентификатор задачи")
) -> StatusResponse:
    """
    Получение статуса задачи
    """
    # Проверяем, что задача существует
    if task_id not in tasks_info:
        raise HTTPException(
            status_code=404,
            detail=f"Задача с идентификатором {task_id} не найдена"
        )
    
    # Получаем информацию о задаче
    task_info = tasks_info[task_id]
    
    # Оцениваем время завершения
    estimated_completion = None
    if task_info["status"] == ProcessingStatus.PROCESSING and task_info["progress"] > 0:
        # Вычисляем оставшееся время на основе прогресса и времени, прошедшего с начала обработки
        try:
            created_at = datetime.fromisoformat(task_info["created_at"])
            updated_at = datetime.fromisoformat(task_info["updated_at"])
            elapsed_time = (updated_at - created_at).total_seconds()
            
            if elapsed_time > 0 and task_info["progress"] > 0:
                # Оцениваем общее время на основе текущего прогресса
                total_time = elapsed_time / (task_info["progress"] / 100)
                remaining_time = total_time - elapsed_time
                
                # Добавляем оставшееся время к текущему времени
                estimated_completion = (updated_at + datetime.timedelta(seconds=remaining_time)).isoformat()
        except Exception as e:
            logger.warning(f"Failed to estimate completion time for task {task_id}: {e}")
    
    # Возвращаем статус задачи
    return StatusResponse(
        task_id=task_id,
        status=task_info["status"],
        progress=task_info["progress"],
        message=task_info["message"],
        estimated_completion=estimated_completion
    )

@router.get(
    "/protocol/{task_id}",
    response_model=ProtocolResponse,
    summary="Получение протокола встречи",
    description="Возвращает сгенерированный протокол встречи",
    responses={
        200: {"description": "Протокол встречи", "model": ProtocolResponse},
        404: {"description": "Протокол не найден", "model": ErrorResponse},
        422: {"description": "Обработка не завершена", "model": ErrorResponse}
    }
)
async def get_protocol(
    task_id: str = PathParam(..., description="Идентификатор задачи"),
    format: str = Query("json", description="Формат протокола (json или markdown)")
) -> Union[ProtocolResponse, Response]:
    """
    Получение протокола встречи
    """
    # Проверяем, что задача существует
    if task_id not in tasks_info:
        raise HTTPException(
            status_code=404,
            detail=f"Задача с идентификатором {task_id} не найдена"
        )
    
    # Получаем информацию о задаче
    task_info = tasks_info[task_id]
    
    # Проверяем, что задача завершена
    if task_info["status"] != ProcessingStatus.COMPLETED:
        raise HTTPException(
            status_code=422,
            detail=f"Обработка задачи {task_id} не завершена. Текущий статус: {task_info['status']}"
        )
    
    # Проверяем, что результат существует
    if "result" not in task_info or not task_info["result"]:
        raise HTTPException(
            status_code=404,
            detail=f"Результат для задачи {task_id} не найден"
        )
    
    # Если запрошен формат markdown, возвращаем файл
    if format.lower() == "markdown":
        md_file_path = task_info["result"]["files"]["md"]
        
        if not os.path.exists(md_file_path):
            raise HTTPException(
                status_code=404,
                detail=f"Файл протокола в формате Markdown не найден"
            )
        
        return FileResponse(
            path=md_file_path,
            media_type="text/markdown",
            filename=os.path.basename(md_file_path)
        )
    
    # По умолчанию возвращаем протокол в формате JSON
    protocol_data = task_info["result"]["protocol"]
    
    # Преобразуем протокол в модель ответа
    try:
        return ProtocolResponse.from_internal(protocol_data)
    except Exception as e:
        logger.error(f"Failed to convert protocol to response model: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при преобразовании протокола: {str(e)}"
        )

@router.get(
    "/download/{task_id}/{file_type}",
    summary="Скачивание файла результата",
    description="Возвращает файл результата обработки (markdown или json)",
    responses={
        200: {"description": "Файл для скачивания"},
        404: {"description": "Файл не найден", "model": ErrorResponse},
        422: {"description": "Обработка не завершена", "model": ErrorResponse}
    }
)
async def download_file(
    task_id: str = PathParam(..., description="Идентификатор задачи"),
    file_type: str = PathParam(..., description="Тип файла: 'md' для Markdown или 'json' для JSON")
) -> FileResponse:
    """
    Скачивание файла результата
    """
    # Проверяем, что задача существует
    if task_id not in tasks_info:
        raise HTTPException(
            status_code=404,
            detail=f"Задача с идентификатором {task_id} не найдена"
        )
    
    # Получаем информацию о задаче
    task_info = tasks_info[task_id]
    
    # Проверяем, что задача завершена
    if task_info["status"] != ProcessingStatus.COMPLETED:
        raise HTTPException(
            status_code=422,
            detail=f"Обработка задачи {task_id} не завершена. Текущий статус: {task_info['status']}"
        )
    
    # Проверяем, что результат существует
    if "result" not in task_info or not task_info["result"] or "files" not in task_info["result"]:
        raise HTTPException(
            status_code=404,
            detail=f"Результат для задачи {task_id} не найден"
        )
    
    # Определяем путь к файлу
    if file_type.lower() == "md":
        file_path = task_info["result"]["files"]["md"]
        media_type = "text/markdown"
    elif file_type.lower() == "json":
        file_path = task_info["result"]["files"]["json"]
        media_type = "application/json"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый тип файла: {file_type}. Поддерживаемые типы: 'md', 'json'"
        )
    
    # Проверяем, что файл существует
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"Файл {file_path} не найден"
        )
    
    # Возвращаем файл
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=os.path.basename(file_path)
    )

@router.get(
    "/tasks",
    response_model=TasksResponse,
    summary="Получение списка задач",
    description="Возвращает список всех задач обработки",
    responses={
        200: {"description": "Список задач"},
        500: {"description": "Внутренняя ошибка сервера", "model": ErrorResponse}
    }
)
async def get_tasks() -> TasksResponse:
    """
    Получение списка всех задач
    """
    try:
        # Преобразуем словарь задач в список
        tasks_list = []
        for task_id, task_info in tasks_info.items():
            # Создаем копию информации о задаче
            task_data = {
                "task_id": task_id,
                "status": task_info.get("status", ProcessingStatus.PENDING),
                "message": task_info.get("message", ""),
                "progress": task_info.get("progress", 0),
                "created_at": task_info.get("created_at", datetime.now().isoformat()),
                "updated_at": task_info.get("updated_at", datetime.now().isoformat()),
                "file_name": task_info.get("file_name", ""),
                "task_type": task_info.get("task_type", "audio_processing")
            }
            tasks_list.append(task_data)
        
        # Сортируем задачи по времени создания (новые сначала)
        tasks_list.sort(key=lambda x: x["created_at"], reverse=True)
        
        return TasksResponse(tasks=tasks_list)
        
    except Exception as e:
        logger.exception(f"Ошибка при получении списка задач: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении списка задач: {str(e)}")

@router.get(
    "/protocols",
    response_model=ProtocolsResponse,
    summary="Получение списка протоколов",
    description="Возвращает список всех доступных протоколов",
    responses={
        200: {"description": "Список протоколов"},
        500: {"description": "Внутренняя ошибка сервера", "model": ErrorResponse}
    }
)
async def get_protocols() -> ProtocolsResponse:
    """
    Получение списка всех протоколов
    """
    try:
        # Получаем список задач со статусом 'completed'
        completed_tasks = [task_id for task_id, task_info in tasks_info.items() 
                          if task_info.get("status") == ProcessingStatus.COMPLETED]
        
        # Получаем протоколы для завершенных задач
        protocols_list = []
        
        for task_id in completed_tasks:
            try:
                # Проверяем наличие результата
                task_info = tasks_info[task_id]
                if "result" not in task_info or not task_info["result"] or "files" not in task_info["result"]:
                    continue
                
                # Проверяем наличие JSON-файла протокола
                json_path = task_info["result"]["files"].get("json")
                if not json_path or not os.path.exists(json_path):
                    continue
                
                # Загружаем протокол из JSON-файла
                with open(json_path, "r", encoding="utf-8") as f:
                    protocol_data = json.load(f)
                
                # Добавляем ID задачи к протоколу
                protocol_data["id"] = task_id
                
                # Добавляем протокол в список
                protocols_list.append(protocol_data)
                
            except Exception as e:
                logger.warning(f"Ошибка при загрузке протокола для задачи {task_id}: {str(e)}")
                continue
        
        # Сортируем протоколы по дате (новые сначала)
        protocols_list.sort(
            key=lambda x: x.get("metadata", {}).get("date", "") 
                if isinstance(x.get("metadata", {}).get("date", ""), str) 
                else str(x.get("metadata", {}).get("date", "")), 
            reverse=True
        )
        
        return ProtocolsResponse(protocols=protocols_list)
        
    except Exception as e:
        logger.exception(f"Ошибка при получении списка протоколов: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении списка протоколов: {str(e)}")

@router.get(
    "/protocols/{protocol_id}",
    response_model=Protocol,
    summary="Получение протокола по ID",
    description="Возвращает протокол по указанному ID",
    responses={
        200: {"description": "Протокол"},
        404: {"description": "Протокол не найден", "model": ErrorResponse},
        500: {"description": "Внутренняя ошибка сервера", "model": ErrorResponse}
    }
)
async def get_protocol_by_id(protocol_id: str = PathParam(..., description="Идентификатор протокола")) -> Protocol:
    """
    Получение протокола по ID
    """
    try:
        # Проверяем существование задачи
        if protocol_id not in tasks_info:
            raise HTTPException(status_code=404, detail=f"Протокол с ID {protocol_id} не найден")
        
        # Проверяем статус задачи
        task_info = tasks_info[protocol_id]
        if task_info.get("status") != ProcessingStatus.COMPLETED:
            raise HTTPException(
                status_code=400, 
                detail=f"Протокол недоступен для задачи со статусом '{task_info.get('status')}'"
            )
        
        # Проверяем наличие результата
        if "result" not in task_info or not task_info["result"] or "files" not in task_info["result"]:
            raise HTTPException(status_code=404, detail="Результат не найден")
        
        # Проверяем наличие JSON-файла протокола
        json_path = task_info["result"]["files"].get("json")
        if not json_path or not os.path.exists(json_path):
            raise HTTPException(status_code=404, detail=f"Файл протокола не найден")
        
        # Загружаем протокол из JSON-файла
        with open(json_path, "r", encoding="utf-8") as f:
            protocol_data = json.load(f)
        
        # Добавляем ID задачи к протоколу
        protocol_data["id"] = protocol_id
        
        return protocol_data
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception(f"Ошибка при получении протокола: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении протокола: {str(e)}")

@router.get(
    "/protocols/{protocol_id}/{format}",
    response_class=FileResponse,
    summary="Скачивание протокола в указанном формате",
    description="Возвращает протокол в формате Markdown или JSON",
    responses={
        200: {"description": "Файл протокола"},
        404: {"description": "Протокол не найден", "model": ErrorResponse},
        500: {"description": "Внутренняя ошибка сервера", "model": ErrorResponse}
    }
)
async def get_protocol_format(
    protocol_id: str = PathParam(..., description="Идентификатор протокола"),
    format: str = PathParam(..., description="Формат протокола: 'md' для Markdown или 'json' для JSON")
) -> FileResponse:
    """
    Получение протокола в указанном формате
    """
    try:
        # Проверяем существование задачи
        if protocol_id not in tasks_info:
            raise HTTPException(status_code=404, detail=f"Протокол с ID {protocol_id} не найден")
        
        # Проверяем статус задачи
        task_info = tasks_info[protocol_id]
        if task_info.get("status") != ProcessingStatus.COMPLETED:
            raise HTTPException(
                status_code=400, 
                detail=f"Протокол недоступен для задачи со статусом '{task_info.get('status')}'"
            )
        
        # Проверяем наличие результата
        if "result" not in task_info or not task_info["result"] or "files" not in task_info["result"]:
            raise HTTPException(status_code=404, detail="Результат не найден")
        
        # Проверяем формат
        if format.lower() not in ["md", "json"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Неподдерживаемый формат: {format}. Поддерживаются только 'md' и 'json'"
            )
        
        # Получаем путь к файлу
        format_key = format.lower()
        if format_key not in task_info["result"]["files"]:
            raise HTTPException(status_code=404, detail=f"Файл в формате {format} не найден")
        
        file_path = task_info["result"]["files"][format_key]
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"Файл {file_path} не найден")
        
        # Определяем тип контента
        media_type = "text/markdown" if format_key == "md" else "application/json"
        
        # Формируем имя файла для скачивания
        filename = f"protocol_{protocol_id}.{format_key}"
        
        # Возвращаем файл
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type
        )
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception(f"Ошибка при получении протокола: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении протокола: {str(e)}")

@router.delete(
    "/tasks/{task_id}",
    summary="Удаление задачи",
    description="Удаляет задачу из списка",
    responses={
        200: {"description": "Задача успешно удалена"},
        404: {"description": "Задача не найдена", "model": ErrorResponse},
        500: {"description": "Внутренняя ошибка сервера", "model": ErrorResponse}
    }
)
async def delete_task(task_id: str = PathParam(..., description="Идентификатор задачи")):
    """
    Удаление задачи
    """
    try:
        # Проверяем существование задачи
        if task_id not in tasks_info:
            raise HTTPException(status_code=404, detail=f"Задача с ID {task_id} не найдена")
        
        # Удаляем задачу из словаря
        task_info = tasks_info.pop(task_id)
        
        # Логируем удаление
        logger.info(f"Задача {task_id} удалена")
        
        # Обновляем метрики
        metrics_collector.decrement_counter("active_tasks")
        
        return {"status": "success", "message": f"Задача {task_id} успешно удалена"}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception(f"Ошибка при удалении задачи: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении задачи: {str(e)}")


@router.get("/cache/stats")
async def get_cache_stats():
    """
    Получение статистики кеша
    """
    try:
        cache = get_cache()
        stats = {
            "healthy": True,
            "timestamp": datetime.now().isoformat(),
            "redis_available": cache.is_redis_available() if hasattr(cache, 'is_redis_available') else True,
            "size": cache.get_cache_size() if hasattr(cache, 'get_cache_size') else None,
            "type": type(cache).__name__
        }
        return stats
    except Exception as e:
        logger.exception(f"Ошибка получения статистики кеша: {str(e)}")
        return {
            "healthy": False,
            "timestamp": datetime.now().isoformat(),
            "redis_available": False,
            "error": str(e)
        }


@router.post("/cache/clear")
async def clear_cache():
    """
    Очистка кеша
    """
    try:
        cache = get_cache()
        if hasattr(cache, 'clear'):
            cache.clear()
        return {"status": "success", "message": "Кеш успешно очищен"}
    except Exception as e:
        logger.exception(f"Ошибка очистки кеша: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка очистки кеша: {str(e)}")


@router.get(
    "/protocols/{protocol_id}/download",
    summary="Скачивание протокола",
    description="Возвращает протокол в указанном формате",
    responses={
        200: {"description": "Файл протокола для скачивания"},
        400: {"description": "Неверный формат", "model": ErrorResponse},
        404: {"description": "Протокол не найден", "model": ErrorResponse}
    }
)
async def download_protocol(
    protocol_id: str = PathParam(..., description="Идентификатор протокола"),
    format: str = Query("markdown", description="Формат файла: 'markdown' или 'json'")
) -> FileResponse:
    """
    Скачивание протокола в указанном формате
    """
    try:
        if format not in ["markdown", "json"]:
            raise HTTPException(status_code=400, detail="Неподдерживаемый формат. Используйте 'markdown' или 'json'")
        
        # Проверяем, существует ли задача с таким ID
        if protocol_id not in tasks_info:
            raise HTTPException(status_code=404, detail=f"Протокол с ID {protocol_id} не найден")
        
        task_info = tasks_info[protocol_id]
        if task_info["status"] != "completed":
            raise HTTPException(status_code=400, detail="Обработка протокола не завершена")
        
        # Определяем путь к файлу
        if format == "markdown":
            file_path = task_info.get("markdown_file")
            media_type = "text/markdown"
            file_extension = "md"
        else:  # json
            file_path = task_info.get("json_file")
            media_type = "application/json"
            file_extension = "json"
        
        if not file_path or not Path(file_path).exists():
            raise HTTPException(status_code=404, detail=f"Файл протокола в формате {format} не найден")
        
        # Возвращаем файл
        filename = f"protocol_{protocol_id}.{file_extension}"
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type
        )
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception(f"Ошибка при скачивании протокола: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка при скачивании протокола: {str(e)}")

