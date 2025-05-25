"""
FastAPI веб-интерфейс для конвейера генерации протоколов совещаний
"""
import os
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from ..utils.logging import get_default_logger
from ..config.config import config
from ..utils.config_validator import get_config_health_status, is_config_healthy

from ..utils.cache import get_cache
from ..utils.metrics import get_metrics_collector
from .api_routes import router as api_router

class CustomJSONEncoder(json.JSONEncoder):
    """
    Кастомный JSON-энкодер для сериализации datetime и других объектов
    """
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)
from .auth_routes import router as auth_router
from .models import ErrorResponse

logger = get_default_logger(__name__)

# Настраиваем кастомный JSON-энкодер для FastAPI
def custom_json_encoder():
    """
    Функция для настройки кастомного JSON-энкодера в FastAPI
    """
    def default(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    return default

# Инициализируем FastAPI приложение
app = FastAPI(
    title="Meeting Protocol Generator",
    description="API для генерации протоколов совещаний из аудиозаписей",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    json_encoders={datetime: lambda dt: dt.isoformat(), date: lambda d: d.isoformat()}
)

# Добавляем маршруты API
app.include_router(api_router)
app.include_router(auth_router)

# Добавляем backward compatibility routes
from fastapi import APIRouter
compat_router = APIRouter(prefix="/api", tags=["Compatibility"])

# Импортируем функцию upload из api_routes
from .api_routes import upload_audio
compat_router.add_api_route("/upload", upload_audio, methods=["POST"])
app.include_router(compat_router)

# Настраиваем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настраиваем статические файлы и шаблоны
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# Переопределяем OpenAPI схему для добавления дополнительной информации
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Добавляем информацию о сервере
    openapi_schema["servers"] = [
        {
            "url": "/",
            "description": "Current server"
        }
    ]
    
    # Добавляем информацию о безопасности
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    
    # Добавляем требование авторизации для всех эндпоинтов
    openapi_schema["security"] = [{"bearerAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Обработчик исключений
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            detail=exc.detail,
            status_code=exc.status_code,
            path=request.url.path
        ).model_dump()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            detail=f"Internal Server Error: {str(exc)}",
            status_code=500,
            path=request.url.path
        ).model_dump()
    )

# Маршруты веб-интерфейса

@app.get("/", response_class=HTMLResponse, summary="Главная страница")
async def index(request: Request):
    """
    Главная страница с формой загрузки и списком задач
    """
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/upload", response_class=HTMLResponse, summary="Страница загрузки")
async def upload_page(request: Request):
    """
    Страница загрузки аудиофайлов
    """
    return templates.TemplateResponse("upload.html", {"request": request})

@app.get("/tasks", response_class=HTMLResponse, summary="Страница задач")
async def tasks_page(request: Request):
    """
    Страница с списком задач и их статусом
    """
    return templates.TemplateResponse("tasks.html", {"request": request})

@app.get("/protocols", response_class=HTMLResponse, summary="Страница протоколов")
async def protocols_page(request: Request):
    """
    Страница с списком протоколов
    """
    # Получаем ID протокола из параметров запроса, если есть
    protocol_id = request.query_params.get("id")
    return templates.TemplateResponse("protocols.html", {"request": request, "protocol_id": protocol_id})

# Health Check endpoint
@app.get("/health", tags=["Monitoring"])
async def health_check():
    """
    Health check endpoint для мониторинга состояния приложения
    
    Returns:
        JSON с информацией о здоровье системы
    """
    # Проверяем конфигурацию
    config_status = get_config_health_status()
    
    # Проверяем директории
    directories_status = {
        "uploads_dir": {
            "path": config.uploads_dir,
            "exists": os.path.exists(config.uploads_dir),
            "is_dir": os.path.isdir(config.uploads_dir) if os.path.exists(config.uploads_dir) else False,
            "writable": os.access(config.uploads_dir, os.W_OK) if os.path.exists(config.uploads_dir) else False
        },
        "output_dir": {
            "path": config.output_dir,
            "exists": os.path.exists(config.output_dir),
            "is_dir": os.path.isdir(config.output_dir) if os.path.exists(config.output_dir) else False,
            "writable": os.access(config.output_dir, os.W_OK) if os.path.exists(config.output_dir) else False
        },
        "prompt_templates_dir": {
            "path": config.prompt_templates_dir,
            "exists": os.path.exists(config.prompt_templates_dir),
            "is_dir": os.path.isdir(config.prompt_templates_dir) if os.path.exists(config.prompt_templates_dir) else False,
            "readable": os.access(config.prompt_templates_dir, os.R_OK) if os.path.exists(config.prompt_templates_dir) else False
        }
    }
    
    # Проверяем кеш
    cache_instance = get_cache()
    cache_status = {
        "initialized": cache_instance is not None,
        "type": type(cache_instance).__name__ if cache_instance else None,
        "size": cache_instance.size() if cache_instance and hasattr(cache_instance, "size") else None
    }
    
    # Проверяем метрики
    metrics_collector_instance = get_metrics_collector()
    metrics_status = {
        "initialized": metrics_collector_instance is not None,
        "type": type(metrics_collector_instance).__name__ if metrics_collector_instance else None
    }
    
    # Собираем общий статус
    status = {
        "status": "healthy" if is_config_healthy() else "unhealthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "config": config_status,
            "directories": directories_status,
            "cache": cache_status,
            "metrics": metrics_status,
        },
        "config": config_status,
        "directories": directories_status,
        "cache": cache_status,
        "metrics": metrics_status,
        "version": app.version
    }
    
    return status

# Prometheus метрики endpoint
@app.get("/metrics", tags=["Monitoring"])
async def metrics():
    """
    Prometheus метрики endpoint
    
    Returns:
        Метрики в формате Prometheus
    """
    metrics_collector = get_metrics_collector()
    
    if not metrics_collector:
        raise HTTPException(
            status_code=500,
            detail="Metrics collector is not initialized"
        )
    
    return metrics_collector.get_metrics()

# Запуск приложения
def start():
    """
    Запуск FastAPI приложения с помощью uvicorn
    """
    # Используем значения по умолчанию, если нет в конфигурации
    host = getattr(config, "web_host", "0.0.0.0")
    port = getattr(config, "web_port", 8080)
    reload = getattr(config, "debug_mode", False)
    
    logger.info(f"Starting web server on {host}:{port} (reload={reload})")
    
    uvicorn.run(
        "app.web.app:app",
        host=host,
        port=port,
        reload=reload
    )

if __name__ == "__main__":
    start()
