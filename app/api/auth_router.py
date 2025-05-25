#!/usr/bin/env python3
"""
Authentication API endpoints
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field

from app.services.auth_service_enhanced import get_auth_service, UserRole, AuthToken
from app.middleware.auth_middleware import (
    get_current_active_user, 
    AuthorizedUser,
    require_admin,
    check_rate_limit
)
from app.utils.logging import get_default_logger

logger = get_default_logger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    dependencies=[Depends(check_rate_limit)]  # Rate limiting для всех endpoints
)

# Pydantic models для API

class UserRegisterRequest(BaseModel):
    """Запрос на регистрацию пользователя"""
    username: str = Field(..., min_length=3, max_length=50, regex="^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    role: Optional[UserRole] = UserRole.USER

class UserLoginRequest(BaseModel):
    """Запрос на вход пользователя"""
    username: str
    password: str

class TokenResponse(BaseModel):
    """Ответ с токенами"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int

class RefreshTokenRequest(BaseModel):
    """Запрос на обновление токена"""
    refresh_token: str

class UserResponse(BaseModel):
    """Ответ с информацией о пользователе"""
    id: str
    username: str
    email: str
    role: UserRole
    is_active: bool
    created_at: str
    last_login: Optional[str] = None

class UserUpdateRoleRequest(BaseModel):
    """Запрос на обновление роли пользователя"""
    role: UserRole

# API Endpoints

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    request: UserRegisterRequest,
    current_admin: AuthorizedUser = Depends(require_admin())  # Только админ может регистрировать пользователей
):
    """
    Регистрирует нового пользователя (только для администраторов)
    """
    try:
        auth_service = await get_auth_service()
        
        # Регистрируем пользователя
        user = await auth_service.register_user(
            username=request.username,
            email=request.email,
            password=request.password,
            role=request.role
        )
        
        logger.info(f"User '{user.username}' registered by admin '{current_admin.username}'")
        
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at.isoformat(),
            last_login=user.last_login.isoformat() if user.last_login else None
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user"
        )

@router.post("/login", response_model=TokenResponse)
async def login(request: UserLoginRequest):
    """
    Аутентифицирует пользователя и возвращает JWT токены
    """
    try:
        auth_service = await get_auth_service()
        
        # Аутентифицируем пользователя
        user = await auth_service.authenticate_user(
            username=request.username,
            password=request.password
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Создаём токены
        tokens = await auth_service.create_tokens(user)
        
        logger.info(f"User '{user.username}' logged in successfully")
        
        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    """
    Обновляет access token используя refresh token
    """
    try:
        auth_service = await get_auth_service()
        
        # Обновляем токены
        tokens = await auth_service.refresh_access_token(request.refresh_token)
        
        if not tokens:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )

@router.post("/logout")
async def logout(
    refresh_token: Optional[str] = None,
    current_user: AuthorizedUser = Depends(get_current_active_user)
):
    """
    Выход пользователя (отзыв refresh token)
    """
    try:
        if refresh_token:
            auth_service = await get_auth_service()
            await auth_service.revoke_refresh_token(refresh_token)
            logger.info(f"User '{current_user.username}' logged out and refresh token revoked")
        else:
            logger.info(f"User '{current_user.username}' logged out")
        
        return {"message": "Successfully logged out"}
        
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        # Даже если произошла ошибка, считаем logout успешным
        return {"message": "Logged out"}

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: AuthorizedUser = Depends(get_current_active_user)
):
    """
    Получает информацию о текущем пользователе
    """
    try:
        auth_service = await get_auth_service()
        user = await auth_service.get_user_by_username(current_user.username)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at.isoformat(),
            last_login=user.last_login.isoformat() if user.last_login else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )

@router.get("/users", response_model=List[UserResponse])
async def get_all_users(
    limit: int = 100,
    offset: int = 0,
    current_admin: AuthorizedUser = Depends(require_admin())
):
    """
    Получает список всех пользователей (только для администраторов)
    """
    try:
        auth_service = await get_auth_service()
        users = await auth_service.get_all_users(limit=limit, offset=offset)
        
        return [
            UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at.isoformat(),
                last_login=user.last_login.isoformat() if user.last_login else None
            )
            for user in users
        ]
        
    except Exception as e:
        logger.error(f"Error getting users list: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get users list"
        )

@router.put("/users/{username}/role", response_model=UserResponse)
async def update_user_role(
    username: str,
    request: UserUpdateRoleRequest,
    current_admin: AuthorizedUser = Depends(require_admin())
):
    """
    Обновляет роль пользователя (только для администраторов)
    """
    try:
        auth_service = await get_auth_service()
        
        # Обновляем роль
        success = await auth_service.update_user_role(username, request.role)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Получаем обновлённого пользователя
        user = await auth_service.get_user_by_username(username)
        
        logger.info(f"User '{username}' role updated to '{request.role.value}' by admin '{current_admin.username}'")
        
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at.isoformat(),
            last_login=user.last_login.isoformat() if user.last_login else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user role"
        )

@router.delete("/users/{username}")
async def deactivate_user(
    username: str,
    current_admin: AuthorizedUser = Depends(require_admin())
):
    """
    Деактивирует пользователя (только для администраторов)
    """
    try:
        # Защита от деактивации самого себя
        if username == current_admin.username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account"
            )
        
        auth_service = await get_auth_service()
        success = await auth_service.deactivate_user(username)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        logger.info(f"User '{username}' deactivated by admin '{current_admin.username}'")
        
        return {"message": f"User '{username}' has been deactivated"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate user"
        )

@router.get("/stats")
async def get_auth_statistics(
    current_admin: AuthorizedUser = Depends(require_admin())
):
    """
    Получает статистику аутентификации (только для администраторов)
    """
    try:
        auth_service = await get_auth_service()
        stats = await auth_service.get_auth_statistics()
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting auth statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get statistics"
        )
