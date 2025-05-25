"""
FastAPI зависимости для аутентификации
"""
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .auth_service import AuthenticationService, UserInDB, TokenData
from ..utils.logging import get_default_logger
from ..config.config import config

logger = get_default_logger(__name__)

# Инициализируем глобальный экземпляр AuthenticationService
auth_service = AuthenticationService(
    secret_key=config.auth_secret_key if hasattr(config, 'auth_secret_key') else None,
    access_token_expire_minutes=config.access_token_expire_minutes if hasattr(config, 'access_token_expire_minutes') else 30,
    session_expire_hours=config.session_expire_hours if hasattr(config, 'session_expire_hours') else 24
)

# Security схема для JWT токенов
security = HTTPBearer()

async def get_current_user_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData:
    """
    Получает текущего пользователя из JWT токена
    
    Args:
        credentials: Авторизационные данные
        
    Returns:
        Данные из токена
        
    Raises:
        HTTPException: Если токен невалидный
    """
    try:
        token_data = auth_service.decode_token(credentials.credentials)
        return token_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(
    token_data: TokenData = Depends(get_current_user_token)
) -> UserInDB:
    """
    Получает текущего пользователя
    
    Args:
        token_data: Данные из токена
        
    Returns:
        Пользователь
        
    Raises:
        HTTPException: Если пользователь не найден
    """
    user = auth_service.get_user(token_data.username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return user

async def get_current_active_user(
    current_user: UserInDB = Depends(get_current_user)
) -> UserInDB:
    """
    Получает текущего активного пользователя
    
    Args:
        current_user: Текущий пользователь
        
    Returns:
        Активный пользователь
        
    Raises:
        HTTPException: Если пользователь неактивен
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

class RoleChecker:
    """
    Dependency для проверки ролей пользователя
    
    Пример использования:
        @app.get("/admin", dependencies=[Depends(RoleChecker(["admin"]))])
        async def admin_endpoint():
            return {"message": "Admin only content"}
    """
    
    def __init__(self, required_roles: List[str], require_all: bool = False):
        """
        Инициализация проверки ролей
        
        Args:
            required_roles: Список требуемых ролей
            require_all: Если True, требуются все роли, иначе хотя бы одна
        """
        self.required_roles = required_roles
        self.require_all = require_all
    
    async def __call__(self, current_user: UserInDB = Depends(get_current_active_user)):
        """
        Проверяет роли пользователя
        
        Args:
            current_user: Текущий пользователь
            
        Raises:
            HTTPException: Если у пользователя нет необходимых ролей
        """
        if not auth_service.check_permission(
            current_user.roles,
            self.required_roles,
            self.require_all
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )

# Предустановленные проверки ролей
require_admin = RoleChecker(["admin"])
require_moderator = RoleChecker(["moderator", "admin"])
require_user = RoleChecker(["user"])

async def get_current_session(request: Request) -> Optional[str]:
    """
    Получает ID текущей сессии из cookies
    
    Args:
        request: FastAPI Request объект
        
    Returns:
        ID сессии или None
    """
    return request.cookies.get("session_id")

async def get_current_user_from_session(
    session_id: Optional[str] = Depends(get_current_session)
) -> Optional[UserInDB]:
    """
    Получает пользователя из сессии
    
    Args:
        session_id: ID сессии
        
    Returns:
        Пользователь или None
    """
    if not session_id:
        return None
        
    session = auth_service.get_session(session_id)
    if not session:
        return None
        
    user = auth_service.get_user(session.username)
    return user

async def require_session_auth(
    user: Optional[UserInDB] = Depends(get_current_user_from_session)
) -> UserInDB:
    """
    Требует аутентификацию через сессию
    
    Args:
        user: Пользователь из сессии
        
    Returns:
        Аутентифицированный пользователь
        
    Raises:
        HTTPException: Если пользователь не аутентифицирован
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session authentication required"
        )
    return user
