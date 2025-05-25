"""
Адаптер для Redis кеширования
"""
import os
import json
import hashlib
import time
from typing import Any, Optional, Dict, Union
from pathlib import Path
import pickle
import gzip

try:
    import redis
    from redis import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None

from ..core.exceptions import ConfigError
from ..utils.logging import get_default_logger
from ..config.config import config

logger = get_default_logger(__name__)

class CacheAdapter:
    """
    Универсальный адаптер для кеширования с поддержкой Redis и fallback на файловый кеш
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        default_ttl: int = 3600,
        fallback_to_file: bool = True,
        file_cache_dir: Optional[Path] = None
    ):
        """
        Инициализация кеш адаптера
        
        Args:
            redis_url: URL для подключения к Redis
            redis_host: Хост Redis сервера
            redis_port: Порт Redis сервера
            redis_db: Номер базы данных Redis
            redis_password: Пароль для Redis
            default_ttl: TTL по умолчанию в секундах
            fallback_to_file: Использовать файловый кеш если Redis недоступен
            file_cache_dir: Директория для файлового кеша
        """
        self.default_ttl = default_ttl
        self.fallback_to_file = fallback_to_file
        self.file_cache_dir = file_cache_dir or (config.base_dir / "cache")
        self.redis_client: Optional[Redis] = None
        self._redis_available = False
        
        # Создаем директорию для файлового кеша
        if self.fallback_to_file:
            self.file_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Пытаемся подключиться к Redis
        if REDIS_AVAILABLE:
            try:
                if redis_url:
                    self.redis_client = redis.from_url(redis_url)
                else:
                    self.redis_client = Redis(
                        host=redis_host,
                        port=redis_port,
                        db=redis_db,
                        password=redis_password,
                        decode_responses=False,  # Для binary данных
                        socket_timeout=5,
                        socket_connect_timeout=5
                    )
                
                # Проверяем подключение
                self.redis_client.ping()
                self._redis_available = True
                logger.info(f"Redis cache connected: {redis_host}:{redis_port}/{redis_db}")
                
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
                if not self.fallback_to_file:
                    raise ConfigError(f"Redis connection failed and fallback disabled: {e}")
                else:
                    logger.info("Falling back to file-based cache")
        else:
            logger.warning("Redis not available, using file-based cache only")
    
    def _make_key(self, namespace: str, key: str) -> str:
        """Создает ключ для кеша с namespace"""
        return f"meeting_protocol:{namespace}:{key}"
    
    def _make_file_path(self, namespace: str, key: str) -> Path:
        """Создает путь к файлу для файлового кеша"""
        # Хешируем ключ для безопасного имени файла
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.file_cache_dir / namespace / f"{key_hash}.cache"
    
    def _serialize_data(self, data: Any) -> bytes:
        """Сериализует данные для хранения"""
        # Используем pickle с gzip сжатием для эффективности
        pickled = pickle.dumps(data)
        return gzip.compress(pickled)
    
    def _deserialize_data(self, data: bytes) -> Any:
        """Десериализует данные из кеша"""
        decompressed = gzip.decompress(data)
        return pickle.loads(decompressed)
    
    def get(self, namespace: str, key: str) -> Optional[Any]:
        """
        Получает данные из кеша
        
        Args:
            namespace: Пространство имен (например, 'asr', 'llm')
            key: Ключ для поиска
            
        Returns:
            Данные из кеша или None если не найдено
        """
        cache_key = self._make_key(namespace, key)
        
        # Пытаемся получить из Redis
        if self._redis_available and self.redis_client:
            try:
                data = self.redis_client.get(cache_key)
                if data:
                    result = self._deserialize_data(data)
                    logger.debug(f"Cache hit (Redis): {namespace}/{key[:20]}...")
                    return result
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
                self._redis_available = False
        
        # Fallback на файловый кеш
        if self.fallback_to_file:
            try:
                file_path = self._make_file_path(namespace, key)
                if file_path.exists():
                    # Проверяем TTL
                    file_stat = file_path.stat()
                    age = time.time() - file_stat.st_mtime
                    if age < self.default_ttl:
                        data = file_path.read_bytes()
                        result = self._deserialize_data(data)
                        logger.debug(f"Cache hit (file): {namespace}/{key[:20]}...")
                        return result
                    else:
                        # Файл устарел, удаляем
                        file_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"File cache get error: {e}")
        
        logger.debug(f"Cache miss: {namespace}/{key[:20]}...")
        return None
    
    def set(
        self, 
        namespace: str, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """
        Сохраняет данные в кеш
        
        Args:
            namespace: Пространство имен
            key: Ключ для сохранения
            value: Данные для сохранения
            ttl: TTL в секундах (если None, используется default_ttl)
            
        Returns:
            True если успешно сохранено
        """
        cache_key = self._make_key(namespace, key)
        ttl = ttl or self.default_ttl
        
        try:
            serialized_data = self._serialize_data(value)
        except Exception as e:
            logger.error(f"Failed to serialize data for cache: {e}")
            return False
        
        success = False
        
        # Пытаемся сохранить в Redis
        if self._redis_available and self.redis_client:
            try:
                self.redis_client.setex(cache_key, ttl, serialized_data)
                success = True
                logger.debug(f"Cache set (Redis): {namespace}/{key[:20]}...")
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
                self._redis_available = False
        
        # Fallback на файловый кеш
        if self.fallback_to_file:
            try:
                file_path = self._make_file_path(namespace, key)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(serialized_data)
                success = True
                logger.debug(f"Cache set (file): {namespace}/{key[:20]}...")
            except Exception as e:
                logger.warning(f"File cache set error: {e}")
        
        return success
    
    def delete(self, namespace: str, key: str) -> bool:
        """
        Удаляет данные из кеша
        
        Args:
            namespace: Пространство имен
            key: Ключ для удаления
            
        Returns:
            True если успешно удалено
        """
        cache_key = self._make_key(namespace, key)
        success = False
        
        # Удаляем из Redis
        if self._redis_available and self.redis_client:
            try:
                deleted = self.redis_client.delete(cache_key)
                success = deleted > 0
                logger.debug(f"Cache delete (Redis): {namespace}/{key[:20]}...")
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")
        
        # Удаляем из файлового кеша
        if self.fallback_to_file:
            try:
                file_path = self._make_file_path(namespace, key)
                if file_path.exists():
                    file_path.unlink()
                    success = True
                    logger.debug(f"Cache delete (file): {namespace}/{key[:20]}...")
            except Exception as e:
                logger.warning(f"File cache delete error: {e}")
        
        return success
    
    def clear_namespace(self, namespace: str) -> bool:
        """
        Очищает все данные в указанном namespace
        
        Args:
            namespace: Пространство имен для очистки
            
        Returns:
            True если успешно очищено
        """
        success = False
        
        # Очищаем Redis namespace
        if self._redis_available and self.redis_client:
            try:
                pattern = self._make_key(namespace, "*")
                keys = self.redis_client.keys(pattern)
                if keys:
                    deleted = self.redis_client.delete(*keys)
                    logger.info(f"Cleared {deleted} keys from Redis namespace: {namespace}")
                    success = True
            except Exception as e:
                logger.warning(f"Redis clear namespace error: {e}")
        
        # Очищаем файловый кеш namespace
        if self.fallback_to_file:
            try:
                namespace_dir = self.file_cache_dir / namespace
                if namespace_dir.exists():
                    import shutil
                    shutil.rmtree(namespace_dir)
                    logger.info(f"Cleared file cache namespace: {namespace}")
                    success = True
            except Exception as e:
                logger.warning(f"File cache clear namespace error: {e}")
        
        return success
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику кеша
        
        Returns:
            Словарь со статистикой
        """
        stats = {
            "redis_available": self._redis_available,
            "fallback_enabled": self.fallback_to_file,
            "file_cache_dir": str(self.file_cache_dir),
            "default_ttl": self.default_ttl
        }
        
        # Статистика Redis
        if self._redis_available and self.redis_client:
            try:
                redis_info = self.redis_client.info()
                stats["redis_info"] = {
                    "used_memory": redis_info.get("used_memory_human"),
                    "connected_clients": redis_info.get("connected_clients"),
                    "total_commands_processed": redis_info.get("total_commands_processed")
                }
            except Exception as e:
                logger.warning(f"Failed to get Redis stats: {e}")
        
        # Статистика файлового кеша
        if self.fallback_to_file and self.file_cache_dir.exists():
            try:
                cache_files = list(self.file_cache_dir.rglob("*.cache"))
                total_size = sum(f.stat().st_size for f in cache_files if f.exists())
                stats["file_cache_info"] = {
                    "total_files": len(cache_files),
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2)
                }
            except Exception as e:
                logger.warning(f"Failed to get file cache stats: {e}")
        
        return stats
    
    def is_healthy(self) -> bool:
        """
        Проверяет здоровье кеш системы
        
        Returns:
            True если кеш работает
        """
        # Тестируем Redis
        if self._redis_available and self.redis_client:
            try:
                self.redis_client.ping()
                return True
            except Exception:
                self._redis_available = False
        
        # Тестируем файловый кеш
        if self.fallback_to_file:
            try:
                test_file = self.file_cache_dir / "health_check.tmp"
                test_file.write_text("test")
                test_file.unlink()
                return True
            except Exception:
                return False
        
        return False

