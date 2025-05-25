"""
Database Service для управления подключениями и операциями с PostgreSQL
"""
import os
from typing import Optional, Dict, Any, List, Type, TypeVar, Generic
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
import json

from sqlalchemy import create_engine, MetaData, Table, Column, String, Boolean, DateTime, JSON, select, and_, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import NullPool

from pydantic import BaseModel

from ..utils.logging import get_default_logger
from ..core.exceptions import DatabaseError, ConfigError

logger = get_default_logger(__name__)

# Type variable для generic repository
T = TypeVar('T', bound=BaseModel)

# Base для ORM моделей
Base = declarative_base()

class DatabaseConfig(BaseModel):
    """Конфигурация для подключения к базе данных"""
    host: str = "localhost"
    port: int = 5432
    database: str = "meeting_protocol"
    user: str = "postgres"
    password: str = ""
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False
    
    @property
    def sync_url(self) -> str:
        """Возвращает URL для синхронного подключения"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    @property
    def async_url(self) -> str:
        """Возвращает URL для асинхронного подключения"""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

class DatabaseService:
    """
    Сервис для управления подключениями к PostgreSQL и выполнения операций
    
    Предоставляет:
    - Управление подключениями (синхронные и асинхронные)
    - Миграции базы данных
    - Репозиторий паттерн для работы с данными
    - Управление транзакциями
    """
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        Инициализация Database Service
        
        Args:
            config: Конфигурация подключения к БД
        """
        self.config = config or self._load_config_from_env()
        
        # Движки для синхронных и асинхронных операций
        self._sync_engine: Optional[Any] = None
        self._async_engine: Optional[AsyncEngine] = None
        
        # Фабрики сессий
        self._sync_session_factory: Optional[sessionmaker] = None
        self._async_session_factory: Optional[sessionmaker] = None
        
        # Метаданные для работы с таблицами
        self.metadata = MetaData()
        
        logger.info("DatabaseService initialized")
    
    def _load_config_from_env(self) -> DatabaseConfig:
        """Загружает конфигурацию из переменных окружения"""
        return DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "meeting_protocol"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
            pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
            echo=os.getenv("DB_ECHO", "false").lower() == "true"
        )

    
    # Управление синхронными подключениями
    @property
    def sync_engine(self):
        """Возвращает синхронный движок SQLAlchemy"""
        if self._sync_engine is None:
            self._sync_engine = create_engine(
                self.config.sync_url,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                echo=self.config.echo
            )
            self._sync_session_factory = sessionmaker(
                bind=self._sync_engine,
                expire_on_commit=False
            )
        return self._sync_engine
    
    @contextmanager
    def get_sync_session(self) -> Session:
        """
        Контекстный менеджер для синхронной сессии
        
        Yields:
            SQLAlchemy Session
        """
        if self._sync_session_factory is None:
            _ = self.sync_engine  # Инициализируем движок
            
        session = self._sync_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    # Управление асинхронными подключениями
    @property
    async def async_engine(self) -> AsyncEngine:
        """Возвращает асинхронный движок SQLAlchemy"""
        if self._async_engine is None:
            self._async_engine = create_async_engine(
                self.config.async_url,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                echo=self.config.echo
            )
            self._async_session_factory = sessionmaker(
                bind=self._async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
        return self._async_engine

    
    @asynccontextmanager
    async def get_async_session(self) -> AsyncSession:
        """
        Асинхронный контекстный менеджер для сессии
        
        Yields:
            SQLAlchemy AsyncSession
        """
        if self._async_session_factory is None:
            _ = await self.async_engine  # Инициализируем движок
            
        async with self._async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    # Методы для миграций
    def create_tables(self) -> None:
        """Создает все таблицы в базе данных"""
        try:
            Base.metadata.create_all(bind=self.sync_engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            raise DatabaseError(
                message="Failed to create database tables",
                details={"error": str(e)}
            )
    
    async def create_tables_async(self) -> None:
        """Асинхронно создает все таблицы в базе данных"""
        try:
            engine = await self.async_engine
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully (async)")
        except Exception as e:
            raise DatabaseError(
                message="Failed to create database tables",
                details={"error": str(e)}
            )
    
    def drop_tables(self) -> None:
        """Удаляет все таблицы из базы данных"""
        try:
            Base.metadata.drop_all(bind=self.sync_engine)
            logger.info("Database tables dropped successfully")
        except Exception as e:
            raise DatabaseError(
                message="Failed to drop database tables",
                details={"error": str(e)}
            )

    
    # Health check методы
    def check_connection(self) -> bool:
        """
        Проверяет подключение к базе данных
        
        Returns:
            True, если подключение успешно
        """
        try:
            with self.get_sync_session() as session:
                session.execute(select(1))
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False
    
    async def check_connection_async(self) -> bool:
        """
        Асинхронно проверяет подключение к базе данных
        
        Returns:
            True, если подключение успешно
        """
        try:
            async with self.get_async_session() as session:
                await session.execute(select(1))
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False
    
    def get_table_stats(self) -> Dict[str, int]:
        """
        Получает статистику по таблицам
        
        Returns:
            Словарь с количеством записей в каждой таблице
        """
        stats = {}
        try:
            with self.get_sync_session() as session:
                for table in Base.metadata.tables.values():
                    count = session.query(table).count()
                    stats[table.name] = count
        except Exception as e:
            logger.error(f"Failed to get table stats: {e}")
        
        return stats

    
    def close(self) -> None:
        """Закрывает все подключения"""
        if self._sync_engine:
            self._sync_engine.dispose()
            self._sync_engine = None
            self._sync_session_factory = None
            logger.info("Sync database connections closed")
    
    async def close_async(self) -> None:
        """Асинхронно закрывает все подключения"""
        if self._async_engine:
            await self._async_engine.dispose()
            self._async_engine = None
            self._async_session_factory = None
            logger.info("Async database connections closed")

class BaseRepository(Generic[T]):
    """
    Базовый репозиторий для работы с данными
    
    Предоставляет общие CRUD операции для всех моделей
    """
    
    def __init__(self, model_class: Type[T], db_service: DatabaseService):
        """
        Инициализация репозитория
        
        Args:
            model_class: Класс модели Pydantic
            db_service: Сервис базы данных
        """
        self.model_class = model_class
        self.db_service = db_service
        self.table_name = model_class.__name__.lower() + "s"
    
    async def create(self, data: T) -> T:
        """
        Создает новую запись
        
        Args:
            data: Данные для создания
            
        Returns:
            Созданная запись
        """
        async with self.db_service.get_async_session() as session:
            # Здесь будет логика создания записи
            # Пока возвращаем входные данные
            return data

    
    async def get_by_id(self, id: str) -> Optional[T]:
        """
        Получает запись по ID
        
        Args:
            id: ID записи
            
        Returns:
            Найденная запись или None
        """
        async with self.db_service.get_async_session() as session:
            # Здесь будет логика получения записи
            return None
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """
        Получает все записи с пагинацией
        
        Args:
            limit: Максимальное количество записей
            offset: Смещение
            
        Returns:
            Список записей
        """
        async with self.db_service.get_async_session() as session:
            # Здесь будет логика получения записей
            return []
    
    async def update(self, id: str, data: Dict[str, Any]) -> Optional[T]:
        """
        Обновляет запись
        
        Args:
            id: ID записи
            data: Данные для обновления
            
        Returns:
            Обновленная запись или None
        """
        async with self.db_service.get_async_session() as session:
            # Здесь будет логика обновления записи
            return None
    
    async def delete(self, id: str) -> bool:
        """
        Удаляет запись
        
        Args:
            id: ID записи
            
        Returns:
            True, если запись удалена
        """
        async with self.db_service.get_async_session() as session:
            # Здесь будет логика удаления записи
            return False
