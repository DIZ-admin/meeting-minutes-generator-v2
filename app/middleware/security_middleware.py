#!/usr/bin/env python3
"""
Security Middleware для FastAPI
Обеспечивает дополнительную защиту приложения
"""
from typing import Callable
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import time
import re

from app.utils.logging import get_default_logger

logger = get_default_logger(__name__)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Добавляет security headers к ответам"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Добавляем security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.openai.com https://api.anthropic.com;"
        )
        response.headers["Content-Security-Policy"] = csp
        
        return response

class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Валидирует входящие запросы"""
    
    def __init__(self, app, max_content_length: int = 10 * 1024 * 1024):  # 10MB по умолчанию
        super().__init__(app)
        self.max_content_length = max_content_length
        
        # Паттерны для обнаружения потенциально опасных входных данных
        self.dangerous_patterns = [
            re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
            re.compile(r'javascript:', re.IGNORECASE),
            re.compile(r'on\w+\s*=', re.IGNORECASE),  # onclick, onload, etc.
            re.compile(r'<iframe', re.IGNORECASE),
            re.compile(r'<object', re.IGNORECASE),
            re.compile(r'<embed', re.IGNORECASE),
            re.compile(r'<form', re.IGNORECASE),
            # SQL injection patterns
            re.compile(r"('\s*(OR|AND)\s*')|(-{2})|(/\*.*\*/)", re.IGNORECASE),
            re.compile(r'(UNION\s+SELECT)|(INSERT\s+INTO)|(DELETE\s+FROM)|(DROP\s+TABLE)', re.IGNORECASE),
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Проверяем размер контента
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_content_length:
            logger.warning(f"Request content too large: {content_length} bytes")
            return JSONResponse(
                status_code=413,
                content={"detail": "Request content too large"}
            )
        
        # Проверяем path на опасные паттерны
        if self._contains_dangerous_content(request.url.path):
            logger.warning(f"Dangerous content in path: {request.url.path}")
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid request"}
            )
        
        # Проверяем query parameters
        for param_value in request.query_params.values():
            if self._contains_dangerous_content(param_value):
                logger.warning(f"Dangerous content in query params: {param_value}")
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid query parameters"}
                )
        
        response = await call_next(request)
        return response
    
    def _contains_dangerous_content(self, content: str) -> bool:
        """Проверяет содержимое на опасные паттерны"""
        return any(pattern.search(content) for pattern in self.dangerous_patterns)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Логирует все запросы для аудита"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Засекаем время начала
        start_time = time.time()
        
        # Получаем client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Логируем запрос
        logger.info(
            f"Request: {request.method} {request.url.path} "
            f"from {client_ip} "
            f"User-Agent: {request.headers.get('user-agent', 'unknown')}"
        )
        
        # Обрабатываем запрос
        response = await call_next(request)
        
        # Вычисляем время обработки
        process_time = time.time() - start_time
        
        # Логируем ответ
        logger.info(
            f"Response: {request.method} {request.url.path} "
            f"Status: {response.status_code} "
            f"Time: {process_time:.3f}s"
        )
        
        # Добавляем header с временем обработки
        response.headers["X-Process-Time"] = str(process_time)
        
        return response

def setup_security_middleware(app):
    """
    Настраивает все security middleware для приложения
    
    Args:
        app: FastAPI application instance
    """
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8000"],  # В production настроить правильно
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time"],
    )
    
    # Trusted host middleware
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "*.meeting-protocol.local"]
    )
    
    # Custom security middleware
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    
    logger.info("Security middleware configured")