# Глобальный экземпляр кеша
_cache_instance: Optional[CacheAdapter] = None

def get_cache() -> CacheAdapter:
    """
    Возвращает глобальный экземпляр кеша
    
    Returns:
        Экземпляр CacheAdapter
    """
    global _cache_instance
    
    if _cache_instance is None:
        # Настройки из переменных окружения
        redis_url = os.getenv("REDIS_URL")
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD")
        
        _cache_instance = CacheAdapter(
            redis_url=redis_url,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            redis_password=redis_password,
            default_ttl=int(os.getenv("CACHE_TTL", "3600")),
            fallback_to_file=True
        )
    
    return _cache_instance

# Convenience функции для часто используемых операций
def cache_asr_result(audio_file_hash: str, result: Any, ttl: int = 86400) -> bool:
    """Кеширует результат ASR (TTL 24 часа по умолчанию)"""
    return get_cache().set("asr", audio_file_hash, result, ttl)

def get_cached_asr_result(audio_file_hash: str) -> Optional[Any]:
    """Получает закешированный результат ASR"""
    return get_cache().get("asr", audio_file_hash)

def cache_llm_response(prompt_hash: str, response: Any, ttl: int = 3600) -> bool:
    """Кеширует ответ LLM (TTL 1 час по умолчанию)"""
    return get_cache().set("llm", prompt_hash, response, ttl)

def get_cached_llm_response(prompt_hash: str) -> Optional[Any]:
    """Получает закешированный ответ LLM"""
    return get_cache().get("llm", prompt_hash)

def generate_content_hash(content: Union[str, bytes, Path]) -> str:
    """
    Генерирует хеш для контента (для использования как ключ кеша)
    
    Args:
        content: Строка, байты или путь к файлу
        
    Returns:
        SHA256 хеш в hex формате
    """
    hasher = hashlib.sha256()
    
    if isinstance(content, Path):
        # Для файлов используем содержимое + размер + время модификации
        if content.exists():
            hasher.update(content.read_bytes())
            stat = content.stat()
            hasher.update(str(stat.st_size).encode())
            hasher.update(str(stat.st_mtime).encode())
        else:
            hasher.update(str(content).encode())
    elif isinstance(content, str):
        hasher.update(content.encode())
    elif isinstance(content, bytes):
        hasher.update(content)
    else:
        # Для других объектов используем их строковое представление
        hasher.update(str(content).encode())
    
    return hasher.hexdigest()
