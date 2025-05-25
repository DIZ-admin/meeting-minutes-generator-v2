#!/usr/bin/env python3
"""
Database initialization script
"""
import asyncio
import sys
from app.services.database_service import get_database_service, close_database_service
from app.services.auth_service_enhanced import get_auth_service, close_auth_service
from app.migrations.migrate import run_migrations
from app.utils.logging import get_default_logger

logger = get_default_logger(__name__)

async def init_database():
    """Инициализирует базу данных и запускает миграции"""
    try:
        logger.info("Starting database initialization...")
        
        # Инициализируем database service
        db_service = await get_database_service()
        logger.info("Database service initialized")
        
        # Запускаем миграции
        logger.info("Running database migrations...")
        await run_migrations()
        
        # Инициализируем auth service (создаст админа по умолчанию)
        logger.info("Initializing authentication service...")
        auth_service = await get_auth_service()
        
        # Проверяем статистику
        stats = await auth_service.get_auth_statistics()
        logger.info(f"Database initialized successfully. Statistics: {stats}")
        
        # Закрываем сервисы
        await close_auth_service()
        await close_database_service()
        
        logger.info("Database initialization completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(init_database())
    sys.exit(0 if success else 1)
