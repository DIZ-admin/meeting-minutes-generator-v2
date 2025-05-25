#!/usr/bin/env python3
"""
JWT Authentication Middleware для FastAPI
"""
from typing import Optional, List
from fastapi import HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.services.auth_service_enhanced import get_auth_service, User, UserRole
from app.utils.logging import get_default_logger

logger = get_default_logger(__name__)

# Security схема для JWT Bearer токенов
security = HTTPBearer()

class TokenPayload(BaseModel):
    """Payload JWT токена"""
    sub: str
    user_id: str
    role: str
    email: str
    exp: int
    iat: int
    type: str

class AuthorizedUser(BaseModel):
    """Авторизованный пользователь из токена"""
    username: str
    user_id: str
    email: str
    role: UserRole
    
    @classmethod
    def from_payload(cls, payload: dict) -> 'AuthorizedUser':
        """Создаёт пользователя из JWT payload"""
        return cls(
            username=payload["sub"],
            user_id=payload["user_id"],
            email=payload["email"],
            role=UserRole(payload["role"])
        )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> AuthorizedUser:
    """
    Dependency для получения текущего пользователя из JWT токена
    
    Raises:
        HTTPException: Если токен невалиден или истёк
    """
    token = credentials.credentials
    
    # Получаем auth service
    auth_service = await get_auth_service()
    
    # Верифицируем токен
    payload = await auth_service.verify_token(token)
    
    if not payload:
        logger.warning(f"Invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Проверяем тип токена
    if payload.get("type") != "access":
        logger.warning(f"Invalid token type: {payload.get('type')}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Создаём авторизованного пользователя
    return AuthorizedUser.from_payload(payload)

async def get_current_active_user(
    current_user: AuthorizedUser = Depends(get_current_user)
) -> AuthorizedUser:
    """
    Dependency для проверки, что пользователь активен
    
    Raises:
        HTTPException: Если пользователь неактивен
    """
    # Получаем auth service
    auth_service = await get_auth_service()
    
    # Проверяем активность пользователя
    user = await auth_service.get_user_by_username(current_user.username)
    
    if not user or not user.is_active:
        logger.warning(f"User {current_user.username} is inactive")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return current_user

def require_role(allowed_roles: List[UserRole]):
    """
    Dependency factory для проверки ролей пользователя
    
    Args:
        allowed_roles: Список разрешённых ролей
        
    Usage:
        @router.get("/admin", dependencies=[Depends(require_role([UserRole.ADMIN]))])
    """
    async def role_checker(
        current_user: AuthorizedUser = Depends(get_current_active_user)
    ) -> AuthorizedUser:
        if current_user.role not in allowed_roles:
            logger.warning(
                f"User {current_user.username} with role {current_user.role.value} "
                f"attempted to access resource requiring roles {[r.value for r in allowed_roles]}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {[r.value for r in allowed_roles]}"
            )
        return current_user
    
    return role_checker

def require_admin():
    """Dependency для endpoints, требующих роль администратора"""
    return require_role([UserRole.ADMIN])

def require_user_or_admin():
    """Dependency для endpoints, требующих роль пользователя или администратора"""
    return require_role([UserRole.USER, UserRole.ADMIN])

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[AuthorizedUser]:
    """
    Dependency для опциональной аутентификации
    Возвращает пользователя если токен есть и валиден, иначе None
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None

# Rate limiting middleware
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio

class RateLimiter:
    """Простой rate limiter для защиты API"""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)
        self.cleanup_interval = 60  # секунд
        self._cleanup_task = None
    
    async def start(self):
        """Запускает фоновую очистку"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop(self):
        """Останавливает фоновую очистку"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def _cleanup_loop(self):
        """Периодически очищает старые записи"""
        while True:
            await asyncio.sleep(self.cleanup_interval)
            self._cleanup_old_requests()
    
    def _cleanup_old_requests(self):
        """Удаляет записи старше минуты"""
        cutoff = datetime.now() - timedelta(minutes=1)
        
        for key in list(self.requests.keys()):
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if req_time > cutoff
            ]
            if not self.requests[key]:
                del self.requests[key]
    
    def check_rate_limit(self, key: str) -> bool:
        """
        Проверяет rate limit для ключа
        
        Args:
            key: Уникальный ключ (например, IP или user_id)
            
        Returns:
            True если запрос разрешён, False если превышен лимит
        """
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Удаляем старые запросы
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if req_time > minute_ago
        ]
        
        # Проверяем лимит
        if len(self.requests[key]) >= self.requests_per_minute:
            return False
        
        # Добавляем новый запрос
        self.requests[key].append(now)
        return True

# Глобальный rate limiter
rate_limiter = RateLimiter(requests_per_minute=60)

async def check_rate_limit(
    current_user: Optional[AuthorizedUser] = Depends(get_optional_user),
    client_ip: Optional[str] = None  # Будет заполнено middleware
):
    """
    Dependency для проверки rate limit
    
    Raises:
        HTTPException: Если превышен rate limit
    """
    # Используем user_id если есть, иначе IP
    key = current_user.user_id if current_user else (client_ip or "anonymous")
    
    if not rate_limiter.check_rate_limit(key):
        logger.warning(f"Rate limit exceeded for {key}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later."
        )
