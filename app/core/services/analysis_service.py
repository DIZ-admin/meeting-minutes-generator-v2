"""
Сервис для обработки текста с использованием паттерна Map-Reduce-Refine
"""
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
from concurrent.futures import ThreadPoolExecutor

from ...adapters.llm.base import LLMAdapter
from ...adapters.llm.openai_adapter import OpenAILLMAdapter
from ...core.exceptions import LLMError, ConfigError, ValidationError
from ...core.models.transcript import Transcript, TranscriptSegment
from ...core.models.protocol import Protocol, AgendaItem, Decision, ActionItem, Participant
from ...utils.logging import get_default_logger
from ...utils.text import split_text_into_chunks, split_transcript_segments, merge_text_with_headers
from ...config.config import config

logger = get_default_logger(__name__)

class MapReduceService:
    """
    Сервис для обработки текста с использованием паттерна Map-Reduce-Refine.
    
    Этот сервис позволяет обрабатывать большие тексты или транскрипции,
    разбивая их на части (Map), затем объединяя результаты (Reduce)
    и наконец улучшая итоговый результат (Refine).
    """
    
    def __init__(
        self,
        llm_adapter: Optional[LLMAdapter] = None,
        map_temperature: float = 0.2,
        reduce_temperature: float = 0.3,
        refine_temperature: float = 0.5,
        max_parallel_workers: int = 5,
        templates_dir: Optional[Path] = None
    ):
        """
        Инициализирует сервис Map-Reduce-Refine
        
        Args:
            llm_adapter: Адаптер для языковых моделей (если None, создается OpenAILLMAdapter)
            map_temperature: Температура для этапа Map
            reduce_temperature: Температура для этапа Reduce
            refine_temperature: Температура для этапа Refine
            max_parallel_workers: Максимальное количество параллельных рабочих потоков
            templates_dir: Директория с шаблонами промптов (если None, берется из конфигурации)
        
        Raises:
            ConfigError: Если не удалось создать адаптер по умолчанию или загрузить шаблоны
        """
        # Инициализируем адаптер LLM
        if llm_adapter:
            self.llm_adapter = llm_adapter
        else:
            try:
                self.llm_adapter = OpenAILLMAdapter()
                logger.info("Successfully initialized default OpenAILLMAdapter")
            except ConfigError as e:
                error_msg = f"Failed to initialize default LLM adapter: {e}"
                logger.error(error_msg)
                raise ConfigError(error_msg) from e
        
        # Сохраняем настройки
        self.map_temperature = map_temperature
        self.reduce_temperature = reduce_temperature
        self.refine_temperature = refine_temperature
        self.max_parallel_workers = min(max_parallel_workers, os.cpu_count() or 1)
        
        # Загружаем шаблоны промптов
        self.templates_dir = templates_dir or Path(config.prompt_templates_dir)
        self._load_prompt_templates()
        
        logger.info(f"MapReduceService initialized with {type(self.llm_adapter).__name__}")
    
    def _load_prompt_templates(self):
        """
        Загружает шаблоны промптов из файлов
        
        Raises:
            ConfigError: Если не удалось загрузить шаблоны
        """
        try:
            # Проверяем существование директории с шаблонами
            if not self.templates_dir.exists():
                error_msg = f"Templates directory not found at {self.templates_dir}"
                logger.error(error_msg)
                raise ConfigError(error_msg)
            
            # Загружаем шаблоны
            map_prompt_path = self.templates_dir / "map_prompt.txt"
            reduce_prompt_path = self.templates_dir / "reduce_prompt.txt"
            refine_prompt_path = self.templates_dir / "refine_prompt.txt"
            
            # Загружаем шаблоны для разных языков
            map_prompt_de_path = self.templates_dir / "map_prompt_de.txt"
            reduce_prompt_de_path = self.templates_dir / "reduce_prompt_de.txt"
            refine_prompt_de_path = self.templates_dir / "refine_prompt_de.txt"
            
            # Загружаем английские шаблоны
            with open(map_prompt_path, "r", encoding="utf-8") as f:
                self.map_prompt_template = f.read()
            
            with open(reduce_prompt_path, "r", encoding="utf-8") as f:
                self.reduce_prompt_template = f.read()
            
            with open(refine_prompt_path, "r", encoding="utf-8") as f:
                self.refine_prompt_template = f.read()
            
            # Загружаем немецкие шаблоны, если они существуют
            self.map_prompt_template_de = None
            self.reduce_prompt_template_de = None
            self.refine_prompt_template_de = None
            
            if map_prompt_de_path.exists():
                with open(map_prompt_de_path, "r", encoding="utf-8") as f:
                    self.map_prompt_template_de = f.read()
            
            if reduce_prompt_de_path.exists():
                with open(reduce_prompt_de_path, "r", encoding="utf-8") as f:
                    self.reduce_prompt_template_de = f.read()
            
            if refine_prompt_de_path.exists():
                with open(refine_prompt_de_path, "r", encoding="utf-8") as f:
                    self.refine_prompt_template_de = f.read()
            
            logger.debug("Successfully loaded prompt templates")
            
        except Exception as e:
            error_msg = f"Error loading prompt templates: {e}"
            logger.error(error_msg, exc_info=True)
            raise ConfigError(error_msg) from e
    
    def process_transcript(
        self,
        transcript: Union[Transcript, List[Dict[str, Any]], List[TranscriptSegment]],
        meeting_info: Optional[Dict[str, Any]] = None,
        language: str = "en"
    ) -> Tuple[Protocol, str]:
        """
        Обрабатывает транскрипцию по алгоритму Map-Reduce-Refine
        
        Args:
            transcript: Транскрипция (объект Transcript, список сегментов или словарей)
            meeting_info: Дополнительная информация о встрече (название, дата, участники и т.д.)
            language: Язык транскрипции (en, de)
            
        Returns:
            Кортеж из объекта Protocol и сгенерированного Markdown-текста
        
        Raises:
            LLMError: Если произошла ошибка при обработке текста
            ValidationError: Если произошла ошибка при валидации результата
        """
        start_time = time.time()
        logger.info(f"Starting Map-Reduce-Refine processing of transcript with language '{language}'")
        
        # Если meeting_info не передано, создаем пустой словарь
        if meeting_info is None:
            meeting_info = {}
        
        # 1. Подготовка сегментов для обработки
        segments = self._prepare_segments(transcript)
        logger.debug(f"Prepared {len(segments)} segments for processing")
        
        # 2. Разбиваем сегменты на чанки
        chunks = split_transcript_segments(segments)
        logger.debug(f"Split segments into {len(chunks)} chunks")
        
        # 3. Этап MAP: обрабатываем каждый чанк параллельно
        map_results = self._process_map_stage(chunks, language)
        logger.debug(f"Completed MAP stage, got {len(map_results)} results")
        
        # 4. Этап REDUCE: объединяем результаты
        reduced_data = self._process_reduce_stage(map_results, language)
        logger.debug("Completed REDUCE stage")
        
        # 5. Этап REFINE: генерируем финальный протокол
        protocol, markdown = self._process_refine_stage(reduced_data, meeting_info, language)
        
        end_time = time.time()
        processing_time = end_time - start_time
        logger.info(f"Completed Map-Reduce-Refine processing in {processing_time:.2f} seconds")
        
        return protocol, markdown
    
    def _prepare_segments(
        self,
        transcript: Union[Transcript, List[Dict[str, Any]], List[TranscriptSegment]]
    ) -> List[Dict[str, Any]]:
        """
        Подготавливает сегменты транскрипции для обработки
        
        Args:
            transcript: Транскрипция в различных форматах
            
        Returns:
            Список словарей с сегментами
        """
        # Если transcript - это объект Transcript, извлекаем сегменты
        if isinstance(transcript, Transcript):
            return [segment.to_dict() for segment in transcript.segments]
        
        # Если transcript - это список TranscriptSegment, преобразуем в словари
        if transcript and isinstance(transcript[0], TranscriptSegment):
            return [segment.to_dict() for segment in transcript]
        
        # Если transcript - это список словарей, возвращаем как есть
        if transcript and isinstance(transcript[0], dict):
            return transcript
        
        # Если ничего не подошло, возвращаем пустой список
        return []
    
    def _process_map_stage(
        self,
        chunks: List[List[Dict[str, Any]]],
        language: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Выполняет этап MAP: обрабатывает каждый чанк параллельно
        
        Args:
            chunks: Список чанков сегментов
            language: Язык обработки
            
        Returns:
            Список результатов обработки каждого чанка
        """
        logger.info(f"Starting MAP stage with {len(chunks)} chunks")
        
        # Если чанков нет, возвращаем пустой список
        if not chunks:
            logger.warning("No chunks to process in MAP stage")
            return []
        
        # Выбираем шаблон промпта в зависимости от языка
        if language.lower() == "de" and self.map_prompt_template_de:
            prompt_template = self.map_prompt_template_de
        else:
            prompt_template = self.map_prompt_template
        
        # Подготавливаем текстовые представления чанков
        text_chunks = []
        for chunk in chunks:
            # Объединяем тексты сегментов в один
            chunk_text = "\n\n".join(
                f"[{segment.get('speaker', 'UNKNOWN')}]: {segment.get('text', '')}"
                for segment in chunk
            )
            text_chunks.append(chunk_text)
        
        # Выполняем параллельную обработку
        map_results = []
        
        with ThreadPoolExecutor(max_workers=self.max_parallel_workers) as executor:
            # Создаем задачи для каждого чанка
            futures = [
                executor.submit(
                    self._process_map_chunk,
                    chunk_text,
                    prompt_template,
                    self.map_temperature
                )
                for chunk_text in text_chunks
            ]
            
            # Собираем результаты
            for i, future in enumerate(futures):
                try:
                    result = future.result(timeout=120)  # Таймаут 2 минуты на обработку чанка
                    map_results.append(result)
                    logger.debug(f"Processed chunk {i+1}/{len(text_chunks)}")
                except Exception as e:
                    logger.error(f"Error processing chunk {i+1}: {e}", exc_info=True)
                    # Добавляем пустой результат, чтобы сохранить порядок
                    map_results.append({
                        "summary": f"Error processing chunk: {e}",
                        "decisions": [],
                        "actions": []
                    })
        
        return map_results
    
    def _process_map_chunk(
        self,
        chunk_text: str,
        prompt_template: str,
        temperature: float
    ) -> Dict[str, Any]:
        """
        Обрабатывает один чанк текста в рамках этапа MAP
        
        Args:
            chunk_text: Текст чанка
            prompt_template: Шаблон промпта
            temperature: Температура генерации
            
        Returns:
            Результат обработки чанка (структурированный JSON с ключами summary, decisions, actions, participants, agenda_items)
        """
        # Добавляем в промпт информацию о необходимости структурированного JSON
        schema_path = Path(__file__).parent.parent.parent / "utils" / "schemas" / "map_reduce_schema.json"
        schema_exists = schema_path.exists()
        
        enhanced_prompt = prompt_template
        if schema_exists:
            try:
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema = json.load(f)
                schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
                enhanced_prompt += f"\n\nYour response must follow this JSON schema:\n{schema_str}"
            except Exception as e:
                logger.error(f"Error loading schema: {e}")
        
        # Добавляем явное указание на необходимые поля
        enhanced_prompt += "\n\nYour response must include the following fields: summary, decisions, actions, participants, agenda_items."
        
        try:
            # Генерируем JSON на основе промпта
            result = self.llm_adapter.generate_json(
                prompt=chunk_text,
                system_message=enhanced_prompt,
                temperature=temperature
            )
            
            # Проверяем структуру результата
            if not isinstance(result, dict):
                logger.warning(f"MAP result is not a dictionary: {result}")
                return {
                    "summary": "Error: Invalid result format",
                    "decisions": [],
                    "actions": [],
                    "participants": [],
                    "agenda_items": []
                }
            
            # Убеждаемся, что все необходимые ключи присутствуют
            result.setdefault("summary", "")
            result.setdefault("decisions", [])
            result.setdefault("actions", [])
            result.setdefault("participants", [])
            result.setdefault("agenda_items", [])
            
            # Валидируем результат по схеме, если она существует
            if schema_exists:
                try:
                    from ...utils.schemas import validate_json_schema
                    errors = validate_json_schema(result, schema)
                    if errors:
                        logger.warning(f"MAP result does not match schema: {errors}")
                except Exception as e:
                    logger.error(f"Error validating schema: {e}")
            
            return result
            
        except LLMError as e:
            logger.error(f"LLM error during MAP stage: {e}")
            return {
                "summary": f"Error: {e}",
                "decisions": [],
                "actions": []
            }
        
        except Exception as e:
            logger.error(f"Unexpected error during MAP stage: {e}", exc_info=True)
            return {
                "summary": f"Error: {e}",
                "decisions": [],
                "actions": []
            }
    
    def _process_reduce_stage(
        self,
        map_results: List[Dict[str, Any]],
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Выполняет этап REDUCE: объединяет результаты MAP в структурированный JSON
        
        Args:
            map_results: Список результатов этапа MAP
            language: Язык обработки
            
        Returns:
            Структурированный JSON в соответствии с моделью Protocol
        """
        logger.info("Starting REDUCE stage")
        
        # Если результатов нет, возвращаем пустой результат
        if not map_results:
            logger.warning("No results to process in REDUCE stage")
            return {
                "summary": "",
                "decisions": [],
                "actions": [],
                "participants": [],
                "agenda_items": []
            }
        
        # Если результат всего один, дополняем его недостающими полями
        if len(map_results) == 1:
            logger.debug("Only one MAP result, enhancing with required fields")
            result = map_results[0].copy()
            result.setdefault("summary", "")
            result.setdefault("decisions", [])
            result.setdefault("actions", [])
            result.setdefault("participants", [])
            result.setdefault("agenda_items", [])
            return result
        
        # Выбираем шаблон промпта в зависимости от языка
        if language and language.lower() == "de" and self.reduce_prompt_template_de:
            prompt_template = self.reduce_prompt_template_de
        else:
            prompt_template = self.reduce_prompt_template
        
        # Добавляем в промпт информацию о необходимости структурированного JSON
        schema_path = Path(__file__).parent.parent.parent / "utils" / "schemas" / "map_reduce_schema.json"
        schema_exists = schema_path.exists()
        
        if schema_exists:
            try:
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema = json.load(f)
                schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
                prompt_template += f"\n\nYour response must follow this JSON schema:\n{schema_str}"
            except Exception as e:
                logger.error(f"Error loading schema: {e}")
        
        try:
            # Подготавливаем текст для промпта
            combined_summaries = "\n\n".join(
                f"Segment {i+1} Summary: {result.get('summary', '')}"
                for i, result in enumerate(map_results)
            )
            
            # Собираем все решения
            all_decisions = []
            for result in map_results:
                decisions = result.get("decisions", [])
                if isinstance(decisions, list):
                    all_decisions.extend(decisions)
            
            # Собираем все действия
            all_actions = []
            for result in map_results:
                actions = result.get("actions", [])
                if isinstance(actions, list):
                    all_actions.extend(actions)
            
            # Собираем всех участников
            all_participants = []
            for result in map_results:
                participants = result.get("participants", [])
                if isinstance(participants, list):
                    all_participants.extend(participants)
            
            # Собираем все пункты повестки
            all_agenda_items = []
            for result in map_results:
                agenda_items = result.get("agenda_items", [])
                if isinstance(agenda_items, list):
                    all_agenda_items.extend(agenda_items)
            
            # Формируем текст промпта
            reduce_input_text = (
                f"Combined Summaries:\n{combined_summaries}\n\n"
                f"Extracted Decisions:\n{json.dumps(all_decisions, indent=2, ensure_ascii=False)}\n\n"
                f"Extracted Actions:\n{json.dumps(all_actions, indent=2, ensure_ascii=False)}\n\n"
                f"Extracted Participants:\n{json.dumps(all_participants, indent=2, ensure_ascii=False)}\n\n"
                f"Extracted Agenda Items:\n{json.dumps(all_agenda_items, indent=2, ensure_ascii=False)}"
            )
            
            # Генерируем JSON на основе промпта
            result = self.llm_adapter.generate_json(
                prompt=reduce_input_text,
                system_message=prompt_template,
                temperature=self.reduce_temperature
            )
            
            # Проверяем структуру результата
            if not isinstance(result, dict):
                logger.warning(f"REDUCE result is not a dictionary: {result}")
                return {
                    "summary": "",
                    "decisions": [],
                    "actions": [],
                    "participants": [],
                    "agenda_items": []
                }
            
            # Убеждаемся, что все необходимые ключи присутствуют
            result.setdefault("summary", "")
            result.setdefault("decisions", [])
            result.setdefault("actions", [])
            result.setdefault("participants", [])
            result.setdefault("agenda_items", [])
            
            # Валидируем результат по схеме, если она существует
            if schema_exists:
                try:
                    from ...utils.schemas import validate_json_schema
                    errors = validate_json_schema(result, schema)
                    if errors:
                        logger.warning(f"REDUCE result does not match schema: {errors}")
                except Exception as e:
                    logger.error(f"Error validating schema: {e}")
            
            # Преобразуем actions в action_items для совместимости с моделью Protocol
            if "actions" in result and "action_items" not in result:
                result["action_items"] = result.pop("actions")
            
            return result
            
        except LLMError as e:
            logger.error(f"LLM error during REDUCE stage: {e}")
            return {
                "decisions": [f"Error during REDUCE: {e}"],
                "actions": []
            }
        
        except Exception as e:
            logger.error(f"Unexpected error during REDUCE stage: {e}", exc_info=True)
            return {
                "decisions": [f"Error during REDUCE: {e}"],
                "actions": []
            }
    
    def _process_refine_stage(
        self,
        reduced_data: Dict[str, Any],
        meeting_info: Dict[str, Any],
        language: str = "en"
    ) -> Tuple[Protocol, str]:
        """
        Выполняет этап REFINE: генерирует финальный протокол
        
        Args:
            reduced_data: Результат этапа REDUCE
            meeting_info: Информация о встрече
            language: Язык обработки
            
        Returns:
            Кортеж из объекта Protocol и сгенерированного Markdown-текста
        """
        logger.info("Starting REFINE stage")
        
        # Выбираем шаблон промпта в зависимости от языка
        if language.lower() == "de" and self.refine_prompt_template_de:
            prompt_template = self.refine_prompt_template_de
        else:
            prompt_template = self.refine_prompt_template
        
        try:
            # Подготавливаем данные для промпта
            meeting_title = meeting_info.get("title", "Meeting Protocol")
            meeting_date = meeting_info.get("date", time.strftime("%Y-%m-%d"))
            
            # Подготавливаем список участников
            participants_list = []
            if "participants" in meeting_info:
                if isinstance(meeting_info["participants"], list):
                    participants_list = meeting_info["participants"]
                elif isinstance(meeting_info["participants"], dict):
                    if "present" in meeting_info["participants"]:
                        participants_list = meeting_info["participants"]["present"]
            
            participants_str = "\n".join(
                f"- {p}" if isinstance(p, str) else f"- {p.get('name', 'Unknown')} ({p.get('role', 'Participant')})"
                for p in participants_list
            )
            if not participants_str:
                participants_str = "- (No participants listed)"
            
            # Подготавливаем повестку
            agenda_list = meeting_info.get("agenda", [])
            agenda_str = "\n".join(
                f"{i+1}. {item}" for i, item in enumerate(agenda_list)
            )
            if not agenda_str:
                agenda_str = "- (No agenda items listed)"
            
            # Подготавливаем решения
            decisions = reduced_data.get("decisions", [])
            decisions_str = "\n".join(
                f"- {d}" if isinstance(d, str) else f"- {d.get('description', d)}"
                for d in decisions
            )
            if not decisions_str:
                decisions_str = "- (No decisions recorded)"
            
            # Подготавливаем действия
            actions = reduced_data.get("actions", [])
            actions_str = "\n".join(
                f"- Task: {a.get('what', 'N/A')}, Assigned to: {a.get('who', 'N/A')}, Due: {a.get('due', 'N/A')}"
                for a in actions
            )
            if not actions_str:
                actions_str = "- (No action items recorded)"
            
            # Заполняем шаблон промпта
            refine_prompt = prompt_template.replace("{{title}}", meeting_title)
            refine_prompt = refine_prompt.replace("{{date}}", meeting_date)
            refine_prompt = refine_prompt.replace("{{participants}}", participants_str)
            refine_prompt = refine_prompt.replace("{{agenda}}", agenda_str)
            refine_prompt = refine_prompt.replace("{{decisions}}", decisions_str)
            refine_prompt = refine_prompt.replace("{{actions}}", actions_str)
            
            # Генерируем JSON на основе промпта
            try:
                logger.debug(f"Generating JSON with prompt: {refine_prompt[:100]}...")
                logger.debug(f"Using language: {language}")
                logger.debug(f"Using template: refine_{language}.txt")
                
                # Добавляем системное сообщение для улучшения генерации JSON
                system_message = """You are a meeting protocol generator. 
                Your task is to generate a well-structured JSON object according to the specified format.
                The JSON must include the following keys: metadata, participants, agenda_items, summary, decisions, action_items.
                Ensure that all dates are in YYYY-MM-DD format and that the JSON is valid."""
                
                json_result = self.llm_adapter.generate_json(
                    prompt=refine_prompt,
                    system_message=system_message,
                    temperature=self.refine_temperature
                )
                
                # Подробное логирование сгенерированного JSON
                logger.debug(f"Generated JSON result type: {type(json_result)}")
                if isinstance(json_result, dict):
                    logger.debug(f"Generated JSON keys: {json_result.keys()}")
                    for key, value in json_result.items():
                        logger.debug(f"Key: {key}, Value type: {type(value)}, Value: {value}")
                else:
                    logger.debug(f"Generated JSON result is not a dict: {json_result}")
                
                # Проверяем наличие необходимых полей в JSON
                required_keys = ['metadata', 'participants', 'agenda_items', 'summary', 'decisions', 'action_items']
                missing_keys = [key for key in required_keys if key not in json_result]
                if missing_keys:
                    logger.warning(f"Missing required keys in generated JSON: {missing_keys}")
                    # Добавляем отсутствующие ключи
                    for key in missing_keys:
                        if key == 'metadata':
                            json_result[key] = meeting_info or {}
                        elif key in ['participants', 'agenda_items', 'decisions', 'action_items']:
                            json_result[key] = []
                        elif key == 'summary':
                            json_result[key] = "No summary generated"
                
                # Преобразуем JSON в объект Protocol
                protocol = Protocol.from_dict(json_result)
                logger.debug(f"Created protocol object: {protocol.metadata}")
                
                # Генерируем Markdown
                markdown = self._generate_markdown(protocol)
                logger.debug(f"Generated markdown: {markdown[:100]}...")
                
                return protocol, markdown
            except Exception as e:
                logger.error(f"Error in _process_refine_stage: {e}", exc_info=True)
                # Создаем пустой протокол с информацией об ошибке
                error_protocol = Protocol(
                    metadata=meeting_info,
                    summary=f"Failed to generate protocol content due to error: {e}",
                    decisions=[],
                    action_items=[],
                    participants=[],
                    agenda_items=[]
                )
                error_markdown = self._generate_error_markdown(error_protocol, str(e))
                return error_protocol, error_markdown
            
        except LLMError as e:
            logger.error(f"LLM error during REFINE stage: {e}")
            # Создаем минимальный протокол с ошибкой
            error_protocol = Protocol(
                metadata={
                    "title": meeting_info.get("title", "Meeting Protocol"),
                    "date": meeting_info.get("date", time.strftime("%Y-%m-%d")),
                    "error": f"Error during REFINE: {e}"
                },
                participants=[],
                agenda_items=[],
                summary=f"Failed to generate protocol due to error: {e}",
                decisions=[Decision(description=d) for d in reduced_data.get("decisions", [])],
                action_items=[ActionItem.from_dict(a) for a in reduced_data.get("actions", [])]
            )
            
            # Генерируем базовый Markdown с ошибкой
            error_markdown = self._generate_error_markdown(error_protocol, str(e))
            
            return error_protocol, error_markdown
        
        except Exception as e:
            logger.error(f"Unexpected error during REFINE stage: {e}", exc_info=True)
            # Создаем минимальный протокол с ошибкой
            error_protocol = Protocol(
                metadata={
                    "title": meeting_info.get("title", "Meeting Protocol"),
                    "date": meeting_info.get("date", time.strftime("%Y-%m-%d")),
                    "error": f"Unexpected error during REFINE: {e}"
                },
                participants=[],
                agenda_items=[],
                summary=f"Failed to generate protocol due to error: {e}",
                decisions=[Decision(description=d) for d in reduced_data.get("decisions", [])],
                action_items=[ActionItem.from_dict(a) for a in reduced_data.get("actions", [])]
            )
            
            # Генерируем базовый Markdown с ошибкой
            error_markdown = self._generate_error_markdown(error_protocol, str(e))
            
            return error_protocol, error_markdown
    
    def _generate_markdown(self, protocol: Protocol) -> str:
        """
        Генерирует Markdown на основе объекта Protocol
        
        Args:
            protocol: Объект Protocol
            
        Returns:
            Сгенерированный Markdown-текст
        """
        md_parts = []
        
        # Заголовок и метаданные
        md_parts.append(f"# {protocol.metadata.get('title', 'Meeting Protocol')}")
        md_parts.append(f"**Date:** {protocol.metadata.get('date', 'N/A')}")
        md_parts.append(f"**Location:** {protocol.metadata.get('location', 'N/A')}")
        md_parts.append(f"**Organizer:** {protocol.metadata.get('organizer', 'N/A')}")
        md_parts.append("")
        
        # Участники
        md_parts.append("## Participants")
        for p in protocol.participants:
            if p.role:
                md_parts.append(f"- {p.name} ({p.role})")
            else:
                md_parts.append(f"- {p.name}")
        
        if not protocol.participants:
            md_parts.append("- None listed")
        
        md_parts.append("")
        
        # Общее резюме
        md_parts.append("## Summary")
        md_parts.append(protocol.summary)
        md_parts.append("")
        
        # Пункты повестки
        md_parts.append("## Agenda Items")
        
        for item in protocol.agenda_items:
            md_parts.append(f"### {item.topic}")
            md_parts.append(f"**Discussion Summary:** {item.discussion_summary}")
            
            if item.decisions_made:
                md_parts.append("**Decisions:**")
                for d in item.decisions_made:
                    if isinstance(d, Decision):
                        md_parts.append(f"- {d.description}")
                    else:
                        md_parts.append(f"- {d}")
            
            if item.action_items_assigned:
                md_parts.append("**Action Items:**")
                for a in item.action_items_assigned:
                    due_date = f", Due: {a.due}" if a.due else ""
                    md_parts.append(f"- {a.what} (Assigned to: {a.who}{due_date})")
            
            md_parts.append("")
        
        if not protocol.agenda_items:
            md_parts.append("No agenda items listed")
            md_parts.append("")
        
        # Глобальные решения
        md_parts.append("## Decisions")
        for d in protocol.decisions:
            md_id = f" (ID: {d.id})" if d.id else ""
            md_parts.append(f"- {d.description}{md_id}")
        
        if not protocol.decisions:
            md_parts.append("- None recorded")
        
        md_parts.append("")
        
        # Глобальные задачи
        md_parts.append("## Action Items")
        for a in protocol.action_items:
            due_date = f", Due: {a.due_date}" if a.due_date else ""
            status = f", Status: {a.status}" if a.status else ""
            id_str = f", ID: {a.action_id}" if a.action_id else ""
            md_parts.append(f"- {a.description} (Assigned to: {a.assigned_to}{due_date}{status}{id_str})")
        
        if not protocol.action_items:
            md_parts.append("- None recorded")
        
        # Добавляем сообщение об ошибке, если она есть
        if "error" in protocol.metadata:
            md_parts.append("\n## Errors")
            md_parts.append(f"- {protocol.metadata['error']}")
        
        return "\n\n".join(md_parts)
    
    def _generate_error_markdown(self, protocol: Protocol, error_message: str) -> str:
        """
        Генерирует Markdown с ошибкой
        
        Args:
            protocol: Объект Protocol
            error_message: Сообщение об ошибке
            
        Returns:
            Сгенерированный Markdown-текст
        """
        md_parts = []
        
        # Заголовок и метаданные
        md_parts.append(f"# {protocol.metadata.get('title', 'Meeting Protocol')} - ERROR")
        md_parts.append(f"**Date:** {protocol.metadata.get('date', 'N/A')}")
        md_parts.append("")
        
        # Сообщение об ошибке
        md_parts.append("## Error")
        md_parts.append(f"**{error_message}**")
        md_parts.append("")
        md_parts.append("The protocol generation encountered an error. Only the extracted decisions and action items are available.")
        md_parts.append("")
        
        # Решения
        md_parts.append("## Extracted Decisions")
        for d in protocol.decisions:
            md_parts.append(f"- {d.description}")
        
        if not protocol.decisions:
            md_parts.append("- None extracted")
        
        md_parts.append("")
        
        # Задачи
        md_parts.append("## Extracted Action Items")
        for a in protocol.action_items:
            due_date = f", Due: {a.due}" if a.due else ""
            md_parts.append(f"- {a.what} (Assigned to: {a.who}{due_date})")
        
        if not protocol.action_items:
            md_parts.append("- None extracted")
        
        return "\n\n".join(md_parts)
    
    def _generate_text_with_caching(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.3,
        **kwargs
    ) -> str:
        """
        Генерирует текст с использованием кэширования
        
        Args:
            prompt: Промпт для генерации
            system_message: Системное сообщение
            temperature: Температура для LLM
            **kwargs: Дополнительные параметры для LLM
            
        Returns:
            Сгенерированный текст
            
        Raises:
            LLMError: Если произошла ошибка при генерации текста
        """
        if not self.use_caching:
            # Если кэширование отключено, просто вызываем LLM
            return self.llm_adapter.generate_text(
                prompt=prompt,
                system_message=system_message,
                temperature=temperature,
                **kwargs
            )
        
        # Генерируем ключ кэша
        cache_key = self._generate_cache_key(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature,
            output_type="text",
            **kwargs
        )
        
        # Проверяем кэш в памяти
        if cache_key in self.cache:
            logger.debug(f"Cache hit (memory): {cache_key[:10]}...")
            return self.cache[cache_key]
        
        # Проверяем кэш на диске
        cache_file = self.cache_dir / f"{cache_key}.txt"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    result = f.read()
                    
                # Добавляем в кэш в памяти
                self.cache[cache_key] = result
                
                logger.debug(f"Cache hit (disk): {cache_key[:10]}...")
                return result
            except Exception as e:
                logger.warning(f"Error reading cache file: {e}", exc_info=True)
        
        # Если кэш не найден, генерируем текст
        logger.debug(f"Cache miss: {cache_key[:10]}...")
        
        result = self.llm_adapter.generate_text(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature,
            **kwargs
        )
        
        # Сохраняем в кэш
        self.cache[cache_key] = result
        
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(result)
            logger.debug(f"Saved to cache: {cache_key[:10]}...")
        except Exception as e:
            logger.warning(f"Error writing to cache file: {e}", exc_info=True)
        
        return result
    
    def _generate_json_with_caching(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.3,
        schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Генерирует JSON с использованием кэширования
        
        Args:
            prompt: Промпт для генерации
            system_message: Системное сообщение
            temperature: Температура для LLM
            schema: Схема JSON для валидации
            **kwargs: Дополнительные параметры для LLM
            
        Returns:
            Сгенерированный JSON
            
        Raises:
            LLMError: Если произошла ошибка при генерации JSON
        """
        if not self.use_caching:
            # Если кэширование отключено, просто вызываем LLM
            return self.llm_adapter.generate_json(
                prompt=prompt,
                system_message=system_message,
                temperature=temperature,
                schema=schema,
                **kwargs
            )
        
        # Генерируем ключ кэша
        cache_key = self._generate_cache_key(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature,
            schema=schema,
            output_type="json",
            **kwargs
        )
        
        # Проверяем кэш в памяти
        if cache_key in self.cache:
            logger.debug(f"Cache hit (memory): {cache_key[:10]}...")
            return self.cache[cache_key]
        
        # Проверяем кэш на диске
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    result = json.load(f)
                    
                # Добавляем в кэш в памяти
                self.cache[cache_key] = result
                
                logger.debug(f"Cache hit (disk): {cache_key[:10]}...")
                return result
            except Exception as e:
                logger.warning(f"Error reading cache file: {e}", exc_info=True)
        
        # Если кэш не найден, генерируем JSON
        logger.debug(f"Cache miss: {cache_key[:10]}...")
        
        result = self.llm_adapter.generate_json(
            prompt=prompt,
            system_message=system_message,
            temperature=temperature,
            schema=schema,
            **kwargs
        )
        
        # Сохраняем в кэш
        self.cache[cache_key] = result
        
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.debug(f"Saved to cache: {cache_key[:10]}...")
        except Exception as e:
            logger.warning(f"Error writing to cache file: {e}", exc_info=True)
        
        return result
    
    def _generate_cache_key(self, **kwargs) -> str:
        """
        Генерирует ключ кэша на основе параметров запроса
        
        Args:
            **kwargs: Параметры запроса
            
        Returns:
            Строка, представляющая ключ кэша
        """
        # Сериализуем параметры в JSON
        cache_data = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
        
        # Генерируем хеш на основе сериализованных параметров
        return hashlib.md5(cache_data.encode("utf-8")).hexdigest()
    
    def clear_cache(self) -> None:
        """
        Очищает кэш
        """
        self.cache = {}
        
        if self.use_caching:
            # Удаляем файлы кэша
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.warning(f"Error deleting cache file {cache_file}: {e}")
            
            for cache_file in self.cache_dir.glob("*.txt"):
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.warning(f"Error deleting cache file {cache_file}: {e}")
            
            logger.info(f"Cache cleared")
