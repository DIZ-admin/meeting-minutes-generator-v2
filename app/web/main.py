"""
Веб-интерфейс для системы генерации протоколов совещаний на базе FastAPI
"""
import os
import json
import time
import uuid
import asyncio
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from datetime import datetime

import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Импортируем компоненты системы
from ..core.services.pipeline import Pipeline
from ..core.utils.transcript_converter import convert_file_to_transcript_format, save_transcript_format
from ..config.config import config
from ..utils.logging import get_default_logger as setup_logger

# Настройка логирования
logger = setup_logger(__name__)

# Создаем директорию для загрузок, если она не существует
UPLOAD_DIR = Path(config.uploads_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Создаем директорию для выходных файлов, если она не существует
OUTPUT_DIR = Path(config.output_dir)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Создаем директорию для хранения состояния задач
TASKS_DIR = Path(config.base_dir) / "tasks"
TASKS_DIR.mkdir(parents=True, exist_ok=True)

# Создаем экземпляр FastAPI
app = FastAPI(
    title="Meeting Protocol Generator",
    description="API для генерации протоколов совещаний на основе аудиозаписей",
    version="1.0.0"
)

# Настраиваем статические файлы и шаблоны
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Создаем экземпляр Pipeline
pipeline = Pipeline()

# Модели данных
class TaskStatus(BaseModel):
    """Статус задачи обработки"""
    task_id: str
    status: str  # pending, processing, completed, failed
    progress: float  # от 0 до 1
    message: str
    result: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str

class TaskCreate(BaseModel):
    """Данные для создания задачи"""
    title: Optional[str] = None
    language: Optional[str] = None
    date: Optional[str] = None
    skip_notifications: bool = True

# Хранилище задач (в реальном приложении лучше использовать базу данных)
tasks: Dict[str, TaskStatus] = {}

# Функция для обновления статуса задачи
def update_task_status(task_id: str, status: str, progress: float, message: str, result: Optional[Dict[str, Any]] = None):
    """Обновляет статус задачи и сохраняет его в файл"""
    if task_id in tasks:
        tasks[task_id].status = status
        tasks[task_id].progress = progress
        tasks[task_id].message = message
        tasks[task_id].updated_at = datetime.now().isoformat()
        
        if result:
            tasks[task_id].result = result
        
        # Сохраняем статус в файл
        task_file = TASKS_DIR / f"{task_id}.json"
        with open(task_file, "w", encoding="utf-8") as f:
            f.write(tasks[task_id].json())

# Функция обратного вызова для отслеживания прогресса
def progress_callback(message: str, progress: float, task_id: str):
    """Функция обратного вызова для отслеживания прогресса обработки"""
    update_task_status(task_id, "processing", progress, message)

# Фоновая задача для обработки аудиофайла
async def process_audio_task(audio_path: Path, task_id: str, task_data: TaskCreate):
    """Фоновая задача для обработки аудиофайла"""
    try:
        # Подготавливаем данные
        meeting_info = {}
        if task_data.title:
            meeting_info["title"] = task_data.title
        if task_data.date:
            meeting_info["date"] = task_data.date
        
        # Создаем директорию для выходных файлов
        output_dir = OUTPUT_DIR / f"task_{task_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Обрабатываем аудиофайл
        md_file, json_file = pipeline.process_audio(
            audio_path=audio_path,
            output_dir=output_dir,
            language=task_data.language,
            meeting_info=meeting_info,
            skip_notifications=task_data.skip_notifications,
            progress_callback=lambda message, progress: progress_callback(message, progress, task_id)
        )
        
        # Обновляем статус задачи
        result = {
            "markdown_file": str(md_file),
            "json_file": str(json_file),
            "output_dir": str(output_dir)
        }
        update_task_status(task_id, "completed", 1.0, "Обработка завершена успешно", result)
        
    except Exception as e:
        logger.error(f"Error processing audio file: {e}", exc_info=True)
        update_task_status(task_id, "failed", 0.0, f"Ошибка обработки: {str(e)}")

# Фоновая задача для обработки транскрипта
async def process_transcript_task(transcript_path: Path, task_id: str, task_data: TaskCreate):
    """Фоновая задача для обработки транскрипта"""
    try:
        # Подготавливаем данные
        meeting_info = {}
        if task_data.title:
            meeting_info["title"] = task_data.title
        if task_data.date:
            meeting_info["date"] = task_data.date
        
        # Создаем директорию для выходных файлов
        output_dir = OUTPUT_DIR / f"task_{task_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Обрабатываем транскрипт
        md_file, json_file = pipeline.process_transcript_json(
            transcript_path=transcript_path,
            output_dir=output_dir,
            language=task_data.language,
            meeting_info=meeting_info,
            skip_notifications=task_data.skip_notifications,
            progress_callback=lambda message, progress: progress_callback(message, progress, task_id)
        )
        
        # Обновляем статус задачи
        result = {
            "markdown_file": str(md_file),
            "json_file": str(json_file),
            "output_dir": str(output_dir)
        }
        update_task_status(task_id, "completed", 1.0, "Обработка завершена успешно", result)
        
    except Exception as e:
        logger.error(f"Error processing transcript: {e}", exc_info=True)
        update_task_status(task_id, "failed", 0.0, f"Ошибка обработки: {str(e)}")

# Маршруты API
@app.get("/health")
async def health():
    """Проверка работоспособности сервиса для Docker healthcheck"""
    return {"status": "ok", "version": "0.3.0"}

@app.get("/")
async def root(request: Request):
    """Главная страница"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/upload")
async def upload_page(request: Request):
    """Страница загрузки файлов"""
    return templates.TemplateResponse("upload.html", {"request": request})

@app.get("/tasks")
async def tasks_page(request: Request):
    """Страница со списком задач"""
    return templates.TemplateResponse("tasks.html", {"request": request})

@app.get("/protocols")
async def protocols_page(request: Request):
    """Страница с протоколами"""
    return templates.TemplateResponse("protocols.html", {"request": request})

@app.post("/api/upload-audio")
async def upload_audio(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    date: Optional[str] = Form(None),
    skip_notifications: bool = Form(True)
):
    """Загрузка и обработка аудиофайла"""
    # Проверяем расширение файла
    allowed_extensions = [".mp3", ".wav", ".m4a", ".ogg", ".flac"]
    file_ext = os.path.splitext(audio_file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемый формат файла. Разрешены: {', '.join(allowed_extensions)}")
    
    # Создаем уникальный идентификатор задачи
    task_id = str(uuid.uuid4())
    
    # Сохраняем файл
    audio_path = UPLOAD_DIR / f"{task_id}{file_ext}"
    with open(audio_path, "wb") as f:
        f.write(await audio_file.read())
    
    # Создаем задачу
    task_data = TaskCreate(
        title=title,
        language=language,
        date=date or datetime.now().strftime("%Y-%m-%d"),
        skip_notifications=skip_notifications
    )
    
    # Создаем запись о задаче
    tasks[task_id] = TaskStatus(
        task_id=task_id,
        status="pending",
        progress=0.0,
        message="Задача создана",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    # Сохраняем статус в файл
    task_file = TASKS_DIR / f"{task_id}.json"
    with open(task_file, "w", encoding="utf-8") as f:
        f.write(tasks[task_id].json())
    
    # Запускаем обработку в фоновом режиме
    background_tasks.add_task(process_audio_task, audio_path, task_id, task_data)
    
    return {"task_id": task_id, "status": "pending", "message": "Аудиофайл загружен и поставлен в очередь на обработку"}

@app.post("/api/v1/upload")
async def upload_file_v1(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    skip_notifications: bool = Form(True),
    meeting_info: Optional[str] = Form(None)
):
    """Универсальный эндпоинт для загрузки файлов (API v1)"""
    # Проверяем расширение файла
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    # Определяем тип файла
    is_transcript = file_ext == ".json"
    is_audio = file_ext in [".mp3", ".wav", ".m4a", ".ogg", ".flac"]
    
    if not (is_transcript or is_audio):
        raise HTTPException(
            status_code=400, 
            detail=f"Неподдерживаемый формат файла. Разрешены: .mp3, .wav, .m4a, .ogg, .flac, .json"
        )
    
    # Создаем уникальный идентификатор задачи
    task_id = str(uuid.uuid4())
    
    # Сохраняем файл
    file_path = UPLOAD_DIR / f"{task_id}{file_ext}"
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # Парсим информацию о встрече, если она предоставлена
    title = None
    date = None
    
    if meeting_info:
        try:
            meeting_data = json.loads(meeting_info)
            title = meeting_data.get('title')
            date = meeting_data.get('date')
        except json.JSONDecodeError:
            logger.warning(f"Не удалось распарсить информацию о встрече: {meeting_info}")
    
    # Создаем задачу
    task_data = TaskCreate(
        title=title,
        language=language,
        date=date or datetime.now().strftime("%Y-%m-%d"),
        skip_notifications=skip_notifications
    )
    
    # Создаем запись о задаче
    tasks[task_id] = TaskStatus(
        task_id=task_id,
        status="pending",
        progress=0.0,
        message="Задача создана",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    # Сохраняем статус в файл
    task_file = TASKS_DIR / f"{task_id}.json"
    with open(task_file, "w", encoding="utf-8") as f:
        f.write(tasks[task_id].json())
    
    # Запускаем обработку в фоновом режиме
    if is_transcript:
        # Если это текстовый файл или нестандартный JSON, преобразуем его
        try:
            # Проверяем, нужно ли преобразование
            need_conversion = True
            if file_path.suffix.lower() == '.json':
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # Проверяем, что формат уже подходит
                    if (isinstance(data, list) and all(isinstance(item, dict) and 'text' in item for item in data)) or \
                       (isinstance(data, dict) and 'segments' in data):
                        need_conversion = False
                except (json.JSONDecodeError, UnicodeDecodeError):
                    need_conversion = True
            
            if need_conversion:
                logger.info(f"Converting file {file_path} to transcript format")
                # Преобразуем файл в формат транскрипта
                segments = convert_file_to_transcript_format(file_path)
                
                # Сохраняем преобразованный транскрипт в новый файл
                converted_path = UPLOAD_DIR / f"{task_id}_converted.json"
                save_transcript_format(segments, converted_path)
                
                # Используем преобразованный файл для дальнейшей обработки
                file_path = converted_path
                
                # Обновляем статус задачи
                update_task_status(task_id, "pending", 0.1, f"Файл преобразован в формат транскрипта")
        except Exception as e:
            logger.error(f"Error converting file to transcript format: {e}", exc_info=True)
            update_task_status(task_id, "failed", 0.0, f"Ошибка преобразования файла: {str(e)}")
            return {"task_id": task_id, "status": "failed", "message": f"Ошибка преобразования файла: {str(e)}"}
            
        background_tasks.add_task(process_transcript_task, file_path, task_id, task_data)
    else:
        background_tasks.add_task(process_audio_task, file_path, task_id, task_data)
    
    return {"task_id": task_id, "status": "pending", "message": "Файл загружен и поставлен в очередь на обработку"}

@app.post("/api/upload-transcript")
async def upload_transcript(
    background_tasks: BackgroundTasks,
    transcript_file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    date: Optional[str] = Form(None),
    skip_notifications: bool = Form(True)
):
    """Загрузка и обработка транскрипта"""
    # Проверяем расширение файла
    file_ext = os.path.splitext(transcript_file.filename)[1].lower()
    if file_ext != ".json":
        raise HTTPException(status_code=400, detail="Транскрипт должен быть в формате JSON")
    
    # Создаем уникальный идентификатор задачи
    task_id = str(uuid.uuid4())
    
    # Сохраняем файл
    transcript_path = UPLOAD_DIR / f"{task_id}{file_ext}"
    with open(transcript_path, "wb") as f:
        f.write(await transcript_file.read())
    
    # Создаем задачу
    task_data = TaskCreate(
        title=title,
        language=language,
        date=date or datetime.now().strftime("%Y-%m-%d"),
        skip_notifications=skip_notifications
    )
    
    # Создаем запись о задаче
    tasks[task_id] = TaskStatus(
        task_id=task_id,
        status="pending",
        progress=0.0,
        message="Задача создана",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    
    # Сохраняем статус в файл
    task_file = TASKS_DIR / f"{task_id}.json"
    with open(task_file, "w", encoding="utf-8") as f:
        f.write(tasks[task_id].json())
    
    # Запускаем обработку в фоновом режиме
    background_tasks.add_task(process_transcript_task, transcript_path, task_id, task_data)
    
    return {"task_id": task_id, "status": "pending", "message": "Транскрипт загружен и поставлен в очередь на обработку"}

@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Получение статуса задачи"""
    # Проверяем, есть ли задача в памяти
    if task_id in tasks:
        return tasks[task_id]
    
    # Если нет в памяти, проверяем файл
    task_file = TASKS_DIR / f"{task_id}.json"
    if task_file.exists():
        with open(task_file, "r", encoding="utf-8") as f:
            task_data = json.load(f)
            tasks[task_id] = TaskStatus(**task_data)
            return tasks[task_id]
    
    raise HTTPException(status_code=404, detail="Задача не найдена")

@app.get("/api/tasks")
async def get_all_tasks():
    """Получение списка всех задач"""
    # Загружаем все задачи из файлов
    all_tasks = []
    for task_file in TASKS_DIR.glob("*.json"):
        with open(task_file, "r", encoding="utf-8") as f:
            task_data = json.load(f)
            all_tasks.append(TaskStatus(**task_data))
    
    # Сортируем по времени создания (новые сверху)
    all_tasks.sort(key=lambda x: x.created_at, reverse=True)
    
    return all_tasks

@app.get("/api/v1/tasks")
async def get_all_tasks_v1():
    """Получение списка всех задач (API v1)"""
    # Загружаем все задачи из файлов
    all_tasks = []
    for task_file in TASKS_DIR.glob("*.json"):
        with open(task_file, "r", encoding="utf-8") as f:
            task_data = json.load(f)
            all_tasks.append(TaskStatus(**task_data))
    
    # Сортируем по времени создания (новые сверху)
    all_tasks.sort(key=lambda x: x.created_at, reverse=True)
    
    return {"tasks": all_tasks}

@app.get("/api/download/{task_id}/{file_type}")
async def download_file(task_id: str, file_type: str):
    """Скачивание файла результата"""
    # Проверяем, есть ли задача
    task_file = TASKS_DIR / f"{task_id}.json"
    if not task_file.exists():
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    # Загружаем данные задачи
    with open(task_file, "r", encoding="utf-8") as f:
        task_data = json.load(f)
    
    # Проверяем статус задачи
    if task_data["status"] != "completed":
        raise HTTPException(status_code=400, detail="Задача еще не завершена")
    
    # Определяем путь к файлу
    if file_type == "markdown":
        file_path = task_data["result"]["markdown_file"]
    elif file_type == "json":
        file_path = task_data["result"]["json_file"]
    else:
        raise HTTPException(status_code=400, detail="Неизвестный тип файла")
    
    # Проверяем существование файла
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    # Возвращаем файл
    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type="text/markdown" if file_type == "markdown" else "application/json"
    )

# Запуск сервера (если файл запущен напрямую)
if __name__ == "__main__":
    uvicorn.run("app.web.main:app", host="0.0.0.0", port=8000, reload=True)
