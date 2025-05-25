"""
Общие фикстуры для тестов
"""
import pytest
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Dict, List, Any

import sys
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from app.core.models.transcript import Transcript, TranscriptSegment
from app.core.models.protocol import Protocol, AgendaItem, Decision, ActionItem, Participant
from app.adapters.asr.base import ASRAdapter
from app.adapters.asr.replicate_adapter import ReplicateASRAdapter
from app.adapters.asr.openai_adapter import OpenAIASRAdapter
from app.adapters.llm.base import LLMAdapter
from app.adapters.llm.openai_adapter import OpenAILLMAdapter
from app.adapters.notifications.base import NotificationAdapter
from app.adapters.notifications.telegram_adapter import TelegramNotificationAdapter
from app.core.services.asr_service import ASRService
from app.core.services.analysis_service import MapReduceService
from app.core.services.protocol_service import ProtocolService
from app.core.services.notification_service import NotificationService
from app.core.services.pipeline import Pipeline

@pytest.fixture
def sample_transcript_segments():
    """Возвращает пример сегментов транскрипции"""
    return [
        {
            "text": "Hello, welcome to the meeting.",
            "start": 0.0,
            "end": 3.0,
            "speaker_id": "SPEAKER_00",
            "speaker_confidence": 0.95
        },
        {
            "text": "Today we're going to discuss the project status.",
            "start": 3.0,
            "end": 7.0,
            "speaker_id": "SPEAKER_00",
            "speaker_confidence": 0.9
        },
        {
            "text": "I think we need to update the roadmap.",
            "start": 7.0,
            "end": 10.0,
            "speaker_id": "SPEAKER_01",
            "speaker_confidence": 0.85
        },
        {
            "text": "Yes, and we should also allocate more resources to the frontend team.",
            "start": 10.0,
            "end": 15.0,
            "speaker_id": "SPEAKER_02",
            "speaker_confidence": 0.8
        },
        {
            "text": "I agree. Let's plan to meet again next week to review progress.",
            "start": 15.0,
            "end": 20.0,
            "speaker_id": "SPEAKER_00",
            "speaker_confidence": 0.9
        }
    ]

@pytest.fixture
def sample_transcript_object(sample_transcript_segments):
    """Возвращает пример объекта Transcript"""
    segments = []
    for idx, segment in enumerate(sample_transcript_segments):
        segments.append(TranscriptSegment(
            text=segment["text"],
            start=segment["start"],
            end=segment["end"],
            speaker=segment["speaker_id"],
            speaker_confidence=segment.get("speaker_confidence", 1.0),
            id=str(idx)
        ))
    
    return Transcript(
        segments=segments,
        audio_path="/path/to/audio.mp3",
        language="en",
        metadata={"sample_rate": 16000}
    )

@pytest.fixture
def sample_metadata():
    """Возвращает пример метаданных протокола"""
    return {
        "title": "Project Status Meeting",
        "date": "2025-01-15",
        "location": "Online",
        "organizer": "John Smith",
        "author": "AI Assistant"
    }

