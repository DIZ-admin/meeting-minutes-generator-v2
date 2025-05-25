"""
Утилиты для валидации схем JSON
"""
import json
from pathlib import Path
from typing import Dict, Any, Union, Optional, List

try:
    import jsonschema
    from jsonschema import Draft7Validator, ValidationError
except ImportError:
    # Установка jsonschema, если отсутствует
    import subprocess
    subprocess.check_call(["pip", "install", "jsonschema"])
    import jsonschema
    from jsonschema import Draft7Validator, ValidationError

from ..core.exceptions import ValidationError as AppValidationError
from ..utils.logging import get_default_logger
from ..config.config import config

logger = get_default_logger(__name__)

def load_json_schema(schema_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Загружает JSON-схему из файла
    
    Args:
        schema_path: Путь к файлу схемы (если None, используется путь из конфигурации)
        
    Returns:
        Словарь с JSON-схемой
        
    Raises:
        FileNotFoundError: Если файл схемы не найден
        ValueError: Если содержимое файла не является валидным JSON
    """
    if schema_path is None:
        schema_path = config.schema_path
    else:
        schema_path = Path(schema_path)
    
    if not schema_path.exists():
        error_msg = f"Schema file not found: {schema_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
    
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        logger.debug(f"Loaded JSON schema from {schema_path}")
        return schema
        
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in schema file: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg) from e

def validate_json(
    data: Union[Dict[str, Any], str, Path],
    schema: Optional[Dict[str, Any]] = None,
    schema_path: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """
    Валидирует JSON-данные по схеме
    
    Args:
        data: JSON-данные (словарь, строка или путь к файлу)
        schema: JSON-схема (если None, загружается из schema_path)
        schema_path: Путь к файлу схемы (если None и schema None, используется путь из конфигурации)
        
    Returns:
        Валидированные данные (всегда словарь)
        
    Raises:
        AppValidationError: Если данные не соответствуют схеме
        ValueError: Если data не является валидным JSON
        FileNotFoundError: Если файл схемы или файл с данными не найден
    """
    # Загружаем данные, если это строка или путь
    if isinstance(data, (str, Path)):
        data_path = Path(data)
        if data_path.exists():
            try:
                with open(data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                logger.debug(f"Loaded JSON data from {data_path}")
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON in data file: {e}"
                logger.error(error_msg)
                raise ValueError(error_msg) from e
        else:
            # Если это не путь к файлу, пробуем распарсить как JSON-строку
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON string: {e}"
                logger.error(error_msg)
                raise ValueError(error_msg) from e
    
    # Убеждаемся, что данные - это словарь
    if not isinstance(data, dict):
        error_msg = f"Data is not a dictionary: {type(data)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Загружаем схему, если она не передана
    if schema is None:
        schema = load_json_schema(schema_path)
    
    # Валидируем данные
    try:
        jsonschema.validate(instance=data, schema=schema)
        
        logger.debug("JSON data passed validation")
        return data
        
    except ValidationError as e:
        error_msg = f"Validation error: {e.message}"
        logger.error(f"{error_msg} at path: {'/'.join(str(p) for p in e.path)}")
        
        # Собираем информацию об ошибке
        error_details = {
            "message": e.message,
            "path": '/'.join(str(p) for p in e.path) if e.path else None,
            "schema_path": '/'.join(str(p) for p in e.schema_path) if e.schema_path else None,
            "validator": e.validator,
            "validator_value": e.validator_value,
        }
        
        # Выбрасываем наше исключение
        raise AppValidationError(
            message=error_msg,
            details={"validation_error": error_details}
        ) from e

def validate_json_schema(
    data: Dict[str, Any],
    schema: Dict[str, Any]
) -> List[str]:
    """
    Валидирует данные по JSON-схеме и возвращает список ошибок
    
    Args:
        data: Данные для валидации
        schema: JSON-схема
        
    Returns:
        Список ошибок валидации (пустой список, если данные валидны)
    """
    validator = Draft7Validator(schema)
    errors = []
    
    for error in validator.iter_errors(data):
        path = "/".join(str(p) for p in error.path) if error.path else "root"
        errors.append(f"Error at {path}: {error.message}")
    
    return errors

def validate_protocol_json(
    data: Union[Dict[str, Any], str, Path],
    strict: bool = False
) -> Dict[str, Any]:
    """
    Валидирует JSON-данные протокола по схеме protocol_schema.json
    
    Args:
        data: JSON-данные протокола (словарь, строка или путь к файлу)
        strict: Если True, то вызывает исключение при любых ошибках валидации.
             Если False, пытается исправить некоторые ошибки и вернуть исправленные данные
        
    Returns:
        Валидированные данные протокола
        
    Raises:
        AppValidationError: Если данные не соответствуют схеме и strict=True
        ValueError: Если data не является валидным JSON
        FileNotFoundError: Если файл схемы или файл с данными не найден
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Получаем путь к схеме
    schema_path = Path(__file__).parent / "schemas" / "protocol_schema.json"
    
    try:
        # Пытаемся валидировать данные по схеме
        return validate_json(data, schema_path=schema_path)
    except Exception as e:
        logger.warning(f"Protocol validation error: {e}")
        
        if strict:
            # В строгом режиме просто пробрасываем исключение дальше
            raise
        
        # В нестрогом режиме пытаемся исправить данные
        logger.info("Attempting to fix protocol data structure...")
        
        # Преобразуем данные в словарь, если они еще не словарь
        if isinstance(data, (str, Path)):
            try:
                if isinstance(data, str):
                    if data.strip().startswith('{'): 
                        import json
                        data = json.loads(data)
                    else:
                        with open(data, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                else:  # Path
                    with open(data, 'r', encoding='utf-8') as f:
                        data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to parse protocol data: {e}")
                raise ValueError(f"Failed to parse protocol data: {e}") from e
        
        # Если это не словарь, мы не можем исправить
        if not isinstance(data, dict):
            logger.error("Protocol data is not a dictionary")
            raise ValueError("Protocol data must be a dictionary")
        
        # Исправляем структуру данных
        fixed_data = {}
        
        # Добавляем обязательные поля
        fixed_data["metadata"] = data.get("metadata", {})
        if not isinstance(fixed_data["metadata"], dict):
            fixed_data["metadata"] = {}
        
        # Добавляем обязательные поля в метаданные
        if "title" not in fixed_data["metadata"]:
            fixed_data["metadata"]["title"] = "Meeting Protocol"
        
        if "date" not in fixed_data["metadata"]:
            from datetime import datetime
            fixed_data["metadata"]["date"] = datetime.now().strftime("%Y-%m-%d")
        
        # Добавляем остальные поля
        fixed_data["summary"] = data.get("summary", "")
        fixed_data["participants"] = data.get("participants", [])
        fixed_data["agenda_items"] = data.get("agenda_items", [])
        fixed_data["decisions"] = data.get("decisions", [])
        fixed_data["action_items"] = data.get("action_items", data.get("actions", []))
        
        # Добавляем время создания
        if "created_at" not in fixed_data:
            from datetime import datetime
            fixed_data["created_at"] = datetime.now().isoformat()
        elif hasattr(fixed_data["created_at"], 'isoformat'):
            # Если это datetime объект, конвертируем в строку
            fixed_data["created_at"] = fixed_data["created_at"].isoformat()
        
        logger.info("Protocol data structure fixed successfully")
        return fixed_data

def convert_to_egl_format(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Конвертирует данные протокола в формат egl_protokoll.json
    
    Args:
        data: Данные протокола
        
    Returns:
        Данные в формате egl_protokoll.json
        
    Raises:
        ValueError: Если data не содержит необходимых полей
    """
    try:
        # Проверяем наличие необходимых полей
        if "metadata" not in data:
            raise ValueError("Missing 'metadata' field")
        
        if "participants" not in data:
            raise ValueError("Missing 'participants' field")
        
        if "agenda_items" not in data:
            raise ValueError("Missing 'agenda_items' field")
        
        # Собираем meta
        meta = {
            "titel": data["metadata"].get("title", "Protokoll"),
            "datum": data["metadata"].get("date", ""),
            "ort": data["metadata"].get("location", ""),
            "sitzungsleiter": data["metadata"].get("organizer", ""),
            "verfasser": data["metadata"].get("author", "AI Assistant"),
        }
        
        # Собираем teilnehmer
        anwesend = []
        entschuldigt = []
        
        for participant in data["participants"]:
            if participant.get("present", True):
                anwesend.append(participant["name"])
            else:
                entschuldigt.append(participant["name"])
        
        teilnehmer = {
            "anwesend": anwesend,
            "entschuldigt": entschuldigt,
        }
        
        # Собираем traktanden
        traktanden = []
        
        for i, item in enumerate(data["agenda_items"]):
            traktand = {
                "id": item.get("id") or f"T{i+1:03d}",
                "titel": item["topic"],
                "diskussion": item.get("discussion_summary", ""),
                "entscheidungen": [],
                "pendenzen": [],
            }
            
            # Добавляем entscheidungen
            for decision in item.get("decisions_made", []):
                if isinstance(decision, dict):
                    traktand["entscheidungen"].append(decision.get("description", ""))
                else:
                    traktand["entscheidungen"].append(str(decision))
            
            # Добавляем pendenzen
            for action in item.get("action_items_assigned", []):
                if isinstance(action, dict):
                    pendenz = {
                        "wer": action.get("who", ""),
                        "was": action.get("what", ""),
                        "frist": action.get("due", None),
                    }
                    traktand["pendenzen"].append(pendenz)
            
            traktanden.append(traktand)
        
        # Собираем анханг
        anhänge = data["metadata"].get("attachments", [])
        
        # Собираем финальный результат
        result = {
            "meta": meta,
            "teilnehmer": teilnehmer,
            "traktanden": traktanden,
            "anhänge": anhänge,
        }
        
        logger.debug("Converted protocol data to egl_protokoll.json format")
        return result
        
    except (KeyError, ValueError) as e:
        error_msg = f"Error converting to egl format: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg) from e


def fix_protocol_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Пытается исправить структуру данных протокола для соответствия схеме
    
    Args:
        data: Исходные данные протокола
        
    Returns:
        Исправленные данные протокола
    """
    try:
        logger.info("Attempting to fix protocol data structure...")
        
        # Создаем базовую структуру
        fixed_data = {
            "metadata": {},
            "summary": "",
            "participants": [],
            "agenda_items": [],
            "decisions": [],
            "action_items": []
        }
        
        # Исправляем метаданные
        if "metadata" in data:
            fixed_data["metadata"] = data["metadata"]
        elif "meta" in data:
            fixed_data["metadata"] = data["meta"]
        
        # Убеждаемся что обязательные поля метаданных присутствуют
        if "title" not in fixed_data["metadata"]:
            fixed_data["metadata"]["title"] = data.get("title", "Meeting Protocol")
        if "date" not in fixed_data["metadata"]:
            fixed_data["metadata"]["date"] = data.get("date", "Unknown Date")
            
        # Исправляем summary
        if "summary" in data:
            fixed_data["summary"] = data["summary"]
        elif "zusammenfassung" in data:
            fixed_data["summary"] = data["zusammenfassung"]
        elif "overall_summary" in data:
            fixed_data["summary"] = data["overall_summary"]
        else:
            fixed_data["summary"] = "No summary available"
            
        # Исправляем участников
        if "participants" in data:
            fixed_data["participants"] = data["participants"]
        elif "teilnehmer" in data:
            # Преобразуем немецкий формат
            if isinstance(data["teilnehmer"], dict):
                participants = []
                for person in data["teilnehmer"].get("anwesend", []):
                    if isinstance(person, str):
                        participants.append({"name": person, "status": "present"})
                    elif isinstance(person, dict):
                        participants.append({**person, "status": "present"})
                        
                for person in data["teilnehmer"].get("abwesend", []):
                    if isinstance(person, str):
                        participants.append({"name": person, "status": "absent"})
                    elif isinstance(person, dict):
                        participants.append({**person, "status": "absent"})
                        
                fixed_data["participants"] = participants
        
        # Исправляем пункты повестки
        if "agenda_items" in data:
            fixed_data["agenda_items"] = data["agenda_items"]
        elif "traktanden" in data:
            agenda_items = []
            for item in data["traktanden"]:
                agenda_item = {
                    "title": item.get("titel", "Untitled"),
                    "discussion": item.get("diskussion", ""),
                    "decisions": item.get("entscheidungen", []),
                    "action_items": item.get("pendenzen", [])
                }
                agenda_items.append(agenda_item)
            fixed_data["agenda_items"] = agenda_items
            
        # Исправляем решения
        if "decisions" in data:
            fixed_data["decisions"] = data["decisions"]
        elif "entscheidungen" in data:
            fixed_data["decisions"] = data["entscheidungen"]
            
        # Исправляем задачи
        if "action_items" in data:
            fixed_data["action_items"] = data["action_items"]
        elif "pendenzen" in data:
            fixed_data["action_items"] = data["pendenzen"]
        elif "actions" in data:
            fixed_data["action_items"] = data["actions"]
            
        logger.info("Protocol data structure fixed successfully")
        return fixed_data
        
    except Exception as e:
        logger.error(f"Failed to fix protocol data: {e}")
        # Возвращаем минимальную структуру
        return {
            "metadata": {"title": "Error Protocol", "date": "Unknown"},
            "summary": f"Error processing protocol: {e}",
            "participants": [],
            "agenda_items": [],
            "decisions": [],
            "action_items": []
        }
