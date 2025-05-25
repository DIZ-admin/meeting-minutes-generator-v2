import logging
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

try:
    from ...core.models.protocol import Protocol
    from ...core.exceptions import ValidationError
    from ...utils.schemas import validate_json_schema
    from ...utils.templates import load_prompt_template
    from ...core.services.analysis_service import MapReduceService
except ImportError:
    logger_temp = logging.getLogger(__name__ + ".fallback")
    logger_temp.warning("Failed to import ProtocolService dependencies, using fallbacks. This may cause issues.")

    class Protocol:
        def to_egl_json(self): return {}
        def __init__(self, *args, **kwargs): 
            self.metadata = kwargs.get('metadata', {})
            self.summary = kwargs.get('summary', '')
            self.decisions = kwargs.get('decisions', [])
            self.action_items = kwargs.get('action_items', [])
            self.participants = kwargs.get('participants', [])
            self.agenda_items = kwargs.get('agenda_items', [])
        
        def to_dict(self):
            """
            Преобразует протокол в словарь
            
            Returns:
                Dict: Словарь с данными протокола
            """
            return {
                'metadata': self.metadata,
                'summary': self.summary,
                'decisions': self.decisions,
                'action_items': self.action_items,
                'participants': self.participants if hasattr(self, 'participants') else [],
                'agenda_items': self.agenda_items if hasattr(self, 'agenda_items') else []
            }

    class ValidationError(Exception):
        def __init__(self, message: str, validation_errors: Optional[List[str]] = None):
            super().__init__(message)
            self.validation_errors = validation_errors if validation_errors is not None else []

    def validate_json_schema(data, schema):
        return []

    def load_prompt_template(template_name: str, lang: str) -> str:
        return f"Prompt for {template_name} in {lang}"

    class MapReduceService:
        def process_transcript(self, *args, **kwargs) -> Dict[str, Any]:
            return {"metadata": {}, "summary": "Fallback summary", "decisions": [], "action_items": []}

logger = logging.getLogger(__name__)