@pytest.fixture
def sample_protocol_object(sample_metadata):
    """Возвращает пример объекта Protocol"""
    # Создаем участников
    participants = [
        Participant(name="John Smith", role="Project Manager"),
        Participant(name="Alice Johnson", role="Frontend Developer"),
        Participant(name="Bob Brown", role="Backend Developer")
    ]
    
    # Создаем пункты повестки
    agenda_items = [
        AgendaItem(
            topic="Project Status Update",
            discussion_summary="Discussed current project status and reviewed milestones.",
            decisions_made=[
                Decision(description="Continue with current plan")
            ],
            action_items_assigned=[
                ActionItem(who="John", what="Update roadmap", due="2025-01-22")
            ]
        ),
        AgendaItem(
            topic="Resource Allocation",
            discussion_summary="Discussed resource allocation for different teams.",
            decisions_made=[
                Decision(description="Allocate more resources to frontend team")
            ],
            action_items_assigned=[
                ActionItem(who="John", what="Update resource allocation spreadsheet", due="2025-01-17")
            ]
        ),
        AgendaItem(
            topic="Next Steps",
            discussion_summary="Planned next steps and follow-up meetings.",
            decisions_made=[
                Decision(description="Hold weekly follow-up meetings")
            ],
            action_items_assigned=[
                ActionItem(who="Alice", what="Prepare frontend progress report", due="2025-01-21"),
                ActionItem(who="Bob", what="Prepare backend progress report", due="2025-01-21")
            ]
        )
    ]
    
    # Создаем глобальные решения и задачи
    decisions = [
        Decision(description="Approve current project timeline", id="D001")
    ]
    
    action_items = [
        ActionItem(who="All", what="Review project documentation", due="2025-01-20", status="Open", id="A001")
    ]
    
    # Создаем объект Protocol
    return Protocol(
        metadata=sample_metadata,
        participants=participants,
        agenda_items=agenda_items,
        summary="Project status meeting discussing current progress, resource allocation, and next steps.",
        decisions=decisions,
        action_items=action_items
    )

