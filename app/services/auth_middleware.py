#!/usr/bin/env python3
"""
Authentication middleware для FastAPI
Интеграция AuthenticationService с веб-приложением
"""
from typing import Optional, Dict, Any
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Request

from app.services.auth_service import get_auth_service, AuthenticationService, UserRole

# Security scheme для FastAPI
security = HTTPBearer()

class AuthMiddleware:
    """Middleware для аутентификации и авторизации"""
    
    def __init__(self, auth_service: AuthenticationService):
        self.auth_service = auth_service
    
    def get_current_user_data(
        self, 
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> Dict[str, Any]:
        """
        Получает данные текущего пользователя из JWT токена
        
        Args:
            credentials: HTTP авторизация
            
        Returns:
            Данные пользователя из токена
            
        Raises:
            HTTPException: Если токен невалиден
        """
        token = credentials.credentials
        user_data = self.auth_service.verify_token(token)
        
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user_data
    
    def require_role(self, required_role: UserRole):
        """
        Создает dependency для проверки роли пользователя
        
        Args:
            required_role: Требуемая роль
            
        Returns:
            Dependency function
        """
        def role_checker(user_data: Dict[str, Any] = Depends(self.get_current_user_data)):
            user_role = UserRole(user_data.get("role"))
            
            # Админы имеют доступ ко всему
            if user_role == UserRole.ADMIN:
                return user_data
            
            # Проверяем конкретную роль
            if user_role != required_role:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Required role: {required_role.value}",
                )
            
            return user_data
        
        return role_checker
    
    def require_admin(self, user_data: Dict[str, Any] = Depends(None)):
        """Dependency для проверки прав администратора"""
        if user_data is None:
            user_data = self.get_current_user_data()
        
        user_role = UserRole(user_data.get("role"))
        
        if user_role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
        
        return user_data

# Глобальный экземпляр middleware
def get_auth_middleware() -> AuthMiddleware:
    """Получает экземпляр auth middleware"""
    auth_service = get_auth_service()
    return AuthMiddleware(auth_service)

# Готовые dependencies для использования в endpoints
def get_current_user(
    auth_middleware: AuthMiddleware = Depends(get_auth_middleware)
) -> Dict[str, Any]:
    """Dependency для получения текущего пользователя"""
    return auth_middleware.get_current_user_data()

def require_admin_user(
    auth_middleware: AuthMiddleware = Depends(get_auth_middleware)
) -> Dict[str, Any]:
    """Dependency для проверки прав администратора"""
    return auth_middleware.require_admin()

def require_user_role(
    auth_middleware: AuthMiddleware = Depends(get_auth_middleware)
) -> Dict[str, Any]:
    """Dependency для проверки роли USER"""
    return auth_middleware.require_role(UserRole.USER)()
