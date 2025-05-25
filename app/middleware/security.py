"""
Middleware для безопасности приложения
"""
from typing import Callable, Dict, Any, Optional, List
from datetime import datetime, timedelta
import re
import time
import hashlib
from collections import defaultdict

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import Headers

from ..utils.logging import get_default_logger

logger = get_default_logger(__name__)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware для добавления заголовков безопасности
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Добавляем заголовки безопасности
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), "
            "gyroscope=(), magnetometer=(), microphone=(), "
            "payment=(), usb=()"
        )
        
        return response

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware для ограничения скорости запросов (Rate Limiting)
    """
    
    def __init__(
        self,
        app,
        calls: int = 100,
        period: int = 60,
        exclude_paths: Optional[List[str]] = None
    ):
        """
        Инициализация Rate Limiter
        
        Args:
            app: FastAPI приложение
            calls: Количество разрешенных вызовов
            period: Период в секундах
            exclude_paths: Пути, исключенные из rate limiting
        """
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.exclude_paths = exclude_paths or ["/health", "/metrics"]
        self.clients: Dict[str, List[float]] = defaultdict(list)
    
    def _get_client_id(self, request: Request) -> str:
        """Получает идентификатор клиента"""
        # Пытаемся получить IP из заголовков прокси
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # Иначе используем client.host
        return request.client.host if request.client else "unknown"
    
    def _is_rate_limited(self, client_id: str) -> bool:
        """Проверяет, превышен ли лимит"""
        now = time.time()
        
        # Удаляем старые записи
        self.clients[client_id] = [
            timestamp for timestamp in self.clients[client_id]
            if timestamp > now - self.period
        ]
        
        # Проверяем лимит
        if len(self.clients[client_id]) >= self.calls:
            return True
        
        # Добавляем текущий запрос
        self.clients[client_id].append(now)
        return False

    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Проверяем, исключен ли путь
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        # Получаем ID клиента
        client_id = self._get_client_id(request)
        
        # Проверяем rate limit
        if self._is_rate_limited(client_id):
            logger.warning(f"Rate limit exceeded for client: {client_id}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": self.period
                },
                headers={
                    "Retry-After": str(self.period),
                    "X-RateLimit-Limit": str(self.calls),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + self.period))
                }
            )
        
        # Обрабатываем запрос
        response = await call_next(request)
        
        # Добавляем заголовки rate limit
        remaining = self.calls - len(self.clients[client_id])
        response.headers["X-RateLimit-Limit"] = str(self.calls)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + self.period))
        
        return response

class InputValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware для валидации входных данных
    """
    
    # Паттерны для обнаружения потенциально опасных входных данных
    DANGEROUS_PATTERNS = [
        # SQL Injection
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE)\b)",
        # XSS
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        # Path Traversal
        r"\.\./",
        r"\.\.\\",
        # Command Injection
        r"[;&|`$]",
    ]
    
    def __init__(self, app, max_body_size: int = 10 * 1024 * 1024):  # 10MB по умолчанию
        super().__init__(app)
        self.max_body_size = max_body_size
        self.dangerous_patterns = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.DANGEROUS_PATTERNS
        ]
    
    def _contains_dangerous_content(self, text: str) -> bool:
        """Проверяет, содержит ли текст опасные паттерны"""
        for pattern in self.dangerous_patterns:
            if pattern.search(text):
                return True
        return False
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Проверяем размер тела запроса
        if request.headers.get("content-length"):
            content_length = int(request.headers["content-length"])
            if content_length > self.max_body_size:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request body too large"}
                )
        
        # Проверяем query параметры
        for param_name, param_value in request.query_params.items():
            if self._contains_dangerous_content(str(param_value)):
                logger.warning(
                    f"Dangerous content detected in query parameter '{param_name}' "
                    f"from {request.client.host if request.client else 'unknown'}"
                )
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid input detected"}
                )
        
        # Пропускаем запрос дальше
        return await call_next(request)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для логирования запросов
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Записываем время начала
        start_time = time.time()
        
        # Получаем информацию о клиенте
        client_host = request.client.host if request.client else "unknown"
        
        # Логируем входящий запрос
        logger.info(
            f"Incoming request: {request.method} {request.url.path} "
            f"from {client_host}"
        )
        
        try:
            # Обрабатываем запрос
            response = await call_next(request)
            
            # Вычисляем время обработки
            process_time = time.time() - start_time
            
            # Логируем результат
            logger.info(
                f"Request completed: {request.method} {request.url.path} "
                f"- Status: {response.status_code} "
                f"- Time: {process_time:.3f}s"
            )
            
            # Добавляем заголовок с временем обработки
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except Exception as e:
            # Логируем ошибку
            process_time = time.time() - start_time
            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"- Error: {str(e)} "
                f"- Time: {process_time:.3f}s",
                exc_info=True
            )
            
            # Возвращаем ошибку
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"}
            )
