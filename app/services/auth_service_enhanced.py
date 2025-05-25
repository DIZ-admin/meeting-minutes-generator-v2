#!/usr/bin/env python3
"""
Enhanced Authentication Service - интегрирован с базой данных
Применяет Service Layer pattern для security management
"""
import os
import jwt
import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from enum import Enum

from app.utils.logging import get_default_logger
from app.services.database_service import get_database_service
from app.repositories.user_repository import UserRepository, UserEntity

logger = get_default_logger(__name__)

class UserRole(Enum):
    """Роли пользователей в системе"""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"

@dataclass
class User:
    """Модель пользователя"""
    id: str
    username: str
    email: str
    role: UserRole
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True
    
    @classmethod
    def from_entity(cls, entity: UserEntity) -> 'User':
        """Создаёт User из UserEntity"""
        return cls(
            id=entity.id,
            username=entity.username,
            email=entity.email,
            role=UserRole(entity.role),
            created_at=entity.created_at,
            last_login=entity.last_login,
            is_active=entity.is_active
        )

@dataclass
class AuthToken:
    """Модель токена аутентификации"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600  # 1 hour

class AuthenticationService:
    """
    Enhanced сервис для управления аутентификацией и авторизацией
    Теперь использует PostgreSQL для хранения данных
    """
    
    def __init__(self):
        """Инициализация сервиса аутентификации"""
        self.logger = get_default_logger(self.__class__.__name__)
        self.secret_key = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 60  # 1 hour
        self.refresh_token_expire_days = 30    # 30 days
        
        self._user_repository: Optional[UserRepository] = None
        self._db_service = None
        self._initialized = False
    
    async def initialize(self):
        """Асинхронная инициализация сервиса"""
        if self._initialized:
            return
        
        try:
            # Получаем database service
            self._db_service = await get_database_service()
            
            # Создаём репозиторий
            self._user_repository = UserRepository(self._db_service)
            
            # Создаём таблицы если их нет
            await self._user_repository.create_table()
            await self._create_refresh_tokens_table()
            
            # Создаём администратора по умолчанию
            await self._create_default_admin()
            
            self._initialized = True
            self.logger.info("Authentication service initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize authentication service: {e}")
            raise
    
    async def _create_refresh_tokens_table(self):
        """Создаёт таблицу для refresh токенов"""
        query = """
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id VARCHAR(255) PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR(255) NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(token_hash)
        );
        
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens(expires_at);
        """
        await self._db_service.execute(query)
    
    async def register_user(
        self, 
        username: str, 
        email: str, 
        password: str, 
        role: UserRole = UserRole.USER
    ) -> User:
        """
        Регистрирует нового пользователя
        
        Args:
            username: Имя пользователя
            email: Email пользователя
            password: Пароль в открытом виде
            role: Роль пользователя
            
        Returns:
            Созданный пользователь
            
        Raises:
            ValueError: Если пользователь уже существует
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Проверяем, что пользователь не существует
            existing_user = await self._user_repository.find_by_username(username)
            if existing_user:
                raise ValueError(f"User '{username}' already exists")
            
            # Проверяем email
            existing_email = await self._user_repository.find_by_email(email)
            if existing_email:
                raise ValueError(f"Email '{email}' already registered")
            
            # Валидируем пароль
            self._validate_password(password)
            
            # Создаем пользователя
            user_entity = UserEntity(
                id=secrets.token_urlsafe(16),
                username=username,
                email=email,
                password_hash=self._hash_password(password),
                role=role.value
            )
            
            # Сохраняем в базу
            created_entity = await self._user_repository.create(user_entity)
            user = User.from_entity(created_entity)
            
            self.logger.info(f"User '{username}' registered successfully with role '{role.value}'")
            return user
            
        except Exception as e:
            self.logger.error(f"Error registering user '{username}': {e}")
            raise
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Аутентифицирует пользователя
        
        Args:
            username: Имя пользователя
            password: Пароль в открытом виде
            
        Returns:
            Пользователь если аутентификация успешна, иначе None
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Получаем пользователя из базы
            user_entity = await self._user_repository.find_by_username(username)
            
            if not user_entity:
                self.logger.warning(f"Authentication failed: user '{username}' not found")
                return None
            
            # Проверяем активность пользователя
            if not user_entity.is_active:
                self.logger.warning(f"Authentication failed: user '{username}' is inactive")
                return None
            
            # Проверяем пароль
            if not self._verify_password(password, user_entity.password_hash):
                self.logger.warning(f"Authentication failed: invalid password for user '{username}'")
                return None
            
            # Обновляем время последнего входа
            await self._user_repository.update_last_login(user_entity.id)
            
            user = User.from_entity(user_entity)
            self.logger.info(f"User '{username}' authenticated successfully")
            return user
            
        except Exception as e:
            self.logger.error(f"Error authenticating user '{username}': {e}")
            return None
    
    async def create_tokens(self, user: User) -> AuthToken:
        """
        Создает JWT токены для пользователя
        
        Args:
            user: Пользователь
            
        Returns:
            Токены аутентификации
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Создаем access token
            access_payload = {
                "sub": user.username,
                "user_id": user.id,
                "role": user.role.value,
                "email": user.email,
                "exp": datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes),
                "iat": datetime.utcnow(),
                "type": "access"
            }
            
            access_token = jwt.encode(access_payload, self.secret_key, algorithm=self.algorithm)
            
            # Создаем refresh token
            refresh_token_id = secrets.token_urlsafe(32)
            refresh_payload = {
                "sub": user.username,
                "jti": refresh_token_id,
                "exp": datetime.utcnow() + timedelta(days=self.refresh_token_expire_days),
                "iat": datetime.utcnow(),
                "type": "refresh"
            }
            
            refresh_token = jwt.encode(refresh_payload, self.secret_key, algorithm=self.algorithm)
            
            # Сохраняем refresh token в базу
            await self._save_refresh_token(
                user.id, 
                refresh_token_id,
                refresh_payload["exp"]
            )
            
            self.logger.info(f"Tokens created for user '{user.username}'")
            
            return AuthToken(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=self.access_token_expire_minutes * 60
            )
            
        except Exception as e:
            self.logger.error(f"Error creating tokens for user '{user.username}': {e}")
            raise
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Верифицирует JWT токен
        
        Args:
            token: JWT токен
            
        Returns:
            Данные токена если валиден, иначе None
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Проверяем существование пользователя
            username = payload.get("sub")
            user_entity = await self._user_repository.find_by_username(username)
            
            if not user_entity:
                self.logger.warning(f"Token verification failed: user '{username}' not found")
                return None
            
            # Проверяем активность пользователя
            if not user_entity.is_active:
                self.logger.warning(f"Token verification failed: user '{username}' is inactive")
                return None
            
            return payload
            
        except jwt.ExpiredSignatureError:
            self.logger.warning("Token verification failed: token expired")
            return None
        except jwt.InvalidTokenError as e:
            self.logger.warning(f"Token verification failed: invalid token - {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error verifying token: {e}")
            return None
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[AuthToken]:
        """
        Обновляет access token используя refresh token
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            Новые токены если refresh token валиден, иначе None
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Проверяем refresh token
            payload = jwt.decode(refresh_token, self.secret_key, algorithms=[self.algorithm])
            
            if payload.get("type") != "refresh":
                self.logger.warning("Token refresh failed: invalid token type")
                return None
            
            username = payload.get("sub")
            token_id = payload.get("jti")
            
            # Проверяем токен в базе
            token_exists = await self._verify_refresh_token(token_id)
            if not token_exists:
                self.logger.warning(f"Token refresh failed: refresh token not found for user '{username}'")
                return None
            
            # Получаем пользователя
            user_entity = await self._user_repository.find_by_username(username)
            if not user_entity or not user_entity.is_active:
                self.logger.warning(f"Token refresh failed: user '{username}' not found or inactive")
                return None
            
            user = User.from_entity(user_entity)
            
            # Удаляем старый refresh token
            await self._revoke_refresh_token(token_id)
            
            # Создаем новые токены
            new_tokens = await self.create_tokens(user)
            
            self.logger.info(f"Tokens refreshed for user '{username}'")
            return new_tokens
            
        except jwt.ExpiredSignatureError:
            self.logger.warning("Token refresh failed: refresh token expired")
            return None
        except jwt.InvalidTokenError as e:
            self.logger.warning(f"Token refresh failed: invalid refresh token - {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error refreshing token: {e}")
            return None
    
    async def revoke_refresh_token(self, refresh_token: str) -> bool:
        """
        Отзывает refresh token
        
        Args:
            refresh_token: Refresh token для отзыва
            
        Returns:
            True если токен отозван, иначе False
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            payload = jwt.decode(refresh_token, self.secret_key, algorithms=[self.algorithm])
            token_id = payload.get("jti")
            
            if token_id:
                return await self._revoke_refresh_token(token_id)
            
            return False
                
        except Exception as e:
            self.logger.error(f"Error revoking refresh token: {e}")
            return False
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Получает пользователя по имени
        
        Args:
            username: Имя пользователя
            
        Returns:
            Пользователь если найден, иначе None
        """
        if not self._initialized:
            await self.initialize()
        
        user_entity = await self._user_repository.find_by_username(username)
        if user_entity:
            return User.from_entity(user_entity)
        return None
    
    async def get_all_users(self, limit: int = 100, offset: int = 0) -> List[User]:
        """
        Получает всех пользователей
        
        Returns:
            Список всех пользователей
        """
        if not self._initialized:
            await self.initialize()
        
        user_entities = await self._user_repository.find_all(limit, offset)
        return [User.from_entity(entity) for entity in user_entities]
    
    async def update_user_role(self, username: str, new_role: UserRole) -> bool:
        """
        Обновляет роль пользователя
        
        Args:
            username: Имя пользователя
            new_role: Новая роль
            
        Returns:
            True если роль обновлена, иначе False
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            user_entity = await self._user_repository.find_by_username(username)
            if not user_entity:
                self.logger.warning(f"Role update failed: user '{username}' not found")
                return False
            
            old_role = user_entity.role
            user_entity.role = new_role.value
            
            await self._user_repository.update(user_entity)
            
            self.logger.info(f"Role updated for user '{username}': {old_role} -> {new_role.value}")
            return True
                
        except Exception as e:
            self.logger.error(f"Error updating role for user '{username}': {e}")
            return False
    
    async def deactivate_user(self, username: str) -> bool:
        """
        Деактивирует пользователя
        
        Args:
            username: Имя пользователя
            
        Returns:
            True если пользователь деактивирован, иначе False
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            user_entity = await self._user_repository.find_by_username(username)
            if not user_entity:
                self.logger.warning(f"User deactivation failed: user '{username}' not found")
                return False
            
            # Деактивируем пользователя
            await self._user_repository.deactivate(user_entity.id)
            
            # Отзываем все refresh токены пользователя
            await self._revoke_all_user_tokens(user_entity.id)
            
            self.logger.info(f"User '{username}' deactivated and all tokens revoked")
            return True
                
        except Exception as e:
            self.logger.error(f"Error deactivating user '{username}': {e}")
            return False
    
    # Вспомогательные методы для работы с токенами
    
    async def _save_refresh_token(self, user_id: str, token_id: str, expires_at: datetime):
        """Сохраняет refresh token в базу"""
        query = """
        INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at)
        VALUES ($1, $2, $3, $4)
        """
        
        # Хешируем token_id для безопасности
        token_hash = bcrypt.hashpw(token_id.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        await self._db_service.execute(
            query,
            token_id,
            user_id,
            token_hash,
            expires_at
        )
    
    async def _verify_refresh_token(self, token_id: str) -> bool:
        """Проверяет существование refresh token"""
        query = """
        SELECT EXISTS(
            SELECT 1 FROM refresh_tokens 
            WHERE id = $1 AND expires_at > CURRENT_TIMESTAMP
        )
        """
        
        exists = await self._db_service.fetchval(query, token_id)
        return exists or False
    
    async def _revoke_refresh_token(self, token_id: str) -> bool:
        """Отзывает конкретный refresh token"""
        query = "DELETE FROM refresh_tokens WHERE id = $1"
        result = await self._db_service.execute(query, token_id)
        return "DELETE 1" in result
    
    async def _revoke_all_user_tokens(self, user_id: str):
        """Отзывает все refresh токены пользователя"""
        query = "DELETE FROM refresh_tokens WHERE user_id = $1"
        await self._db_service.execute(query, user_id)
    
    # Вспомогательные методы
    
    def _hash_password(self, password: str) -> str:
        """Хеширует пароль"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def _verify_password(self, password: str, hashed: str) -> bool:
        """Проверяет пароль против хеша"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    def _validate_password(self, password: str):
        """Валидирует пароль"""
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in password):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in password):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one digit")
    
    async def _create_default_admin(self):
        """Создает администратора по умолчанию"""
        try:
            admin_username = "admin"
            admin_password = os.getenv("ADMIN_PASSWORD", "Admin123!")
            
            # Проверяем существование админа
            existing_admin = await self._user_repository.find_by_username(admin_username)
            if not existing_admin:
                await self.register_user(
                    username=admin_username,
                    email="admin@meeting-protocol.local",
                    password=admin_password,
                    role=UserRole.ADMIN
                )
                self.logger.info("Default admin user created")
            
        except Exception as e:
            self.logger.error(f"Error creating default admin: {e}")
    
    # Методы для очистки истекших токенов
    
    async def cleanup_expired_tokens(self):
        """Удаляет истекшие refresh токены из базы"""
        query = "DELETE FROM refresh_tokens WHERE expires_at < CURRENT_TIMESTAMP"
        result = await self._db_service.execute(query)
        
        # Извлекаем количество удаленных записей
        count = int(result.split()[1]) if "DELETE" in result else 0
        if count > 0:
            self.logger.info(f"Cleaned up {count} expired refresh tokens")
    
    # Статистика
    
    async def get_auth_statistics(self) -> Dict[str, Any]:
        """Получает статистику аутентификации"""
        if not self._initialized:
            await self.initialize()
        
        total_users = await self._user_repository.count_users()
        active_users = await self._user_repository.count_active_users()
        
        # Подсчитываем активные токены
        active_tokens_query = """
        SELECT COUNT(*) FROM refresh_tokens 
        WHERE expires_at > CURRENT_TIMESTAMP
        """
        active_tokens = await self._db_service.fetchval(active_tokens_query) or 0
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users,
            "active_refresh_tokens": active_tokens
        }

# Глобальный экземпляр для использования в приложении
_auth_service: Optional[AuthenticationService] = None

async def get_auth_service() -> AuthenticationService:
    """Dependency для получения сервиса аутентификации"""
    global _auth_service
    
    if _auth_service is None:
        _auth_service = AuthenticationService()
        await _auth_service.initialize()
    
    return _auth_service

async def close_auth_service():
    """Закрывает сервис аутентификации при завершении приложения"""
    global _auth_service
    
    if _auth_service is not None:
        # Очищаем истекшие токены перед закрытием
        await _auth_service.cleanup_expired_tokens()
        _auth_service = None