@pytest.fixture
def temp_audio_file():
    """Создает временный аудиофайл для тестов"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        # Записываем какие-то данные (это не настоящий WAV, но для тестов подойдет)
        f.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xAC\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
        path = Path(f.name)
    
    yield path
    
    # Удаляем файл после использования
    if path.exists():
        path.unlink()

@pytest.fixture
def temp_output_dir():
    """Создает временную директорию для выходных файлов"""
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir)
        yield path

@pytest.fixture
def mocked_config():
    """Мокает конфигурацию приложения"""
    with patch("app.config.config.config") as mock_config:
        # Настраиваем базовые пути
        mock_config.base_dir = Path("/mock/base/dir")
        mock_config.output_dir = Path("/mock/output/dir")
        mock_config.schema_path = Path("/mock/schema/path")
        mock_config.prompts_dir = Path("/mock/prompts/dir")
        mock_config.markdown_templates_dir = Path("/mock/templates/dir")
        
        # Настраиваем API ключи
        mock_config.replicate_api_token = "mock_replicate_token"
        mock_config.openai_api_key = "mock_openai_key"
        mock_config.telegram_bot_token = "mock_telegram_token"
        mock_config.telegram_chat_id = "mock_chat_id"
        
        # Настраиваем языковые параметры
        mock_config.default_lang = "en"
        
        # Настраиваем параметры для чанкинга
        mock_config.chunk_tokens = 500
        mock_config.overlap_tokens = 100
        
        # Возвращаем мок
        yield mock_config

@pytest.fixture
def mocked_replicate():
    """Мокает Replicate API"""
    with patch("replicate.run") as mock_run:
        mock_run.return_value = {
            "segments": [
                {
                    "text": "Hello, welcome to the meeting.",
                    "start": 0.0,
                    "end": 3.0,
                    "speaker_id": "SPEAKER_00",
                    "speaker_confidence": 0.95
                },
                {
                    "text": "Today we're going to discuss the project status.",
                    "start": 3.0,
                    "end": 7.0,
                    "speaker_id": "SPEAKER_00",
                    "speaker_confidence": 0.9
                }
            ]
        }
        yield mock_run

@pytest.fixture
def mocked_openai():
    """Мокает OpenAI API"""
    with patch("openai.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Настраиваем мок-ответ для chat.completions.create
        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = '{"result": "success", "data": {"key": "value"}}'
        mock_choice.message = mock_message
        mock_completion.choices = [mock_choice]
        
        mock_client.chat.completions.create.return_value = mock_completion
        
        # Настраиваем мок-ответ для audio.transcriptions.create
        mock_audio_response = MagicMock()
        mock_audio_response.segments = [
            MagicMock(text="Hello, welcome to the meeting.", start=0.0, end=3.0, confidence=0.95),
            MagicMock(text="Today we're going to discuss the project status.", start=3.0, end=7.0, confidence=0.9)
        ]
        mock_client.audio.transcriptions.create.return_value = mock_audio_response
        
        yield mock_client

@pytest.fixture
def mocked_requests():
    """Мокает запросы requests"""
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 123}}
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        yield mock_post

# Мок классы для тестирования сервисов
class MockASRAdapter(ASRAdapter):
    """Мок-адаптер для тестирования ASR"""
    
    def __init__(self, mock_response=None):
        self.mock_response = mock_response or [
            {"text": "Hello", "start": 0.0, "end": 1.0, "speaker_id": "SPEAKER_01"},
            {"text": "World", "start": 1.0, "end": 2.0, "speaker_id": "SPEAKER_02"}
        ]
        self.transcribe_called = False
        self.last_audio_path = None
        self.last_language = None
        self.last_kwargs = {}
    
    def transcribe(self, audio_path, language=None, **kwargs):
        self.transcribe_called = True
        self.last_audio_path = audio_path
        self.last_language = language
        self.last_kwargs = kwargs
        return self.mock_response
    
    def get_adapter_info(self):
        return {
            "name": "MockASRAdapter",
            "provider": "Mock",
            "features": ["test"]
        }

class MockLLMAdapter(LLMAdapter):
    """Мок-адаптер для тестирования LLM"""
    
    def __init__(self, mock_text_response=None, mock_json_response=None):
        self.mock_text_response = mock_text_response or "Mock response"
        self.mock_json_response = mock_json_response or {"result": "mock"}
        self.generate_text_called = False
        self.generate_json_called = False
        self.last_prompt = None
        self.last_system_message = None
        self.last_temperature = None
        self.last_max_tokens = None
        self.last_schema = None
        self.last_kwargs = {}
    
    def generate_text(self, prompt, system_message=None, temperature=0.7, max_tokens=None, **kwargs):
        self.generate_text_called = True
        self.last_prompt = prompt
        self.last_system_message = system_message
        self.last_temperature = temperature
        self.last_max_tokens = max_tokens
        self.last_kwargs = kwargs
        return self.mock_text_response
    
    def generate_json(self, prompt, system_message=None, temperature=0.3, schema=None, **kwargs):
        self.generate_json_called = True
        self.last_prompt = prompt
        self.last_system_message = system_message
        self.last_temperature = temperature
        self.last_schema = schema
        self.last_kwargs = kwargs
        return self.mock_json_response
    
    def count_tokens(self, text):
        return len(text.split())
    
    def get_adapter_info(self):
        return {
            "name": "MockLLMAdapter",
            "provider": "Mock",
            "features": ["test"]
        }

class MockNotificationAdapter(NotificationAdapter):
    """Мок-адаптер для тестирования уведомлений"""
    
    def __init__(self, is_configured=True):
        self.is_configured_value = is_configured
        self.send_message_called = False
        self.send_file_called = False
        self.last_text = None
        self.last_file_path = None
        self.last_caption = None
        self.last_kwargs = {}
    
    def send_message(self, text, **kwargs):
        self.send_message_called = True
        self.last_text = text
        self.last_kwargs = kwargs
        return True
    
    def send_file(self, file_path, caption=None, **kwargs):
        self.send_file_called = True
        self.last_file_path = file_path
        self.last_caption = caption
        self.last_kwargs = kwargs
        return True
    
    def is_configured(self):
        return self.is_configured_value
    
    def get_adapter_info(self):
        return {
            "name": "MockNotificationAdapter",
            "provider": "Mock",
            "features": ["test"],
            "configured": self.is_configured_value
        }

@pytest.fixture
def mock_asr_adapter():
    """Возвращает мок ASR адаптера"""
    return MockASRAdapter()

@pytest.fixture
def mock_llm_adapter():
    """Возвращает мок LLM адаптера"""
    return MockLLMAdapter()

@pytest.fixture
def mock_notification_adapter():
    """Возвращает мок адаптера уведомлений"""
    return MockNotificationAdapter()

@pytest.fixture
def mock_asr_service(mock_asr_adapter):
    """Возвращает мок ASR сервиса"""
    return ASRService(adapter=mock_asr_adapter)

@pytest.fixture
def mock_analysis_service(mock_llm_adapter):
    """Возвращает мок MapReduceService"""
    # Мокаем загрузку шаблонов промптов
    with patch("app.utils.templates.load_prompt_template") as mock_load_prompt:
        mock_load_prompt.return_value = "Test prompt template"
        
        service = MapReduceService(llm_adapter=mock_llm_adapter, chunk_tokens=100, overlap_tokens=20)
        return service

@pytest.fixture
def mock_protocol_service(mock_analysis_service):
    """Возвращает мок ProtocolService"""
    # Мокаем валидацию схемы
    with patch("app.utils.schemas.validate_json_schema") as mock_validate:
        mock_validate.return_value = []
        
        service = ProtocolService(map_reduce_service=mock_analysis_service)
        return service

@pytest.fixture
def mock_notification_service(mock_notification_adapter):
    """Возвращает мок NotificationService"""
    return NotificationService(default_adapter=mock_notification_adapter)

@pytest.fixture
def mock_pipeline(mock_asr_service, mock_analysis_service, mock_protocol_service, mock_notification_service):
    """Возвращает мок Pipeline"""
    return Pipeline(
        asr_service=mock_asr_service,
        analysis_service=mock_analysis_service,
        protocol_service=mock_protocol_service,
        notification_service=mock_notification_service
    )

# Дополнительные фикстуры для тестирования метаданных
@pytest.fixture
def sample_filenames():
    """Возвращает примеры имен файлов для тестирования извлечения метаданных"""
    return [
        "meeting_2024-05-15_project_status.mp3",
        "interview_with_candidate_2024-06-01.wav",
        "board_meeting_quarterly_review.mp3",
        "team_sync_2024-07-10_marketing.wav",
        "",  # пустое имя файла
        "meeting.mp3"  # без даты
    ]

@pytest.fixture
def sample_cli_args():
    """Возвращает примеры аргументов командной строки для тестирования CLI"""
    return [
        # Обработка одного файла
        ["app.py", "process", "--file", "/path/to/audio.mp3"],
        # Обработка одного файла с указанием выходной директории
        ["app.py", "process", "--file", "/path/to/audio.mp3", "--output", "/path/to/output"],
        # Пакетная обработка
        ["app.py", "batch", "--dir", "/path/to/audio/files"],
        # Пакетная обработка с указанием выходной директории
        ["app.py", "batch", "--dir", "/path/to/audio/files", "--output", "/path/to/output"],
        # Пакетная обработка с указанием паттерна файлов
        ["app.py", "batch", "--dir", "/path/to/audio/files", "--pattern", "*.mp3"],
        # Версия
        ["app.py", "--version"],
        # Помощь
        ["app.py", "--help"]
    ]

@pytest.fixture
def mock_audio_metadata():
    """Возвращает мок метаданных аудиофайла"""
    return {
        "duration": 300.5,  # длительность в секундах
        "sample_rate": 16000,
        "channels": 1,
        "format": "mp3",
        "bit_rate": 128000
    }

@pytest.fixture
def mock_extract_metadata_results():
    """Возвращает моки результатов извлечения метаданных из имен файлов"""
    return {
        "meeting_2024-05-15_project_status.mp3": {
            "title": "Meeting Project Status",
            "date": "2024-05-15",
            "location": "Online Meeting",
            "organizer": "",
            "author": "AI Assistant"
        },
        "interview_with_candidate_2024-06-01.wav": {
            "title": "Interview With Candidate",
            "date": "2024-06-01",
            "location": "Online Meeting",
            "organizer": "",
            "author": "AI Assistant"
        },
        "board_meeting_quarterly_review.mp3": {
            "title": "Board Meeting Quarterly Review",
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "location": "Online Meeting",
            "organizer": "",
            "author": "AI Assistant"
        }
    }
