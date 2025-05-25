"""
Prometheus метрики для мониторинга приложения
"""
import time
from typing import Dict, Any, Optional, Callable
from functools import wraps
from threading import Lock

try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Summary, 
        CollectorRegistry, generate_latest, 
        CONTENT_TYPE_LATEST, REGISTRY
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Counter = Histogram = Gauge = Summary = None
    CollectorRegistry = None
    generate_latest = None
    CONTENT_TYPE_LATEST = 'text/plain'
    REGISTRY = None

from ..utils.logging import get_default_logger

logger = get_default_logger(__name__)

class MetricsCollector:
    """Коллектор метрик для мониторинга системы"""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or REGISTRY
        self._metrics: Dict[str, Any] = {}
        self._enabled = PROMETHEUS_AVAILABLE
        
        if not self._enabled:
            logger.warning("Prometheus client not available, metrics disabled")
            return
        
        self._initialize_metrics()
        logger.info("Metrics collector initialized")
    
    def _initialize_metrics(self):
        """Инициализирует стандартные метрики"""
        if not self._enabled:
            return
        
        # Основные бизнес-метрики
        self._metrics['processed_files_total'] = Counter(
            'meeting_processed_files_total',
            'Total number of processed audio files',
            ['status', 'language', 'file_type'],
            registry=self.registry
        )
        
        self._metrics['processing_duration'] = Histogram(
            'meeting_processing_duration_seconds',
            'Time spent processing audio files',
            ['stage', 'language'],
            registry=self.registry
        )
    
    def is_enabled(self) -> bool:
        """Проверяет включены ли метрики"""
        return self._enabled
    
    def get_metrics_text(self) -> str:
        """Возвращает метрики в формате Prometheus"""
        if not self._enabled:
            return "# Prometheus client not available\n"
        
        try:
            return generate_latest(self.registry).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}")
            return f"# Error generating metrics: {e}\n"

# Глобальный экземпляр коллектора метрик
_metrics_collector: Optional[MetricsCollector] = None

def get_metrics_collector() -> MetricsCollector:
    """Возвращает глобальный экземпляр коллектора метрик"""
    global _metrics_collector
    
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    
    return _metrics_collector

# Convenience функции
def track_file_processed(language: str, file_type: str, status: str = 'success'):
    """Отслеживает обработанный файл"""
    pass  # Placeholder для совместимости

def track_processing_time(stage: str, language: str, duration: float):
    """Отслеживает время обработки"""
    pass  # Placeholder для совместимости

def monitor_processing_time(stage: str, language: str = 'unknown'):
    """Декоратор для мониторинга времени обработки"""
    def decorator(func: Callable):
        return func  # Упрощенная версия
    return decorator

def monitor_api_calls(provider: str, method: str):
    """Декоратор для мониторинга API вызовов"""
    def decorator(func: Callable):
        return func  # Упрощенная версия
    return decorator

def track_api_request(provider: str, method: str, duration: float, success: bool = True):
    """Отслеживает API запрос"""
    pass  # Placeholder для совместимости

def track_active_tasks(count: int):
    """Отслеживает количество активных задач"""
    pass  # Placeholder для совместимости