class ProtocolService:
    def __init__(self, schema_path: Optional[str] = None, language: str = "en", map_reduce_service: Optional[MapReduceService] = None):
        self.schema: Optional[Dict[str, Any]] = None
        self.language = language
        self.map_reduce_service = map_reduce_service or MapReduceService()

        if schema_path:
            try:
                schema_file = Path(schema_path)
                if schema_file.exists() and schema_file.is_file():
                    with open(schema_file, 'r', encoding='utf-8') as f:
                        self.schema = json.load(f)
                    logger.info(f"Protocol schema loaded from {schema_path}")
                else:
                    logger.warning(f"Schema file not found or is not a file: {schema_path}. Validation will be skipped.")
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding schema JSON from {schema_path}: {e}. Validation will be skipped.")
            except Exception as e:
                logger.error(f"Unexpected error loading schema from {schema_path}: {e}. Validation will be skipped.")
        else:
            logger.info("No schema path provided to ProtocolService. Protocol validation will be skipped.")

    def _validate_protocol(self, protocol: Protocol):
        if not self.schema:
            logger.warning("Schema not available for ProtocolService, skipping validation of protocol.")
            return
        
        try:
            if not hasattr(protocol, 'to_egl_json'):
                logger.error("Protocol object is missing 'to_egl_json' method.")
                raise AttributeError("Protocol object does not have 'to_egl_json' method required for validation.")

            egl_json = protocol.to_egl_json()
            
            validation_errors = validate_json_schema(egl_json, self.schema)
            
            if validation_errors:
                error_msg = f"Protocol validation failed: {', '.join(validation_errors)}"
                logger.error(error_msg)
                raise ValidationError(
                    message=error_msg,
                    validation_errors=validation_errors
                )
            
            logger.debug("Protocol validated successfully against schema.")
            
        except ValidationError:
            raise
        except AttributeError as e:
            logger.error(f"Attribute error during protocol validation: {e}")
            raise ValidationError(message=str(e)) from e
        except Exception as e:
            error_msg = f"Unexpected error during protocol validation: {e}"
            logger.error(error_msg, exc_info=True)
            raise ValidationError(message=error_msg) from e

    def _create_protocol_from_json(self, protocol_json: Dict[str, Any]) -> Protocol:
        """
        Создает объект Protocol из JSON-данных
        
        Args:
            protocol_json: Словарь с данными протокола
            
        Returns:
            Объект Protocol
        """
        # Проверяем и преобразуем данные для совместимости с моделью Protocol
        protocol_data = {}
        
        # Метаданные
        protocol_data["metadata"] = protocol_json.get("metadata", {})
        
        # Резюме
        protocol_data["summary"] = protocol_json.get("summary", "")
        
        # Участники
        participants = protocol_json.get("participants", [])
        protocol_data["participants"] = participants
        
        # Пункты повестки
        agenda_items = protocol_json.get("agenda_items", [])
        protocol_data["agenda_items"] = agenda_items
        
        # Решения
        decisions = protocol_json.get("decisions", [])
        protocol_data["decisions"] = decisions
        
        # Задачи - могут быть под ключом "actions" или "action_items"
        action_items = protocol_json.get("action_items", protocol_json.get("actions", []))
        protocol_data["action_items"] = action_items
        
        # Добавляем время создания, если отсутствует
        if "created_at" not in protocol_data:
            protocol_data["created_at"] = datetime.now()
        
        # Проверяем и преобразуем данные для совместимости с моделью Protocol
        try:
            # Валидируем данные протокола с помощью JSON-схемы
            try:
                from ...utils.schemas import validate_protocol_json
                # Валидируем данные протокола
                validate_protocol_json(protocol_data)
                logger.debug("Protocol data validated successfully")
            except ImportError:
                logger.warning("Failed to import validate_protocol_json, skipping validation")
            except Exception as e:
                logger.warning(f"Protocol data validation failed: {e}")
                # Попытаемся исправить данные если возможно
                try:
                    from ...utils.schemas import fix_protocol_data
                    protocol_data = fix_protocol_data(protocol_data)
                    logger.info("Protocol data structure fixed")
                except Exception as fix_error:
                    logger.error(f"Failed to fix protocol data: {fix_error}")
            
            # Создаем объект Protocol с безопасной обработкой ошибок
            try:
                return Protocol(**protocol_data)
            except TypeError as te:
                logger.error(f"TypeError creating Protocol: {te}")
                # Попытка создать протокол с минимальными данными
                safe_data = {
                    'metadata': protocol_data.get('metadata', {}),
                    'summary': protocol_data.get('summary', 'No summary available'),
                    'decisions': protocol_data.get('decisions', []),
                    'action_items': protocol_data.get('action_items', []),
                    'participants': protocol_data.get('participants', []),
                    'agenda_items': protocol_data.get('agenda_items', [])
                }
                return Protocol(**safe_data)
            
        except Exception as e:
            logger.error(f"Error creating Protocol object from JSON: {e}")
            logger.debug(f"Protocol data that caused error: {protocol_data}")
            # Создаем минимально работающий протокол
            return Protocol(
                metadata=protocol_data.get("metadata", {}) if isinstance(protocol_data, dict) else {},
                summary=f"Failed to create protocol: {e}",
                decisions=[],
                action_items=[],
                participants=[],
                agenda_items=[]
            )

    def create_protocol_from_segments(
        self,
        segments: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        language: Optional[str] = None,
        temperature: float = 0.3,
        **kwargs
    ) -> Protocol:
        lang = language or self.language
        logger.info(f"Creating protocol from {len(segments)} segments with language: {lang}")
        
        if not self.map_reduce_service:
            error_msg = "MapReduceService is not initialized."
            logger.error(error_msg)
            raise ValidationError(message=error_msg)
        
        current_metadata = metadata.copy() if metadata else {}
        
        if "title" not in current_metadata:
            current_metadata["title"] = "Meeting Protocol"
            
        if "date" not in current_metadata:
            current_metadata["date"] = datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Загружаем шаблоны промптов из директории prompt_templates_dir
            # Имена файлов должны соответствовать шаблону: map_[lang].txt, reduce_[lang].txt, refine_[lang].txt
            try:
                from app.config.config import config
                prompt_templates_dir = config.prompt_templates_dir
                
                map_template_path = prompt_templates_dir / f"map_{lang}.txt"
                reduce_template_path = prompt_templates_dir / f"reduce_{lang}.txt"
                refine_template_path = prompt_templates_dir / f"refine_{lang}.txt"
                
                with open(map_template_path, 'r', encoding='utf-8') as f:
                    map_prompt_template = f.read()
                    
                with open(reduce_template_path, 'r', encoding='utf-8') as f:
                    reduce_prompt_template = f.read()
                    
                with open(refine_template_path, 'r', encoding='utf-8') as f:
                    refine_prompt_template = f.read()
                    
                logger.info(f"Loaded prompt templates for language '{lang}' from {prompt_templates_dir}")
            except Exception as e:
                # Если не удалось загрузить шаблоны из файлов, используем fallback
                logger.warning(f"Failed to load prompt templates from files: {e}. Using fallback templates.")
                map_prompt_template = f"Analyze transcript in {lang} language and extract key points."
                reduce_prompt_template = f"Summarize the analysis results in {lang} language."
                refine_prompt_template = f"Create a formal meeting protocol in {lang} language."
        except Exception as e:
            error_msg = f"Failed to prepare prompt templates for language '{lang}': {e}"
            logger.error(error_msg, exc_info=True)
            raise ValidationError(message=error_msg) from e
        
        try:
            # Вызываем метод process_transcript с правильными параметрами
            # Обратите внимание, что мы не передаем параметры, которые не поддерживаются
            logger.debug(f"Calling process_transcript with {len(segments)} segments, language={lang}")
            result = self.map_reduce_service.process_transcript(
                transcript=segments,
                meeting_info=current_metadata,  # Передаем метаданные как meeting_info
                language=lang
            )
            logger.debug(f"process_transcript returned result of type {type(result)}")
            if isinstance(result, tuple):
                logger.debug(f"Result is a tuple of length {len(result)}")
                for i, item in enumerate(result):
                    logger.debug(f"Item {i} is of type {type(item)}")
            elif isinstance(result, dict):
                logger.debug(f"Result is a dict with keys: {result.keys()}")
            else:
                logger.debug(f"Result is of unexpected type: {type(result)}")

            
            # Проверяем, что результат - это кортеж (protocol, markdown)
            if isinstance(result, tuple) and len(result) >= 1:
                # Если первый элемент кортежа - это объект Protocol
                if isinstance(result[0], Protocol):
                    protocol = result[0]
                    # Обновляем метаданные протокола, если необходимо
                    if not hasattr(protocol, 'metadata') or protocol.metadata is None:
                        protocol.metadata = {}
                    protocol.metadata.update(current_metadata)
                    
                    if self.schema:
                        self._validate_protocol(protocol)
                    
                    logger.info(f"Protocol '{protocol.metadata.get('title', 'N/A')}' created successfully.")
                    return protocol
                # Если первый элемент кортежа - это словарь
                elif isinstance(result[0], dict):
                    protocol_json = result[0]
                    if "metadata" not in protocol_json:
                        protocol_json["metadata"] = {}
                    protocol_json["metadata"].update(current_metadata)
                    
                    protocol = self._create_protocol_from_json(protocol_json)
                    
                    if self.schema:
                        self._validate_protocol(protocol)
                    
                    logger.info(f"Protocol '{protocol.metadata.get('title', 'N/A')}' created successfully.")
                    return protocol
            # Если результат - это словарь (обратная совместимость)
            elif isinstance(result, dict):
                protocol_json = result
                if "metadata" not in protocol_json:
                    protocol_json["metadata"] = {}
                protocol_json["metadata"].update(current_metadata)
                
                protocol = self._create_protocol_from_json(protocol_json)
                
                if self.schema:
                    self._validate_protocol(protocol)
                
                logger.info(f"Protocol '{protocol.metadata.get('title', 'N/A')}' created successfully.")
                return protocol
            else:
                raise ValueError(f"MapReduceService returned unexpected type: {type(result)}")

            
        except Exception as e:
            error_type = type(e).__name__
            error_details = str(e)
            error_msg = f"Failed to create protocol from segments: {error_type}: {error_details}"
            logger.error(error_msg, exc_info=True)
            
            # Добавляем дополнительную информацию об ошибке для отладки
            if hasattr(e, '__traceback__'):
                import traceback
                tb_str = ''.join(traceback.format_tb(e.__traceback__))
                logger.debug(f"Traceback:\n{tb_str}")
            
            # Создаем пустой протокол с информацией об ошибке
            error_protocol = Protocol(
                metadata=current_metadata,
                summary=f"Failed to generate protocol content due to unknown error",
                decisions=[],
                action_items=[],
                participants=[],
                agenda_items=[]
            )
            return error_protocol
