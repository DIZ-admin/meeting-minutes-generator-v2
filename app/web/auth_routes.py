"""
API эндпоинты для аутентификации
"""
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm

from ..services.auth_service import UserCreate, Token, UserInDB
from ..services.auth_dependencies import (
    auth_service,
    get_current_active_user,
    require_admin,
    get_current_session
)
from ..utils.logging import get_default_logger

logger = get_default_logger(__name__)

# Создаем роутер для аутентификации
router = APIRouter(
    prefix="/auth",
    tags=["authentication"]
)

@router.post("/register", response_model=dict)
async def register(
    user_create: UserCreate
):
    """
    Регистрация нового пользователя
    
    Args:
        user_create: Данные для создания пользователя
        
    Returns:
        Сообщение об успешной регистрации
        
    Raises:
        HTTPException: Если пользователь уже существует
    """
    try:
        user = auth_service.create_user(user_create)
        return {
            "message": "User registered successfully",
            "username": user.username,
            "email": user.email
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    response: Response = None
):
    """
    Аутентификация пользователя и получение токена
    
    Args:
        form_data: Данные формы с username и password
        response: Response объект для установки cookies
        
    Returns:
        JWT токен
        
    Raises:
        HTTPException: Если аутентификация не удалась
    """
    user = auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Создаем токен
    access_token = auth_service.create_access_token(user)
    
    # Создаем сессию
    session = auth_service.create_session(user)
    
    # Устанавливаем cookie с session_id
    if response:
        response.set_cookie(
            key="session_id",
            value=session.session_id,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=auth_service.session_expire_hours * 3600
        )
    
    return access_token

@router.post("/logout")
async def logout(
    response: Response,
    session_id: Optional[str] = Depends(get_current_session),
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    Выход пользователя (инвалидация сессии)
    
    Args:
        response: Response объект для удаления cookies
        session_id: ID текущей сессии
        current_user: Текущий пользователь
        
    Returns:
        Сообщение об успешном выходе
    """
    # Инвалидируем текущую сессию
    if session_id:
        auth_service.invalidate_session(session_id)
    
    # Удаляем cookie
    response.delete_cookie("session_id")
    
    return {"message": "Successfully logged out"}

@router.get("/me")
async def get_current_user_info(
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    Получает информацию о текущем пользователе
    
    Args:
        current_user: Текущий пользователь
        
    Returns:
        Информация о пользователе
    """
    return {
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "roles": current_user.roles,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat()
    }

@router.post("/refresh", response_model=Token)
async def refresh_token(
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    Обновляет JWT токен
    
    Args:
        current_user: Текущий пользователь
        
    Returns:
        Новый JWT токен
    """
    access_token = auth_service.create_access_token(current_user)
    return access_token

@router.get("/sessions")
async def get_user_sessions(
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    Получает активные сессии пользователя
    
    Args:
        current_user: Текущий пользователь
        
    Returns:
        Список активных сессий
    """
    sessions = auth_service.get_active_sessions(current_user.id)
    return {
        "sessions": [
            {
                "session_id": session.session_id,
                "created_at": session.created_at.isoformat(),
                "expires_at": session.expires_at.isoformat(),
                "user_agent": session.user_agent,
                "ip_address": session.ip_address
            }
            for session in sessions
        ]
    }

@router.delete("/sessions/{session_id}")
async def invalidate_session(
    session_id: str,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    Инвалидирует конкретную сессию
    
    Args:
        session_id: ID сессии для инвалидации
        current_user: Текущий пользователь
        
    Returns:
        Результат операции
    """
    session = auth_service.get_session(session_id)
    
    if not session or session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    success = auth_service.invalidate_session(session_id)
    
    return {
        "success": success,
        "message": "Session invalidated" if success else "Failed to invalidate session"
    }

# Административные эндпоинты
@router.get("/admin/users", dependencies=[Depends(require_admin)])
async def list_users():
    """
    Получает список всех пользователей (только для админов)
    
    Returns:
        Список пользователей
    """
    users = list(auth_service.users.values())
    return {
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "roles": user.roles,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat()
            }
            for user in users
        ]
    }

@router.put("/admin/users/{username}/roles", dependencies=[Depends(require_admin)])
async def update_user_roles(
    username: str,
    roles: list[str]
):
    """
    Обновляет роли пользователя (только для админов)
    
    Args:
        username: Имя пользователя
        roles: Новый список ролей
        
    Returns:
        Обновленная информация о пользователе
    """
    user = auth_service.get_user(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Обновляем роли
    user.roles = roles
    auth_service._save_data()
    
    return {
        "username": user.username,
        "roles": user.roles,
        "message": "Roles updated successfully"
    }

@router.delete("/admin/sessions/cleanup", dependencies=[Depends(require_admin)])
async def cleanup_sessions():
    """
    Очищает истекшие сессии (только для админов)
    
    Returns:
        Количество удаленных сессий
    """
    count = auth_service.cleanup_expired_sessions()
    return {
        "cleaned_sessions": count,
        "message": f"Cleaned up {count} expired sessions"
    }
