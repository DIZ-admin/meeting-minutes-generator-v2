"""
Основной конвейер для генерации протоколов совещаний
"""
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union, Callable

# Импортируем модуль преобразования транскриптов
from app.core.utils.transcript_converter import convert_plain_text_to_transcript

from ...core.services.asr_service import ASRService
from ...core.services.analysis_service import MapReduceService 
from ...core.services.protocol_service import ProtocolService
from ...core.services.notification_service import NotificationService
from ...core.models.transcript import Transcript, TranscriptSegment
from ...core.models.protocol import Protocol
from ...core.exceptions import ASRError, LLMError, NotificationError, ConfigError, ValidationError, FileProcessingError
from ...utils.logging import get_default_logger
from ...utils.metrics import track_file_processed, track_processing_time, monitor_processing_time
from ...config.config import config

logger = get_default_logger(__name__)

class Pipeline:
    """
    Основной конвейер для генерации протоколов совещаний
    
    Этот класс объединяет все этапы обработки: распознавание речи,
    обработку текста, генерацию протоколов и отправку уведомлений.
    """
    
    def __init__(
        self,
        asr_service: Optional[ASRService] = None,
        analysis_service: Optional[MapReduceService] = None,
        protocol_service: Optional[ProtocolService] = None,
        notification_service: Optional[NotificationService] = None
    ):
        """
        Инициализирует конвейер для генерации протоколов
        
        Args:
            asr_service: Сервис для распознавания речи
            analysis_service: Сервис для анализа текста
            protocol_service: Сервис для генерации протоколов
            notification_service: Сервис для отправки уведомлений
            
        Raises:
            ConfigError: Если не удалось создать сервисы по умолчанию
        """
        # Инициализируем сервисы
        try:
            self.asr_service = asr_service or ASRService()
            logger.debug("ASR service initialized")
        except ConfigError as e:
            error_msg = f"Failed to initialize ASR service: {e}"
            logger.error(error_msg)
            raise ConfigError(error_msg) from e
        
        try:
            self.analysis_service = analysis_service or MapReduceService()
            logger.debug("Analysis service initialized")
        except ConfigError as e:
            error_msg = f"Failed to initialize analysis service: {e}"
            logger.error(error_msg)
            raise ConfigError(error_msg) from e
        
        try:
            self.protocol_service = protocol_service or ProtocolService(map_reduce_service=self.analysis_service)
            logger.debug("Protocol service initialized")
        except ConfigError as e:
            error_msg = f"Failed to initialize protocol service: {e}"
            logger.error(error_msg)
            raise ConfigError(error_msg) from e
        
        try:
            self.notification_service = notification_service or NotificationService()
            logger.debug("Notification service initialized")
        except ConfigError as e:
            # Для уведомлений ошибка не критична, просто логируем
            logger.warning(f"Failed to initialize notification service: {e}")
            self.notification_service = None
        
        logger.info("Pipeline initialized successfully")
    
    @monitor_processing_time("full_pipeline")
    def process_audio(
        self,
        audio_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        language: Optional[str] = None,
        meeting_info: Optional[Dict[str, Any]] = None,
        skip_notifications: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Tuple[Path, Path]:
        """
        Обрабатывает аудиофайл для генерации протокола
        
        Args:
            audio_path: Путь к аудиофайлу
            output_dir: Директория для сохранения результатов
                       (если None, создается автоматически)
            language: Язык аудио (например, 'de', 'en')
            meeting_info: Дополнительная информация о встрече
            skip_notifications: Пропустить отправку уведомлений
            progress_callback: Функция обратного вызова для отслеживания прогресса
                              принимает два аргумента: строку с описанием этапа и число от 0 до 1
            
        Returns:
            Кортеж из путей к файлам протокола (markdown, json)
            
        Raises:
            FileNotFoundError: Если аудиофайл не найден
            ASRError: Если произошла ошибка при распознавании речи
            LLMError: Если произошла ошибка при обработке текста
            ValidationError: Если произошла ошибка при валидации результата
        """
        start_time = time.time()
        logger.info(f"Starting audio processing pipeline for {audio_path}")
        
        # Вызываем callback с начальным статусом, если он предоставлен
        if progress_callback:
            progress_callback("Инициализация", 0.01)
        
        # Преобразуем пути в объекты Path
        audio_path = Path(audio_path)
        
        # Проверяем существование аудиофайла
        if not audio_path.exists():
            error_msg = f"Audio file not found: {audio_path}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback("Ошибка: файл не найден", 0.0)
            raise FileNotFoundError(error_msg)
        
        # Создаем директорию для выходных файлов
        if output_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = config.output_dir / f"{audio_path.stem}_{timestamp}"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Output directory created: {output_dir}")
        
        # Если meeting_info не передано, создаем его из имени файла
        if meeting_info is None:
            meeting_info = self._extract_meeting_info(audio_path.stem)
        
        # Язык по умолчанию
        if language is None:
            language = config.default_lang
            logger.debug(f"Using default language: {language}")
        
        try:
            # 1. Распознавание речи (ASR)
            logger.info("Step 1: Starting audio transcription")
            if progress_callback:
                progress_callback("Транскрибация аудио", 0.1)
            
            transcript_segments = self.asr_service.transcribe(audio_path, language)
            logger.info(f"Transcription complete: {len(transcript_segments)} segments")
            
            if progress_callback:
                progress_callback("Транскрипция завершена", 0.3)
            
            # Сохраняем сырую транскрипцию для отладки
            transcript_path = output_dir / "transcript.json"
            with open(transcript_path, "w", encoding="utf-8") as f:
                json.dump(transcript_segments, f, ensure_ascii=False, indent=2)
            
            # 2. Обработка текста (Map-Reduce-Refine)
            logger.info("Step 2: Starting transcript analysis")
            if progress_callback:
                progress_callback("Анализ транскрипта", 0.4)
            
            protocol, markdown = self.analysis_service.process_transcript(
                transcript_segments,
                meeting_info=meeting_info,
                language=language
            )
            logger.info("Analysis complete")
            
            if progress_callback:
                progress_callback("Анализ завершен", 0.6)
            
            # 3. Сохранение результатов
            logger.info("Step 3: Saving results")
            if progress_callback:
                progress_callback("Генерация протокола", 0.7)
            
            # Определяем имя файла на основе заголовка протокола и даты
            date_str = protocol.metadata.get('date', datetime.now().strftime("%Y-%m-%d"))
            title_safe = protocol.metadata.get('title', 'meeting_protocol')
            # Очищаем заголовок от недопустимых символов для имени файла
            title_safe = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in title_safe)
            title_safe = title_safe.replace(' ', '_')[:50]  # Ограничиваем длину
            
            base_filename = f"{date_str}_{title_safe}"
            
            # Сохраняем протокол в формате Markdown
            md_file = output_dir / f"{base_filename}.md"
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(markdown)
            logger.info(f"Markdown protocol saved to: {md_file}")
            
            # Сохраняем протокол в формате JSON
            json_file = output_dir / f"{base_filename}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(protocol.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info(f"JSON protocol saved to: {json_file}")
            
            # Создаем файл протокола в формате EGL JSON (если язык немецкий)
            if language and language.lower() == "de":
                egl_json_file = output_dir / f"{base_filename}_egl.json"
                with open(egl_json_file, "w", encoding="utf-8") as f:
                    json.dump(protocol.to_egl_json(), f, ensure_ascii=False, indent=2)
                logger.info(f"EGL JSON protocol saved to: {egl_json_file}")
            
            # 4. Отправка уведомлений
            if not skip_notifications and self.notification_service and self.notification_service.is_enabled():
                logger.info("Step 4: Sending notifications")
                if progress_callback:
                    progress_callback("Отправка уведомлений", 0.9)
                
                notification_success = self.notification_service.send_protocol_files(
                    md_path=md_file,
                    json_path=json_file
                )
                
                if notification_success:
                    logger.info("Notifications sent successfully")
                else:
                    logger.warning("Failed to send notifications")
            else:
                logger.info("Notifications skipped")
            
            # Завершаем и логируем время выполнения
            end_time = time.time()
            processing_time = end_time - start_time
            logger.info(f"Processing completed in {processing_time:.2f} seconds")
            
            # Отслеживаем успешную обработку
            file_extension = audio_path.suffix.lower() if hasattr(audio_path, 'suffix') else ".unknown"
            track_file_processed(
                language=language or "unknown",
                file_type=file_extension,
                status="success"
            )
            
            if progress_callback:
                progress_callback("Завершено", 1.0)
            
            return md_file, json_file
            
        except ASRError as e:
            logger.error(f"ASR error: {e}")
            
            # Отслеживаем ошибку обработки
            file_extension = audio_path.suffix.lower() if hasattr(audio_path, 'suffix') else ".unknown"
            track_file_processed(
                language=language or "unknown",
                file_type=file_extension,
                status="asr_error"
            )
            
            # Записываем информацию об ошибке в отдельный файл
            error_file = output_dir / "error.log"
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(f"ASR error: {e}\n")
                if hasattr(e, "details"):
                    f.write(f"Details: {json.dumps(e.details, ensure_ascii=False, indent=2)}\n")
            
            # Уведомляем о прогрессе, если есть callback
            if progress_callback:
                progress_callback(f"Ошибка распознавания речи: {e}", 0.0)
            
            # Продолжаем пробрасывать исключение
            raise
            
        except LLMError as e:
            logger.error(f"LLM error: {e}")
            
            # Отслеживаем ошибку LLM
            file_extension = audio_path.suffix.lower() if hasattr(audio_path, 'suffix') else ".unknown"  
            track_file_processed(
                language=language or "unknown",
                file_type=file_extension,
                status="llm_error"
            )
            
            # Записываем информацию об ошибке в отдельный файл
            error_file = output_dir / "error.log"
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(f"LLM error: {e}\n")
                if hasattr(e, "details"):
                    f.write(f"Details: {json.dumps(e.details, ensure_ascii=False, indent=2)}\n")
            
            # Уведомляем о прогрессе, если есть callback
            if progress_callback:
                progress_callback(f"Ошибка обработки текста: {e}", 0.0)
            
            # Продолжаем пробрасывать исключение
            raise
            
        except Exception as e:
            logger.error(f"Unexpected error during processing: {e}", exc_info=True)
            # Записываем информацию об ошибке в отдельный файл
            error_file = output_dir / "error.log"
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(f"Unexpected error: {e}\n")
            
            # Уведомляем о прогрессе, если есть callback
            if progress_callback:
                progress_callback(f"Непредвиденная ошибка: {e}", 0.0)
            
            # Продолжаем пробрасывать исключение
            raise
    
    def _extract_metadata_and_language(self, data: Dict[str, Any], lang: Optional[str], info: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Извлекает метаданные и язык из JSON-данных
        
        Args:
            data: JSON-данные
            lang: Текущий язык (может быть None)
            info: Текущие метаданные (могут быть None)
            
        Returns:
            Кортеж из языка и метаданных
        """
        extracted_lang = None
        extracted_info = info
        
        # Если есть поле 'language', используем его
        if 'language' in data and data['language'] and not lang:
            extracted_lang = data['language']
            logger.debug(f"Using language from transcript: {extracted_lang}")
        
        # Если есть метаданные, добавляем их в meeting_info
        if 'metadata' in data and isinstance(data['metadata'], dict):
            if extracted_info is None:
                extracted_info = {}
            extracted_info.update(data['metadata'])
            logger.debug(f"Using metadata from transcript: {data['metadata']}")
        
        return extracted_lang, extracted_info
    
    def _extract_replicate_metadata(self, data: Dict[str, Any], info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Извлекает метаданные из формата Replicate API
        
        Args:
            data: JSON-данные от Replicate API
            info: Текущие метаданные
            
        Returns:
            Обновленные метаданные
        """
        extracted_info = info or {}
        
        # Добавляем информацию о модели и времени обработки
        if 'created_at' in data:
            extracted_info['processed_at'] = data['created_at']
        
        if 'completed_at' in data:
            extracted_info['completed_at'] = data['completed_at']
            
        if 'id' in data:
            extracted_info['replicate_id'] = data['id']
            
        # Добавляем параметры входа
        if 'input' in data and isinstance(data['input'], dict):
            input_params = data['input']
            if 'num_speakers' in input_params:
                extracted_info['num_speakers'] = input_params['num_speakers']
            if 'language' in input_params:
                extracted_info['detected_language'] = input_params['language']
            if 'prompt' in input_params:
                extracted_info['processing_prompt'] = input_params['prompt']
        
        logger.debug(f"Extracted Replicate metadata: {extracted_info}")
        return extracted_info
    
    def _normalize_speaker_name(self, speaker_name: str) -> str:
        """
        Нормализует имена спикеров к единому формату
        
        Args:
            speaker_name: Исходное имя спикера (например, 'SPEAKER_04')
            
        Returns:
            Нормализованное имя спикера (например, 'speaker_4')
        """
        if not speaker_name:
            return "speaker_0"
            
        # Преобразуем SPEAKER_XX в speaker_x
        if speaker_name.startswith('SPEAKER_'):
            try:
                num = speaker_name.split('_')[1]
                # Удаляем ведущие нули и преобразуем в число
                normalized_num = str(int(num))
                result = f"speaker_{normalized_num}"
                logger.debug(f"Normalized speaker name: {speaker_name} -> {result}")
                return result
            except (IndexError, ValueError):
                logger.warning(f"Could not normalize speaker name: {speaker_name}")
                return speaker_name.lower()
        
        # Для других форматов просто приводим к нижнему регистру
        return speaker_name.lower()
    
    def _extract_metadata(self, filename: str) -> Dict[str, Any]:
        """
        Извлекает метаданные протокола из имени файла
        
        Args:
            filename: Имя файла без расширения
            
        Returns:
            Словарь с метаданными протокола
        """
        # Базовые метаданные
        metadata = {
            "title": "Meeting Protocol",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "location": "Online Meeting",
            "organizer": "",
            "author": "AI Assistant"
        }
        
        # Пытаемся извлечь дату из имени файла (формат "meeting_2025-06-01" или "eGL_2025-06-01")
        import re
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
        if date_match:
            metadata["date"] = date_match.group(1)
        
        # Пытаемся извлечь название из имени файла
        # Удаляем дату и специальные символы, преобразуем подчеркивания в пробелы
        title = filename
        if date_match:
            title = title.replace(date_match.group(1), "")
        
        # Удаляем специальные символы и лишние пробелы
        title = re.sub(r'[^\w\s]', ' ', title)
        title = re.sub(r'_', ' ', title)
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Если название не пустое, используем его
        if title:
            metadata["title"] = title.title()  # Преобразуем в Title Case
        
        return metadata
    
    def _create_transcript(
        self, 
        segments: List[Dict[str, Any]], 
        audio_path: Path, 
        language: str
    ) -> Transcript:
        """
        Создает объект Transcript из сегментов транскрипции
        
        Args:
            segments: Список сегментов транскрипции
            audio_path: Путь к аудиофайлу
            language: Язык транскрипции
            
        Returns:
            Объект Transcript
        """
        # Преобразуем сегменты в TranscriptSegment
        transcript_segments = []
        for i, segment in enumerate(segments):
            transcript_segments.append(TranscriptSegment(
                text=segment.get("text", ""),
                start=segment.get("start", 0.0),
                end=segment.get("end", 0.0),
                speaker=segment.get("speaker_id", segment.get("speaker", "UNKNOWN")),
                speaker_confidence=segment.get("speaker_confidence", 1.0),
                id=str(i)
            ))
        
        # Создаем объект Transcript
        return Transcript(
            segments=transcript_segments,
            audio_path=str(audio_path),
            language=language,
            metadata={
                "asr_adapter": getattr(self.asr_service.adapter, "get_adapter_info", lambda: {})()  
            }
        )
        
    def _generate_markdown_from_protocol(self, protocol: Protocol) -> str:
        """
        Генерирует Markdown-представление протокола
        
        Args:
            protocol: Протокол
            
        Returns:
            Строка в формате Markdown
        """
        md_lines = []
        
        # Заголовок
        md_lines.append(f"# {protocol.metadata.get('title', 'Meeting Protocol')}")
        md_lines.append('')
        
        # Метаданные
        md_lines.append('## Metadata')
        date_str = protocol.metadata.get('date', datetime.now().strftime("%Y-%m-%d"))
        md_lines.append(f'- **Date:** {date_str}')
        
        if 'location' in protocol.metadata and protocol.metadata['location']:
            md_lines.append(f'- **Location:** {protocol.metadata["location"]}')
        
        if 'organizer' in protocol.metadata and protocol.metadata['organizer']:
            md_lines.append(f'- **Organizer:** {protocol.metadata["organizer"]}')
        
        md_lines.append('')
        
        # Участники
        if hasattr(protocol, 'participants') and protocol.participants:
            md_lines.append('## Participants')
            md_lines.append('')
            for participant in protocol.participants:
                if isinstance(participant, dict):
                    name = participant.get('name', '')
                    role = participant.get('role', '')
                    if role:
                        md_lines.append(f'- {name} ({role})')
                    else:
                        md_lines.append(f'- {name}')
                else:
                    md_lines.append(f'- {participant}')
            md_lines.append('')
        
        # Повестка
        if hasattr(protocol, 'agenda_items') and protocol.agenda_items:
            md_lines.append('## Agenda Items')
            md_lines.append('')
            for item in protocol.agenda_items:
                if isinstance(item, dict):
                    md_lines.append(f'- {item.get("topic", "")}')
                else:
                    md_lines.append(f'- {item}')
            md_lines.append('')
        
        # Резюме
        md_lines.append('## Summary')
        md_lines.append('')
        md_lines.append(protocol.summary)
        md_lines.append('')
        
        # Решения
        if hasattr(protocol, 'decisions') and protocol.decisions:
            md_lines.append('## Decisions')
            for i, decision in enumerate(protocol.decisions, 1):
                md_lines.append(f'### Decision {i}')
                if isinstance(decision, dict):
                    md_lines.append(decision.get('decision', ''))
                    context = decision.get('context', '')
                    if context:
                        md_lines.append(f'*Context:* {context}')
                else:
                    md_lines.append(str(decision))
                md_lines.append('')
        
        # Задачи
        if hasattr(protocol, 'action_items') and protocol.action_items:
            md_lines.append('## Action Items')
            for i, action in enumerate(protocol.action_items, 1):
                md_lines.append(f'### Action {i}')
                if isinstance(action, dict):
                    md_lines.append(action.get('action', ''))
                    assignee = action.get('assignee', '')
                    if assignee:
                        md_lines.append(f'*Assignee:* {assignee}')
                    due_date = action.get('due_date', '')
                    if due_date:
                        md_lines.append(f'*Due Date:* {due_date}')
                else:
                    md_lines.append(str(action))
                md_lines.append('')
        
        return '\n'.join(md_lines)
        """
        Генерирует Markdown-представление протокола
        
        Args:
            protocol: Объект Protocol
            
        Returns:
            Строка с Markdown-представлением протокола
        """
        md_lines = []
        
        # Заголовок
        title = protocol.metadata.get('title', 'Meeting Protocol')
        md_lines.append(f'# {title}\n')
        
        # Метаданные
        md_lines.append('## Metadata')
        date = protocol.metadata.get('date', '')
        if date:
            md_lines.append(f'- **Date:** {date}')
            
        location = protocol.metadata.get('location', '')
        if location:
            md_lines.append(f'- **Location:** {location}')
            
        organizer = protocol.metadata.get('organizer', '')
        if organizer:
            md_lines.append(f'- **Organizer:** {organizer}')
            
        participants = protocol.metadata.get('participants', [])
        if participants:
            md_lines.append('- **Participants:**')
            for participant in participants:
                md_lines.append(f'  - {participant}')
        md_lines.append('')
        
        # Резюме
        md_lines.append('## Summary')
        md_lines.append(protocol.summary)
        md_lines.append('')
        
        # Решения
        if hasattr(protocol, 'decisions') and protocol.decisions:
            md_lines.append('## Decisions')
            for i, decision in enumerate(protocol.decisions, 1):
                md_lines.append(f'### Decision {i}')
                md_lines.append(decision.get('decision', ''))
                context = decision.get('context', '')
                if context:
                    md_lines.append(f'*Context:* {context}')
                md_lines.append('')
        
        # Задачи
        if hasattr(protocol, 'action_items') and protocol.action_items:
            md_lines.append('## Action Items')
            for i, action in enumerate(protocol.action_items, 1):
                md_lines.append(f'### Action {i}')
                md_lines.append(action.get('action', ''))
                
                assignee = action.get('assignee', '')
                if assignee:
                    md_lines.append(f'*Assignee:* {assignee}')
                    
                due_date = action.get('due_date', '')
                if due_date:
                    md_lines.append(f'*Due Date:* {due_date}')
                    
                context = action.get('context', '')
                if context:
                    md_lines.append(f'*Context:* {context}')
                md_lines.append('')
        
        return '\n'.join(md_lines)
    
    def process_batch(
        self,
        audio_files: List[Union[str, Path]],
        output_dir: Optional[Union[str, Path]] = None,
        language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        skip_notifications: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> List[Tuple[Path, Path]]:
        """
        Обрабатывает пакет аудиофайлов
        
        Args:
            audio_files: Список путей к аудиофайлам
            output_dir: Базовая директория для сохранения результатов
                       (если None, используется директория по умолчанию)
            language: Язык аудио (например, 'de', 'en')
            metadata: Метаданные для всех протоколов
            skip_notifications: Пропустить отправку уведомлений
            progress_callback: Функция обратного вызова для отслеживания прогресса
                              принимает два аргумента: строку с описанием этапа и число от 0 до 1
            
        Returns:
            Список кортежей из путей к файлам протоколов (markdown, json)
        """
        # Проверяем список файлов
        if not audio_files:
            logger.warning("No audio files to process")
            if progress_callback:
                progress_callback("Ошибка: нет файлов для обработки", 0.0)
            return []
        
        # Начинаем отслеживание прогресса
        if progress_callback:
            progress_callback(f"Подготовка к обработке {len(audio_files)} файлов", 0.01)
            
        # Преобразуем все пути в объекты Path
        audio_files = [Path(f) for f in audio_files]
        
        # Подготавливаем базовую директорию для выходных файлов
        if output_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_output_dir = config.output_dir / f"batch_{timestamp}"
        else:
            base_output_dir = Path(output_dir)
        
        base_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Batch output directory: {base_output_dir}")
        
        # Инициализируем метаданные
        if metadata is None:
            metadata = {}
            
        # Обрабатываем каждый файл
        results = []
        errors = []
        
        # Отправляем уведомление о начале обработки, если есть сервис уведомлений
        if self.notification_service and self.notification_service.has_available_adapters() and not skip_notifications:
            try:
                status_message = f"Начало обработки пакета {len(audio_files)} файлов"
                self.notification_service.send_message(status_message)
            except Exception as e:
                logger.warning(f"Failed to send start notification: {e}")
        
        for i, audio_file in enumerate(audio_files):
            try:
                # Обрабатываем файл
                result = self.process_file(
                    audio_file,
                    output_dir=base_output_dir,
                    language=language,
                    metadata=metadata,
                    skip_notifications=skip_notifications,
                    progress_callback=progress_callback
                )
                results.append(result)
                
                # Отправляем уведомление о прогрессе, если есть сервис уведомлений
                if self.notification_service and self.notification_service.has_available_adapters() and not skip_notifications:
                    try:
                        status_message = f"Обработано {i+1} из {len(audio_files)} файлов"
                        self.notification_service.send_message(status_message)
                    except Exception as e:
                        logger.warning(f"Failed to send progress notification: {e}")
            except Exception as e:
                logger.error(f"Error processing file {audio_file}: {e}")
                errors.append((audio_file, str(e)))
                
                # Отправляем уведомление об ошибке, если есть сервис уведомлений
                if self.notification_service and self.notification_service.has_available_adapters() and not skip_notifications:
                    try:
                        status_message = f"Ошибка обработки файла {audio_file}: {e}"
                        self.notification_service.send_message(status_message)
                    except Exception as e:
                        logger.warning(f"Failed to send error notification: {e}")
        
        # Отправляем уведомление об окончании обработки, если есть сервис уведомлений
        if self.notification_service and self.notification_service.has_available_adapters() and not skip_notifications:
            try:
                if errors:
                    status_message = f"Обработка пакета завершена с ошибками:\n"
                    for audio_file, error in errors[:5]:
                        status_message += f"\n- {Path(str(audio_file)).name}: {error}"
                    
                    if len(errors) > 5:
                        status_message += f"\n...and {len(errors) - 5} more errors."
                
                self.notification_service.send_message(status_message)
            except Exception as e:
                logger.warning(f"Failed to send completion notification: {e}")
        
        return results
        
    def convert_to_transcript(
        self,
        transcript_data: Union[Dict[str, Any], List[Dict[str, Any]]],
        transcript_path: Union[str, Path] = None,
        language: Optional[str] = None,
        meeting_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[Transcript, str, Dict[str, Any]]:
        """
        Преобразует JSON-данные транскрипта в единый внутренний формат Transcript.
        
        Args:
            transcript_data: Данные транскрипта в формате JSON
            transcript_path: Путь к файлу транскрипта (для логирования)
            language: Язык транскрипта (например, 'de', 'en', 'ru')
            meeting_info: Дополнительная информация о встрече
            
        Returns:
            Кортеж из (объект Transcript, язык, обновленные метаданные)
            
        Raises:
            ValueError: Если формат транскрипта не распознан
        """
        # Добавляем детальное логирование для отладки
        logger.debug(f"Processing transcript data with keys: {list(transcript_data.keys()) if isinstance(transcript_data, dict) else type(transcript_data).__name__}")
        
        # Обрабатываем различные форматы JSON-файлов транскриптов
        segments_data = None
        
        # Формат 1: Список сегментов на верхнем уровне
        if isinstance(transcript_data, list):
            segments_data = transcript_data
            logger.debug("Detected transcript format: list of segments")
        
        # Формат 2: Объект с полем 'segments'
        elif isinstance(transcript_data, dict) and 'segments' in transcript_data:
            segments_data = transcript_data['segments']
            logger.debug("Detected transcript format: object with 'segments' field")
            
            # Проверяем наличие метаданных и языка для этого формата
            language, meeting_info = self._extract_metadata_and_language(transcript_data, language, meeting_info)
        
        # Формат 3: Объект с полем 'text' (простой текстовый формат)
        elif isinstance(transcript_data, dict) and 'text' in transcript_data:
            # Создаем единый сегмент из текста
            segments_data = [{
                'speaker': transcript_data.get('speaker', 'Speaker'),
                'text': transcript_data['text'],
                'start': transcript_data.get('start', 0.0),
                'end': transcript_data.get('end', 0.0)
            }]
            logger.debug("Detected transcript format: simple text object")
            
        # Формат 4: Объект с множественными ключами текста (transcript, content, etc.)
        elif isinstance(transcript_data, dict):
            text_keys = ['transcript', 'content', 'transcription', 'text_content']
            found_text = None
            
            for key in text_keys:
                if key in transcript_data and transcript_data[key]:
                    found_text = transcript_data[key]
                    break
            
            if found_text:
                segments_data = [{
                    'speaker': transcript_data.get('speaker', 'Speaker'),
                    'text': found_text,
                    'start': transcript_data.get('start', 0.0),
                    'end': transcript_data.get('end', 0.0)
                }]
                logger.debug(f"Detected transcript format: object with text key '{key}'")
                
                # Извлекаем метаданные если есть
                if 'metadata' in transcript_data:
                    meeting_info.update(transcript_data['metadata'])
                if 'language' in transcript_data:
                    language = transcript_data['language']
        
        # Формат Replicate API: Объект с полем 'output' содержащим 'segments'
        elif isinstance(transcript_data, dict) and 'output' in transcript_data:
            if isinstance(transcript_data['output'], dict) and 'segments' in transcript_data['output']:
                segments_data = transcript_data['output']['segments']
                logger.debug("Detected transcript format: Replicate API format")
                
                # Извлекаем язык из output если доступен
                if 'language' in transcript_data['output']:
                    language = transcript_data['output']['language']
                    logger.debug(f"Extracted language from Replicate output: {language}")
                
                # Извлекаем дополнительные метаданные
                meeting_info = self._extract_replicate_metadata(transcript_data, meeting_info)
            else:
                logger.warning("Replicate format detected but no segments found in output")
                segments_data = None
        
        # Формат 3: Объект с полем 'results' (формат AWS Transcribe)
        elif isinstance(transcript_data, dict) and 'results' in transcript_data:
            if 'items' in transcript_data['results']:
                # AWS Transcribe формат
                items = transcript_data['results']['items']
                segments_data = []
                current_segment = {"speaker": "speaker_0", "text": "", "start": 0.0, "end": 0.0}
                
                for item in items:
                    if item.get('type') == 'pronunciation':
                        if current_segment["text"] and float(item.get('start_time', 0)) - current_segment["end"] > 1.0:
                            # Новый сегмент, если пауза больше 1 секунды
                            segments_data.append(current_segment.copy())
                            current_segment = {"speaker": "speaker_0", "text": "", "start": float(item.get('start_time', 0)), "end": 0.0}
                        
                        if not current_segment["text"]:
                            current_segment["start"] = float(item.get('start_time', 0))
                        
                        current_segment["text"] += " " + item.get('alternatives', [{}])[0].get('content', '')
                        current_segment["end"] = float(item.get('end_time', 0))
                    
                    elif item.get('type') == 'punctuation':
                        current_segment["text"] += item.get('alternatives', [{}])[0].get('content', '')
                
                # Добавляем последний сегмент
                if current_segment["text"]:
                    segments_data.append(current_segment)
                
                logger.debug("Detected transcript format: AWS Transcribe")
            else:
                # Другой формат с 'results'
                segments_data = transcript_data['results']
                logger.debug("Detected transcript format: object with 'results' field")
                
                # Проверяем наличие метаданных и языка для этого формата
                language, meeting_info = self._extract_metadata_and_language(transcript_data, language, meeting_info)
        
        # Формат 4: Объект с полем 'transcript' или 'transcription'
        elif isinstance(transcript_data, dict) and ('transcript' in transcript_data or 'transcription' in transcript_data):
            transcript_text = transcript_data.get('transcript', transcript_data.get('transcription', ''))
            segments_data = [{
                "speaker": "speaker_0",
                "text": transcript_text,
                "start": 0.0,
                "end": 60.0  # Предполагаем длительность 1 минута
            }]
            logger.debug("Detected transcript format: object with 'transcript' or 'transcription' field")
            
            # Проверяем наличие метаданных и языка для этого формата
            language, meeting_info = self._extract_metadata_and_language(transcript_data, language, meeting_info)
        
        # Формат 5: Простой текст (строка)
        elif isinstance(transcript_data, str) and transcript_data.strip():
            # Преобразуем текст в формат транскрипта
            segments_data = convert_plain_text_to_transcript(transcript_data)
            logger.debug("Detected transcript format: plain text string")
            
        # Если не удалось определить формат
        if segments_data is None:
            # Попытка преобразовать данные в строку и обработать как текст
            try:
                if isinstance(transcript_data, dict):
                    text_data = json.dumps(transcript_data, ensure_ascii=False)
                    segments_data = convert_plain_text_to_transcript(text_data)
                    logger.debug("Converted JSON object to text and processed as transcript")
                elif isinstance(transcript_data, list):
                    # Попытка обработать список как текст
                    text_data = "\n".join([str(item) for item in transcript_data])
                    segments_data = convert_plain_text_to_transcript(text_data)
                    logger.debug("Converted list to text and processed as transcript")
            except Exception as e:
                logger.error(f"Failed to convert data to transcript format: {e}")
                segments_data = None
                
        # Если все попытки преобразования не удались
        # Если ничего не найдено, попробуем создать сегмент из доступных данных
        if segments_data is None and isinstance(transcript_data, dict):
            # Попытка создать базовый сегмент из любых текстовых данных
            text_content = None
            
            # Ищем любой текстовый контент в объекте
            for key, value in transcript_data.items():
                if isinstance(value, str) and len(value.strip()) > 10:  # Минимальная длина текста
                    text_content = value.strip()
                    break
            
            if text_content:
                segments_data = [{
                    'speaker': 'Unknown Speaker',
                    'text': text_content,
                    'start': 0.0,
                    'end': 0.0
                }]
                logger.debug("Created fallback segment from text content")
        
        if segments_data is None:
            # Логируем структуру данных для диагностики
            if isinstance(transcript_data, dict):
                logger.error(f"Failed to parse transcript. Available keys: {list(transcript_data.keys())}")
                logger.error(f"Sample of data structure: {str(transcript_data)[:500]}...")
            else:
                logger.error(f"Failed to parse transcript. Data type: {type(transcript_data)}")
            
            error_msg = "Invalid transcript format: could not determine format. Expected a list of segments or a recognized transcript format."
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Создаем объект Transcript из данных JSON
        segments = []
        for segment in segments_data:
            # Проверяем наличие обязательных полей
            if 'text' not in segment:
                logger.warning(f"Skipping segment without 'text' field: {segment}")
                continue
            
            # Устанавливаем значения по умолчанию для необязательных полей
            speaker = segment.get('speaker', segment.get('speaker_id', 'speaker_0'))
            # Нормализуем имя спикера
            speaker = self._normalize_speaker_name(speaker)
            start = float(segment.get('start', segment.get('start_time', 0.0)))
            end = float(segment.get('end', segment.get('end_time', start + 5.0)))
            
            segments.append(TranscriptSegment(
                speaker=speaker,
                text=segment['text'],
                start=start,
                end=end
            ))
        
        transcript = Transcript(
            segments=segments,
            audio_path=str(transcript_path) if transcript_path else "",
            language=language
        )
        
        return transcript, language, meeting_info
    
    def process_transcript_json(
        self,
        transcript_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        language: Optional[str] = None,
        meeting_info: Optional[Dict[str, Any]] = None,
        skip_notifications: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        save_intermediates: bool = False  # Новый параметр для сохранения промежуточных результатов
    ) -> Tuple[Path, Path]:
        """
        Обрабатывает JSON-файл транскрипта для генерации протокола
        
        Args:
            transcript_path: Путь к JSON-файлу транскрипта
            output_dir: Директория для сохранения результатов
                       (если None, создается автоматически)
            language: Язык транскрипта (например, 'de', 'en', 'ru')
            meeting_info: Дополнительная информация о встрече
            skip_notifications: Пропустить отправку уведомлений
            progress_callback: Функция обратного вызова для отслеживания прогресса
                              принимает два аргумента: строку с описанием этапа и число от 0 до 1
            save_intermediates: Сохранять промежуточные результаты для отладки
            
        Returns:
            Кортеж из путей к файлам протокола (markdown, json)
            
        Raises:
            FileNotFoundError: Если файл транскрипта не найден
            json.JSONDecodeError: Если файл транскрипта содержит некорректный JSON
            LLMError: Если произошла ошибка при обработке текста
            ValidationError: Если произошла ошибка при валидации результата
        """
        # Константы для прогресса (избегаем магических чисел)
        PROGRESS_INIT = 0.01
        PROGRESS_LOAD = 0.1
        PROGRESS_CONVERT = 0.3
        PROGRESS_ANALYZE = 0.4
        PROGRESS_ANALYZE_COMPLETE = 0.6
        PROGRESS_GENERATE = 0.7
        PROGRESS_NOTIFY = 0.9
        PROGRESS_COMPLETE = 1.0
        
        start_time = time.time()
        logger.info(f"Starting transcript processing pipeline for {transcript_path}")
        
        # Вызываем callback с начальным статусом, если он предоставлен
        if progress_callback:
            progress_callback("Инициализация", PROGRESS_INIT)
        
        # Преобразуем путь в объект Path
        transcript_path = Path(transcript_path)
        
        # Проверяем существование файла транскрипта
        if not transcript_path.exists():
            error_msg = f"Transcript file not found: {transcript_path}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback("Ошибка: файл не найден", 0.0)
            raise FileNotFoundError(error_msg)
        
        # Создаем директорию для выходных файлов
        if output_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = config.output_dir / f"{transcript_path.stem}_{timestamp}"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Output directory created: {output_dir}")
        
        # Если meeting_info не передано, создаем его из имени файла
        if meeting_info is None:
            meeting_info = self._extract_metadata(transcript_path.stem)
        
        # Язык по умолчанию
        if language is None:
            language = config.default_lang
            logger.debug(f"Using default language: {language}")
        
        try:
            # Загружаем транскрипт из файла
            if progress_callback:
                progress_callback("Загрузка транскрипта", PROGRESS_LOAD)
            
            # Определяем тип файла по расширению
            file_ext = Path(transcript_path).suffix.lower()
            
            if file_ext == '.json':
                # Загружаем JSON-файл
                try:
                    with open(transcript_path, "r", encoding="utf-8") as f:
                        transcript_data = json.load(f)
                except json.JSONDecodeError as e:
                    # Если JSON некорректный, пробуем обработать как текст
                    logger.warning(f"Failed to parse JSON file, trying as text: {e}")
                    with open(transcript_path, "r", encoding="utf-8") as f:
                        transcript_data = f.read()
            else:
                # Загружаем текстовый файл
                with open(transcript_path, "r", encoding="utf-8") as f:
                    transcript_data = f.read()
            
            # Преобразуем данные в единый внутренний формат Transcript
            transcript, language, meeting_info = self.convert_to_transcript(
                transcript_data=transcript_data,
                transcript_path=transcript_path,
                language=language,
                meeting_info=meeting_info
            )
            
            if progress_callback:
                progress_callback("Транскрипт загружен и преобразован", PROGRESS_CONVERT)
            
            # Обработка текста (Map-Reduce-Refine)
            logger.info("Starting transcript analysis")
            if progress_callback:
                progress_callback("Анализ транскрипта", PROGRESS_ANALYZE)
            
            # Получаем сегменты из транскрипта для обработки
            segments = [{
                "speaker": segment.speaker,
                "text": segment.text,
                "start": segment.start,
                "end": segment.end
            } for segment in transcript.segments]
            
            # Сохраняем транскрипт для отладки
            transcript_json_path = output_dir / "transcript.json"
            with open(transcript_json_path, "w", encoding="utf-8") as f:
                json.dump(segments, f, ensure_ascii=False, indent=2)
            logger.debug(f"Transcript saved to: {transcript_json_path}")
            
            # Создаем протокол из сегментов
            try:
                # Если используется MapReduceService, получаем результаты map и reduce
                map_results = None
                reduce_results = None
                
                if hasattr(self.protocol_service, 'map_reduce_service') and self.protocol_service.map_reduce_service:
                    # Получаем результаты map и reduce для отладки
                    map_reduce = self.protocol_service.map_reduce_service
                    
                    # Выполняем map-этап
                    if hasattr(map_reduce, 'process_map_stage'):
                        map_results = map_reduce.process_map_stage(segments, language)
                        
                        # Сохраняем результаты map для отладки
                        if save_intermediates and map_results:
                            map_results_path = output_dir / "map_results.json"
                            with open(map_results_path, "w", encoding="utf-8") as f:
                                json.dump(map_results, f, ensure_ascii=False, indent=2)
                            logger.debug(f"Map results saved to: {map_results_path}")
                    
                    # Выполняем reduce-этап
                    if hasattr(map_reduce, 'process_reduce_stage') and map_results:
                        reduce_results = map_reduce.process_reduce_stage(map_results, language)
                        
                        # Сохраняем результаты reduce для отладки
                        if save_intermediates and reduce_results:
                            reduce_results_path = output_dir / "reduce_results.json"
                            with open(reduce_results_path, "w", encoding="utf-8") as f:
                                json.dump(reduce_results, f, ensure_ascii=False, indent=2)
                            logger.debug(f"Reduce results saved to: {reduce_results_path}")
                
                # Создаем протокол
                protocol = self.protocol_service.create_protocol_from_segments(
                    segments=segments,
                    metadata=meeting_info,
                    language=language
                )
                
                # Проверяем, что протокол не None
                if protocol is None:
                    # Создаем пустой протокол с информацией об ошибке
                    protocol = Protocol(
                        metadata=meeting_info or {},
                        summary="Failed to generate protocol content due to unknown error",
                        decisions=[],
                        action_items=[],
                        participants=[],
                        agenda_items=[]
                    )
                
                # Создаем markdown-представление протокола
                markdown = self._generate_markdown_from_protocol(protocol)
            except Exception as e:
                # В случае ошибки создаем пустой протокол
                logger.error(f"Error creating protocol: {e}", exc_info=True)
                protocol = Protocol(
                    metadata=meeting_info or {},
                    summary=f"Failed to generate protocol content due to error: {e}",
                    decisions=[],
                    action_items=[],
                    participants=[],
                    agenda_items=[]
                )
                markdown = self._generate_markdown_from_protocol(protocol)
            logger.info("Analysis complete")
            
            if progress_callback:
                progress_callback("Анализ завершен", PROGRESS_ANALYZE_COMPLETE)
            
            # Сохранение результатов
            logger.info("Saving results")
            if progress_callback:
                progress_callback("Генерация протокола", PROGRESS_GENERATE)
            
            # Определяем имя файла на основе заголовка протокола и даты
            date_str = protocol.metadata.get('date', datetime.now().strftime("%Y-%m-%d"))
            title_safe = protocol.metadata.get('title', 'meeting_protocol')
            # Очищаем заголовок от недопустимых символов для имени файла
            title_safe = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in title_safe)
            title_safe = title_safe.replace(' ', '_')[:50]  # Ограничиваем длину
            
            base_filename = f"{date_str}_{title_safe}"
            
            # Сохраняем протокол в формате Markdown
            md_file = output_dir / f"{base_filename}.md"
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(markdown)
            logger.info(f"Markdown protocol saved to: {md_file}")
            
            # Сохраняем протокол в формате JSON
            json_file = output_dir / f"{base_filename}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(protocol.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info(f"JSON protocol saved to: {json_file}")
            
            # Создаем файл протокола в формате EGL JSON (если язык немецкий)
            if language and language.lower() == "de":
                egl_json_file = output_dir / f"{base_filename}_egl.json"
                with open(egl_json_file, "w", encoding="utf-8") as f:
                    json.dump(protocol.to_egl_json(), f, ensure_ascii=False, indent=2)
                logger.info(f"EGL JSON protocol saved to: {egl_json_file}")
            
            # Отправка уведомлений
            if not skip_notifications and self.notification_service:
                try:
                    logger.info("Sending notifications")
                    if progress_callback:
                        progress_callback("Отправка уведомлений", PROGRESS_NOTIFY)
                    
                    # Проверяем, есть ли метод send_protocol_files
                    if hasattr(self.notification_service, 'send_protocol_files'):
                        notification_success = self.notification_service.send_protocol_files(
                            md_path=md_file,
                            json_path=json_file
                        )
                        
                        if notification_success:
                            logger.info("Notifications sent successfully")
                        else:
                            logger.warning("Failed to send notifications")
                    else:
                        # Фоллбэк: пробуем использовать метод send_notification
                        if hasattr(self.notification_service, 'send_notification'):
                            message = f"Protocol generated: {md_file}"
                            notification_success = self.notification_service.send_notification(message)
                            if notification_success:
                                logger.info("Notification sent successfully")
                            else:
                                logger.warning("Failed to send notification")
                        else:
                            logger.warning("NotificationService does not have send_protocol_files or send_notification methods")
                except Exception as e:
                    logger.warning(f"Error sending notifications: {e}")
            else:
                logger.info("Notifications skipped")
            
            # Завершаем и логируем время выполнения
            end_time = time.time()
            processing_time = end_time - start_time
            logger.info(f"Processing completed in {processing_time:.2f} seconds")
            
            # Отслеживаем успешную обработку
            file_extension = transcript_path.suffix.lower() if hasattr(transcript_path, 'suffix') else ".json"
            track_file_processed(
                language=language or "unknown",
                file_type=file_extension,
                status="success"
            )
            
            if progress_callback:
                progress_callback("Завершено", PROGRESS_COMPLETE)
            
            return md_file, json_file
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            error_file = output_dir / "error.log"
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(f"JSON decode error: {e}\n")
            
            if progress_callback:
                progress_callback(f"Ошибка декодирования JSON: {e}", 0.0)
            
            raise
            
        except LLMError as e:
            logger.error(f"LLM error: {e}")
            error_file = output_dir / "error.log"
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(f"LLM error: {e}\n")
                if hasattr(e, "details"):
                    f.write(f"Details: {json.dumps(e.details, ensure_ascii=False, indent=2)}\n")
            
            if progress_callback:
                progress_callback(f"Ошибка обработки текста: {e}", 0.0)
            
            raise
            
        except Exception as e:
            logger.error(f"Unexpected error during processing: {e}", exc_info=True)
            error_file = output_dir / "error.log"
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(f"Unexpected error: {e}\n")
            
            if progress_callback:
                progress_callback(f"Непредвиденная ошибка: {e}", 0.0)
            
            raise
