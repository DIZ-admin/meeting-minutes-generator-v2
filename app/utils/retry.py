"""
Утилиты для retry логики с exponential backoff
"""
import asyncio
import time
import random
from typing import Callable, TypeVar, Optional, Union, Type, Tuple
from functools import wraps

from ..core.exceptions import AppBaseError, APIError
from ..utils.logging import get_default_logger

logger = get_default_logger(__name__)

T = TypeVar('T')

class RetryConfig:
    """Конфигурация для retry механизма"""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Tuple[Type[Exception], ...] = (APIError, ConnectionError, TimeoutError)
    ):
        """
        Args:
            max_attempts: Максимальное количество попыток
            base_delay: Базовая задержка в секундах
            max_delay: Максимальная задержка в секундах
            exponential_base: База для экспоненциального роста
            jitter: Добавлять ли случайность к задержке
            retryable_exceptions: Исключения, для которых нужно делать retry
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions
    
    def calculate_delay(self, attempt: int) -> float:
        """Вычисляет задержку для указанной попытки"""
        # Экспоненциальная задержка
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        
        # Ограничиваем максимальной задержкой
        delay = min(delay, self.max_delay)
        
        # Добавляем jitter для избежания thundering herd
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        
        return delay
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Определяет, нужно ли делать retry для данного исключения"""
        if attempt >= self.max_attempts:
            return False
        
        return isinstance(exception, self.retryable_exceptions)

def retry_sync(config: Optional[RetryConfig] = None):
    """
    Декоратор для синхронного retry с exponential backoff
    
    Args:
        config: Конфигурация retry. Если None, используется по умолчанию
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            attempt = 1
            last_exception: Optional[Exception] = None
            
            while attempt <= config.max_attempts:
                try:
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        logger.info(f"Function {func.__name__} succeeded on attempt {attempt}")
                    return result
                    
                except Exception as e:
                    last_exception = e
                    
                    if config.should_retry(e, attempt):
                        delay = config.calculate_delay(attempt)
                        logger.warning(
                            f"Function {func.__name__} failed on attempt {attempt}/{config.max_attempts}. "
                            f"Retrying in {delay:.2f}s. Error: {e}"
                        )
                        time.sleep(delay)
                        attempt += 1
                    else:
                        logger.error(f"Function {func.__name__} failed permanently: {e}")
                        raise
            
            # Если все попытки исчерпаны
            logger.error(
                f"Function {func.__name__} failed after {config.max_attempts} attempts. Last error: {last_exception}"
            )
            raise last_exception
        
        return wrapper
    return decorator

def retry_async(config: Optional[RetryConfig] = None):
    """
    Декоратор для асинхронного retry с exponential backoff
    
    Args:
        config: Конфигурация retry. Если None, используется по умолчанию
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            attempt = 1
            last_exception: Optional[Exception] = None
            
            while attempt <= config.max_attempts:
                try:
                    result = await func(*args, **kwargs)
                    if attempt > 1:
                        logger.info(f"Async function {func.__name__} succeeded on attempt {attempt}")
                    return result
                    
                except Exception as e:
                    last_exception = e
                    
                    if config.should_retry(e, attempt):
                        delay = config.calculate_delay(attempt)
                        logger.warning(
                            f"Async function {func.__name__} failed on attempt {attempt}/{config.max_attempts}. "
                            f"Retrying in {delay:.2f}s. Error: {e}"
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                    else:
                        logger.error(f"Async function {func.__name__} failed permanently: {e}")
                        raise
            
            # Если все попытки исчерпаны
            logger.error(
                f"Async function {func.__name__} failed after {config.max_attempts} attempts. Last error: {last_exception}"
            )
            raise last_exception
        
        return wrapper
    return decorator

# Предустановленные конфигурации для разных сценариев
class RetryPresets:
    """Предустановленные конфигурации retry для различных сценариев"""
    
    # Для API запросов
    API_CALLS = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=(APIError, ConnectionError, TimeoutError)
    )
    
    # Для критических операций
    CRITICAL = RetryConfig(
        max_attempts=5,
        base_delay=0.5,
        max_delay=60.0,
        exponential_base=1.5,
        jitter=True,
        retryable_exceptions=(APIError, ConnectionError, TimeoutError, OSError)
    )
    
    # Для быстрых операций
    FAST = RetryConfig(
        max_attempts=2,
        base_delay=0.1,
        max_delay=1.0,
        exponential_base=2.0,
        jitter=False,
        retryable_exceptions=(ConnectionError, TimeoutError)
    )
    
    # Для файловых операций
    FILE_OPS = RetryConfig(
        max_attempts=3,
        base_delay=0.5,
        max_delay=10.0,
        exponential_base=1.8,
        jitter=True,
        retryable_exceptions=(OSError, PermissionError, FileNotFoundError)
    )

# Удобные функции для direct использования
async def retry_async_call(
    func: Callable[..., T], 
    *args, 
    config: Optional[RetryConfig] = None,
    **kwargs
) -> T:
    """
    Выполняет асинхронную функцию с retry логикой
    
    Args:
        func: Асинхронная функция для выполнения
        *args: Аргументы для функции
        config: Конфигурация retry
        **kwargs: Ключевые аргументы для функции
    
    Returns:
        Результат выполнения функции
    """
    if config is None:
        config = RetryConfig()
    
    @retry_async(config)
    async def _wrapper():
        return await func(*args, **kwargs)
    
    return await _wrapper()

def retry_sync_call(
    func: Callable[..., T], 
    *args, 
    config: Optional[RetryConfig] = None,
    **kwargs
) -> T:
    """
    Выполняет синхронную функцию с retry логикой
    
    Args:
        func: Синхронная функция для выполнения
        *args: Аргументы для функции
        config: Конфигурация retry
        **kwargs: Ключевые аргументы для функции
    
    Returns:
        Результат выполнения функции
    """
    if config is None:
        config = RetryConfig()
    
    @retry_sync(config)
    def _wrapper():
        return func(*args, **kwargs)
    
    return _wrapper()
