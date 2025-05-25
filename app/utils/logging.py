"""
Утилиты для логирования

Модуль предоставляет функции для настройки логирования в приложении.
Поддерживается как настройка через код, так и через YAML-конфигурацию.
"""
import logging
import logging.config
import sys
import os
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional, Union, Dict, Any

# Пытаемся импортировать colorlog для цветного логирования
try:
    import colorlog
except ImportError:
    colorlog = None

try:
    from ..config.settings import DEFAULT_LOG_LEVEL, DEFAULT_LOG_FORMAT, LOGS_DIR
except ImportError:
    # Значения по умолчанию, если не удалось импортировать настройки
    DEFAULT_LOG_LEVEL = "INFO"
    DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOGS_DIR = Path("logs")

def setup_logger(
    name: str,
    log_level: Union[str, int] = DEFAULT_LOG_LEVEL,
    log_format: str = DEFAULT_LOG_FORMAT,
    log_file: Optional[Union[str, Path]] = None,
    console_output: bool = True
) -> logging.Logger:
    """
    Настраивает и возвращает логгер
    
    Args:
        name (str): Имя логгера
        log_level (Union[str, int]): Уровень логирования
        log_format (str): Формат логов
        log_file (Optional[Union[str, Path]]): Путь к файлу логов
        console_output (bool): Выводить ли логи в консоль
        
    Returns:
        logging.Logger: Настроенный логгер
    """
    # Преобразование уровня логирования из строки в число
    if isinstance(log_level, str):
        numeric_level = getattr(logging, log_level.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError(f"Invalid log level: {log_level}")
        log_level = numeric_level
    
    # Создание логгера
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.handlers = []  # Сбрасываем существующие хэндлеры
    
    # Создание форматтера
    formatter = logging.Formatter(log_format)
    
    # Добавление хэндлера для вывода в консоль
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # Добавление хэндлера для вывода в файл
    if log_file is not None:
        log_file_path = Path(log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

def get_default_logger(name: str) -> logging.Logger:
    """
    Возвращает логгер с настройками по умолчанию
    
    Args:
        name (str): Имя логгера
        
    Returns:
        logging.Logger: Логгер с настройками по умолчанию
    """
    # Создание директории для логов если она не существует
    logs_dir = Path(LOGS_DIR)
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Имя файла для логов основано на имени логгера и текущей дате
    timestamp = datetime.now().strftime("%Y-%m-%d")
    log_filename = logs_dir / f"{name}_{timestamp}.log"
    
    return setup_logger(
        name=name,
        log_level=DEFAULT_LOG_LEVEL,
        log_format=DEFAULT_LOG_FORMAT,
        log_file=log_filename,
        console_output=True
    )

def setup_logging_from_yaml(config_path: Optional[Union[str, Path]] = None) -> None:
    """
    Настраивает логирование из YAML-файла
    
    Args:
        config_path: Путь к файлу конфигурации YAML. 
                    Если None, используется стандартный путь config/logging.yaml
    """
    # Определяем путь к файлу конфигурации
    if config_path is None:
        # Ищем файл конфигурации в стандартных местах
        possible_paths = [
            Path("config/logging.yaml"),
            Path("../config/logging.yaml"),
            Path(__file__).parent.parent.parent / "config" / "logging.yaml"
        ]
        
        for path in possible_paths:
            if path.exists():
                config_path = path
                break
        else:
            print(f"Warning: Logging configuration file not found in {possible_paths}. Using default configuration.")
            return
    else:
        config_path = Path(config_path)
        if not config_path.exists():
            print(f"Warning: Logging configuration file not found at {config_path}. Using default configuration.")
            return
    
    # Создаем директорию для логов, если она не существует
    logs_dir = os.environ.get('LOGS_DIR', 'logs')
    Path(logs_dir).mkdir(exist_ok=True, parents=True)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f.read())
        
        # Проверяем наличие colorlog для цветного логирования
        if colorlog is None:
            # Если colorlog не установлен, заменяем цветной форматтер на стандартный
            for formatter_name, formatter_config in config.get('formatters', {}).items():
                if formatter_config.get('()') == 'colorlog.ColoredFormatter':
                    print(f"Warning: colorlog not installed. Using standard formatter for {formatter_name}.")
                    formatter_config.pop('()', None)
                    formatter_config.pop('log_colors', None)
        
        # Настраиваем логирование
        logging.config.dictConfig(config)
        print(f"Logging configured from {config_path}")
    except Exception as e:
        print(f"Error configuring logging from {config_path}: {e}")
        # Используем стандартную конфигурацию
        logging.basicConfig(
            level=logging.INFO,
            format=DEFAULT_LOG_FORMAT,
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )

# Инициализируем логирование при импорте модуля
# Не инициализируем здесь, так как это может вызвать проблемы при импорте
# Инициализация будет выполнена в основных модулях приложения

# Логгер для всего приложения
app_logger = get_default_logger("app")
