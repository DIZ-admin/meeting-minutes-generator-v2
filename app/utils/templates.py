"""
Утилиты для работы с шаблонами и генерации Markdown
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union

try:
    import jinja2
except ImportError:
    # Установка jinja2, если отсутствует
    import subprocess
    subprocess.check_call(["pip", "install", "jinja2"])
    import jinja2

from ..core.models.protocol import Protocol
from ..utils.logging import get_default_logger
from ..config.config import config
from datetime import datetime

logger = get_default_logger(__name__)

def load_prompt_template(prompt_name: str, language: str = "en") -> str:
    """
    Загружает шаблон промпта из файла
    
    Args:
        prompt_name: Имя промпта (без расширения)
        language: Язык промпта (en, de)
        
    Returns:
        Содержимое шаблона промпта
        
    Raises:
        FileNotFoundError: Если файл промпта не найден
    """
    try:
        # Формируем имя файла промпта
        if language.lower() == "de":
            prompt_file = f"{prompt_name}_de.txt"
        else:
            prompt_file = f"{prompt_name}.txt"
        
        # Формируем путь к промпту
        prompts_dir = Path(config.prompts_dir)
        prompt_path = prompts_dir / prompt_file
        
        # Проверяем существование файла
        if not prompt_path.exists():
            # Если локализованная версия не найдена, используем английскую
            if language.lower() == "de":
                prompt_file = f"{prompt_name}.txt"
                prompt_path = prompts_dir / prompt_file
                
                # Если и английская версия не найдена, выбрасываем исключение
                if not prompt_path.exists():
                    raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
                
                logger.warning(f"German prompt not found, using English prompt: {prompt_path}")
            else:
                raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        
        # Загружаем промпт из файла
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_content = f.read()
        
        logger.debug(f"Loaded prompt template: {prompt_path}")
        return prompt_content
        
    except FileNotFoundError:
        # Пробрасываем исключение дальше
        raise
        
    except Exception as e:
        error_msg = f"Failed to load prompt template: {e}"
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e

def load_template(template_name: str, language: str = "en") -> jinja2.Template:
    """
    Загружает шаблон Markdown
    
    Args:
        template_name: Имя шаблона (без расширения)
        language: Язык шаблона (en, de)
        
    Returns:
        Объект Jinja2 Template
        
    Raises:
        FileNotFoundError: Если файл шаблона не найден
        RuntimeError: Если не удалось загрузить шаблон
    """
    try:
        # Формируем имя файла шаблона
        if language.lower() == "de":
            template_file = f"{template_name}_de.md"
        else:
            template_file = f"{template_name}.md"
        
        # Формируем путь к шаблону
        templates_dir = Path(config.markdown_templates_dir)
        template_path = templates_dir / template_file
        
        # Проверяем существование файла
        if not template_path.exists():
            # Если локализованная версия не найдена, используем английскую
            if language.lower() == "de":
                template_file = f"{template_name}.md"
                template_path = templates_dir / template_file
                
                # Если и английская версия не найдена, выбрасываем исключение
                if not template_path.exists():
                    raise FileNotFoundError(f"Template file not found: {template_path}")
                
                logger.warning(f"German template not found, using English template: {template_path}")
            else:
                raise FileNotFoundError(f"Template file not found: {template_path}")
        
        # Загружаем шаблон из файла
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
        
        # Создаем окружение Jinja2
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(templates_dir),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Загружаем шаблон
        template = env.from_string(template_content)
        
        logger.debug(f"Loaded template: {template_path}")
        return template
        
    except FileNotFoundError:
        # Пробрасываем исключение дальше
        raise
        
    except Exception as e:
        error_msg = f"Failed to load template: {e}"
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e

def generate_markdown(
    protocol: Protocol,
    template_name: str = "protocol",
    language: str = "en"
) -> str:
    """
    Генерирует Markdown из объекта Protocol
    
    Args:
        protocol: Объект Protocol
        template_name: Имя шаблона (без расширения)
        language: Язык шаблона (en, de)
        
    Returns:
        Сгенерированный Markdown
        
    Raises:
        FileNotFoundError: Если файл шаблона не найден
        RuntimeError: Если не удалось сгенерировать Markdown
    """
    try:
        # Загружаем шаблон
        template = load_template(template_name, language)
        
        # Подготавливаем контекст для шаблона
        context = {
            "title": protocol.metadata.get("title", "Meeting Protocol"),
            "date": protocol.metadata.get("date", ""),
            "location": protocol.metadata.get("location", "N/A"),
            "organizer": protocol.metadata.get("organizer", "N/A"),
            "participants": protocol.participants,
            "summary": protocol.summary,
            "agenda_items": protocol.agenda_items,
            "decisions": protocol.decisions,
            "action_items": protocol.action_items,
            "error": protocol.metadata.get("error", "")
        }
        
        # Рендерим шаблон
        markdown = template.render(**context)
        
        logger.debug(f"Generated Markdown using template {template_name} and language {language}")
        return markdown
        
    except FileNotFoundError:
        # Пробрасываем исключение дальше
        raise
        
    except Exception as e:
        error_msg = f"Failed to generate Markdown: {e}"
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e

def generate_error_markdown(
    error_message: str,
    protocol: Optional[Protocol] = None,
    language: str = "en"
) -> str:
    """
    Генерирует Markdown с сообщением об ошибке
    
    Args:
        error_message: Сообщение об ошибке
        protocol: Опциональный объект Protocol (если есть)
        language: Язык шаблона (en, de)
        
    Returns:
        Сгенерированный Markdown с ошибкой
        
    Raises:
        RuntimeError: Если не удалось сгенерировать Markdown
    """
    try:
        # Если протокол не передан, создаем минимальный протокол с ошибкой
        if protocol is None:
            from datetime import datetime
            from ..core.models.protocol import Protocol
            
            protocol = Protocol(
                metadata={
                    "title": "Error: Protocol Generation Failed",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "error": error_message
                },
                participants=[],
                agenda_items=[],
                summary=f"Protocol generation failed: {error_message}",
                decisions=[],
                action_items=[]
            )
        else:
            # Добавляем сообщение об ошибке в метаданные протокола
            if "error" not in protocol.metadata:
                protocol.metadata["error"] = error_message
        
        # Генерируем Markdown
        return generate_markdown(protocol, template_name="protocol", language=language)
        
    except Exception as e:
        # Если не удалось сгенерировать Markdown через шаблон, возвращаем простой текст
        logger.error(f"Failed to generate error Markdown: {e}", exc_info=True)
        
        if language.lower() == "de":
            return f"""
# Fehler bei der Protokollgenerierung

**Datum:** {datetime.now().strftime("%Y-%m-%d")}

## Fehlermeldung
{error_message}

## Details
Bei der Generierung des Protokolls ist ein Fehler aufgetreten. 
Bitte überprüfen Sie die Eingabedaten und versuchen Sie es erneut.
"""
        else:
            return f"""
# Error in Protocol Generation

**Date:** {datetime.now().strftime("%Y-%m-%d")}

## Error Message
{error_message}

## Details
An error occurred during protocol generation.
Please check the input data and try again.
"""
