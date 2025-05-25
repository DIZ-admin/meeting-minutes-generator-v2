#!/usr/bin/env python3
"""
Repository implementations для работы с базой данных
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncpg
from dataclasses import dataclass, field

from app.services.database_service import Repository, BaseEntity, DatabaseService
from app.services.auth_service import User, UserRole
from app.utils.logging import get_default_logger

logger = get_default_logger(__name__)

@dataclass
class UserEntity(BaseEntity):
    """Сущность пользователя для базы данных"""
    id: str
    username: str
    email: str
    password_hash: str
    role: str
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    
    @property
    def table_name(self) -> str:
        return "users"
    
    @property
    def primary_key(self) -> str:
        return "id"

class UserRepository(Repository[UserEntity]):
    """Репозиторий для работы с пользователями"""
    
    def __init__(self, db_service: DatabaseService):
        super().__init__(db_service, UserEntity)
    
    async def create_table(self):
        """Создаёт таблицу пользователей"""
        query = """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(255) PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(50) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
        """
        await self.db_service.execute(query)
        self.logger.info("Users table created")
    
    async def find_by_id(self, user_id: str) -> Optional[UserEntity]:
        """Найти пользователя по ID"""
        query = """
        SELECT id, username, email, password_hash, role, is_active, 
               created_at, updated_at, last_login
        FROM users 
        WHERE id = $1
        """
        row = await self.db_service.fetchrow(query, user_id)
        
        if row:
            return UserEntity(**dict(row))
        return None
    
    async def find_by_username(self, username: str) -> Optional[UserEntity]:
        """Найти пользователя по username"""
        query = """
        SELECT id, username, email, password_hash, role, is_active, 
               created_at, updated_at, last_login
        FROM users 
        WHERE username = $1
        """
        row = await self.db_service.fetchrow(query, username)
        
        if row:
            return UserEntity(**dict(row))
        return None
    
    async def find_by_email(self, email: str) -> Optional[UserEntity]:
        """Найти пользователя по email"""
        query = """
        SELECT id, username, email, password_hash, role, is_active, 
               created_at, updated_at, last_login
        FROM users 
        WHERE email = $1
        """
        row = await self.db_service.fetchrow(query, email)
        
        if row:
            return UserEntity(**dict(row))
        return None
    
    async def find_all(self, limit: int = 100, offset: int = 0) -> List[UserEntity]:
        """Найти всех пользователей с пагинацией"""
        query = """
        SELECT id, username, email, password_hash, role, is_active, 
               created_at, updated_at, last_login
        FROM users 
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """
        rows = await self.db_service.fetch(query, limit, offset)
        
        return [UserEntity(**dict(row)) for row in rows]
    
    async def find_active_users(self, limit: int = 100, offset: int = 0) -> List[UserEntity]:
        """Найти активных пользователей"""
        query = """
        SELECT id, username, email, password_hash, role, is_active, 
               created_at, updated_at, last_login
        FROM users 
        WHERE is_active = TRUE
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """
        rows = await self.db_service.fetch(query, limit, offset)
        
        return [UserEntity(**dict(row)) for row in rows]
    
    async def create(self, entity: UserEntity) -> UserEntity:
        """Создать нового пользователя"""
        query = """
        INSERT INTO users (id, username, email, password_hash, role, is_active, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING *
        """
        
        row = await self.db_service.fetchrow(
            query,
            entity.id,
            entity.username,
            entity.email,
            entity.password_hash,
            entity.role,
            entity.is_active,
            entity.created_at,
            entity.updated_at
        )
        
        if row:
            created_entity = UserEntity(**dict(row))
            self.logger.info(f"User created: {created_entity.username}")
            return created_entity
        
        raise Exception("Failed to create user")
    
    async def update(self, entity: UserEntity) -> UserEntity:
        """Обновить существующего пользователя"""
        entity.updated_at = datetime.now()
        
        query = """
        UPDATE users 
        SET username = $2, email = $3, password_hash = $4, role = $5, 
            is_active = $6, updated_at = $7, last_login = $8
        WHERE id = $1
        RETURNING *
        """
        
        row = await self.db_service.fetchrow(
            query,
            entity.id,
            entity.username,
            entity.email,
            entity.password_hash,
            entity.role,
            entity.is_active,
            entity.updated_at,
            entity.last_login
        )
        
        if row:
            updated_entity = UserEntity(**dict(row))
            self.logger.info(f"User updated: {updated_entity.username}")
            return updated_entity
        
        raise Exception(f"User with id {entity.id} not found")
    
    async def update_last_login(self, user_id: str) -> bool:
        """Обновить время последнего входа"""
        query = """
        UPDATE users 
        SET last_login = $2, updated_at = $3
        WHERE id = $1
        """
        
        result = await self.db_service.execute(
            query,
            user_id,
            datetime.now(),
            datetime.now()
        )
        
        return "UPDATE 1" in result
    
    async def delete(self, user_id: str) -> bool:
        """Удалить пользователя по ID"""
        query = "DELETE FROM users WHERE id = $1"
        result = await self.db_service.execute(query, user_id)
        
        deleted = "DELETE 1" in result
        if deleted:
            self.logger.info(f"User deleted: {user_id}")
        
        return deleted
    
    async def deactivate(self, user_id: str) -> bool:
        """Деактивировать пользователя"""
        query = """
        UPDATE users 
        SET is_active = FALSE, updated_at = $2
        WHERE id = $1
        """
        
        result = await self.db_service.execute(
            query,
            user_id,
            datetime.now()
        )
        
        deactivated = "UPDATE 1" in result
        if deactivated:
            self.logger.info(f"User deactivated: {user_id}")
        
        return deactivated
    
    async def count_users(self) -> int:
        """Подсчитать общее количество пользователей"""
        query = "SELECT COUNT(*) FROM users"
        count = await self.db_service.fetchval(query)
        return count or 0
    
    async def count_active_users(self) -> int:
        """Подсчитать количество активных пользователей"""
        query = "SELECT COUNT(*) FROM users WHERE is_active = TRUE"
        count = await self.db_service.fetchval(query)
        return count or 0
    
    async def search_users(self, search_term: str, limit: int = 50) -> List[UserEntity]:
        """Поиск пользователей по username или email"""
        query = """
        SELECT id, username, email, password_hash, role, is_active, 
               created_at, updated_at, last_login
        FROM users 
        WHERE username ILIKE $1 OR email ILIKE $1
        ORDER BY created_at DESC
        LIMIT $2
        """
        
        search_pattern = f"%{search_term}%"
        rows = await self.db_service.fetch(query, search_pattern, limit)
        
        return [UserEntity(**dict(row)) for row in rows]
