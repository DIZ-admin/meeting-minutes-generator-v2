"""
Тесты для сервисов приложения
"""
import pytest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Dict, List, Any

import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, parent_dir)

from app.core.services.asr_service import ASRService
from app.core.services.analysis_service import MapReduceService
from app.core.services.notification_service import NotificationService
from app.core.services.pipeline import Pipeline
from app.core.models.transcript import Transcript, TranscriptSegment
from app.core.models.protocol import Protocol, AgendaItem, Decision, ActionItem, Participant
from app.core.exceptions import ASRError, LLMError, NotificationError, ConfigError

# Импортируем мок-адаптеры из теста адаптеров
from test_adapters import MockASRAdapter, MockLLMAdapter, MockNotificationAdapter

class TestASRService:
    """Тесты для ASRService"""
    
    def test_asr_service_init(self):
        """Проверка инициализации ASRService"""
        mock_adapter = MockASRAdapter()
        service = ASRService(adapter=mock_adapter)
        assert service.adapter == mock_adapter
    
    def test_asr_service_init_default_adapter(self):
        """Проверка инициализации ASRService с адаптером по умолчанию"""
        with patch("app.core.services.asr_service.ReplicateASRAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter
            
            service = ASRService()
            
            assert service.adapter == mock_adapter
            mock_adapter_class.assert_called_once()
    
    def test_asr_service_transcribe(self):
        """Проверка метода transcribe"""
        mock_adapter = MockASRAdapter()
        service = ASRService(adapter=mock_adapter)
        
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio_file:
            audio_path = Path(audio_file.name)
            
            # Вызываем метод transcribe
            result = service.transcribe(audio_path, language="en")
            
            # Проверяем результат
            assert result == mock_adapter.mock_response
            assert mock_adapter.transcribe_called is True
            assert mock_adapter.last_audio_path == audio_path
            assert mock_adapter.last_language == "en"
    
    def test_asr_service_change_adapter(self):
        """Проверка метода change_adapter"""
        mock_adapter1 = MockASRAdapter()
        mock_adapter2 = MockASRAdapter()
        
        service = ASRService(adapter=mock_adapter1)
        assert service.adapter == mock_adapter1
        
        service.change_adapter(mock_adapter2)
        assert service.adapter == mock_adapter2
    
    def test_asr_service_get_adapter_info(self):
        """Проверка метода get_adapter_info"""
        mock_adapter = MockASRAdapter()
        service = ASRService(adapter=mock_adapter)
        
        info = service.get_adapter_info()
        assert info == mock_adapter.get_adapter_info()

class TestMapReduceService:
    """Тесты для MapReduceService"""
    
    def setup_method(self):
        """Настройка окружения для тестов"""
        # Создаем временную директорию для шаблонов
        self.temp_templates_dir = tempfile.TemporaryDirectory()
        self.templates_dir = Path(self.temp_templates_dir.name)
        
        # Создаем шаблоны
        self.map_prompt_path = self.templates_dir / "map_prompt.txt"
        self.reduce_prompt_path = self.templates_dir / "reduce_prompt.txt"
        self.refine_prompt_path = self.templates_dir / "refine_prompt.txt"
        
        with open(self.map_prompt_path, "w") as f:
            f.write("Map prompt template")
        
        with open(self.reduce_prompt_path, "w") as f:
            f.write("Reduce prompt template")
        
        with open(self.refine_prompt_path, "w") as f:
            f.write("Refine prompt template")
    
    def teardown_method(self):
        """Очистка после тестов"""
        self.temp_templates_dir.cleanup()
    
    def test_map_reduce_service_init(self):
        """Проверка инициализации MapReduceService"""
        mock_llm_adapter = MockLLMAdapter()
        
        service = MapReduceService(
            llm_adapter=mock_llm_adapter,
            map_temperature=0.2,
            reduce_temperature=0.3,
            refine_temperature=0.5,
            max_parallel_workers=3,
            templates_dir=self.templates_dir
        )
        
        assert service.llm_adapter == mock_llm_adapter
        assert service.map_temperature == 0.2
        assert service.reduce_temperature == 0.3
        assert service.refine_temperature == 0.5
        assert service.max_parallel_workers == 3
        assert service.templates_dir == self.templates_dir
    
    def test_map_reduce_service_init_default_adapter(self):
        """Проверка инициализации MapReduceService с адаптером по умолчанию"""
        with patch("app.core.services.analysis_service.OpenAILLMAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter
            
            service = MapReduceService(templates_dir=self.templates_dir)
            
            assert service.llm_adapter == mock_adapter
            mock_adapter_class.assert_called_once()
    
    def test_map_reduce_service_load_templates(self):
        """Проверка загрузки шаблонов"""
        mock_llm_adapter = MockLLMAdapter()
        service = MapReduceService(
            llm_adapter=mock_llm_adapter,
            templates_dir=self.templates_dir
        )
        
        assert service.map_prompt_template == "Map prompt template"
        assert service.reduce_prompt_template == "Reduce prompt template"
        assert service.refine_prompt_template == "Refine prompt template"
    
    @patch("app.core.services.analysis_service.ThreadPoolExecutor")
    def test_map_reduce_service_process_transcript(self, mock_executor_class):
        """Проверка метода process_transcript"""
        # Настраиваем мок-адаптер
        mock_llm_adapter = MockLLMAdapter(
            mock_json_response={
                "metadata": {
                    "title": "Test Meeting",
                    "date": "2025-01-01",
                    "location": "Test Location",
                    "organizer": "Test Organizer"
                },
                "summary": "Test summary",
                "decisions": ["Decision 1"],
                "actions": [{"who": "John", "what": "Task 1", "due": "2025-01-01"}],
                "participants": [{"name": "John", "role": "Speaker"}],
                "agenda_items": [{"topic": "Agenda 1", "discussion_summary": "Agenda summary"}]
            }
        )
        
        # Настраиваем мок-исполнитель
        mock_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_executor
        mock_future = MagicMock()
        mock_future.result.return_value = {"summary": "Chunk summary", "decisions": [], "actions": []}
        mock_executor.submit.return_value = mock_future
        
        # Создаем сервис
        service = MapReduceService(
            llm_adapter=mock_llm_adapter,
            templates_dir=self.templates_dir
        )
        
        # Подготавливаем транскрипцию
        transcript = [
            {"text": "Hello", "start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
            {"text": "World", "start": 1.0, "end": 2.0, "speaker": "SPEAKER_02"}
        ]
        
        # Вызываем метод process_transcript
        protocol, markdown = service.process_transcript(
            transcript=transcript,
            meeting_info={"title": "Test Meeting", "date": "2025-01-01"},
            language="en"
        )
        
        # Проверяем вызовы метода generate_json
        assert mock_llm_adapter.generate_json_called is True
        
        # Проверяем результат
        assert isinstance(protocol, Protocol)
        assert isinstance(markdown, str)
        # Проверяем метаданные протокола
        assert "title" in protocol.metadata
        assert "date" in protocol.metadata
        assert protocol.metadata.get("title") == "Test Meeting"
        assert protocol.metadata.get("date") == "2025-01-01"

class TestNotificationService:
    """Тесты для NotificationService"""
    
    def test_notification_service_init(self):
        """Проверка инициализации NotificationService"""
        mock_adapter = MockNotificationAdapter()
        service = NotificationService(default_adapter=mock_adapter)
        assert service.default_adapter == mock_adapter
        assert mock_adapter in service.adapters
    
    def test_notification_service_init_default_adapter(self):
        """Проверка инициализации NotificationService с адаптером по умолчанию"""
        with patch("app.core.services.notification_service.TelegramNotificationAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter.is_configured.return_value = True
            mock_adapter_class.return_value = mock_adapter
            
            service = NotificationService()
            
            assert service.default_adapter == mock_adapter
            assert mock_adapter in service.adapters
            mock_adapter_class.assert_called_once()
    
    def test_notification_service_has_available_adapters(self):
        """Проверка метода has_available_adapters"""
        mock_adapter = MockNotificationAdapter(is_configured=True)
        service = NotificationService(default_adapter=mock_adapter)
        assert service.has_available_adapters() is True
        
        mock_adapter = MockNotificationAdapter(is_configured=False)
        service = NotificationService(default_adapter=mock_adapter)
        assert service.has_available_adapters() is False
    
    def test_notification_service_send_message(self):
        """Проверка метода send_message"""
        mock_adapter = MockNotificationAdapter()
        service = NotificationService(default_adapter=mock_adapter)
        
        result = service.send_message("Test message")
        
        assert result is True
        assert mock_adapter.send_message_called is True
        assert mock_adapter.last_text == "Test message"
    
    def test_notification_service_send_file(self):
        """Проверка метода send_file"""
        mock_adapter = MockNotificationAdapter()
        service = NotificationService(default_adapter=mock_adapter)
        
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix=".txt") as temp_file:
            file_path = Path(temp_file.name)
            
            result = service.send_file(file_path, caption="Test file")
            
            assert result is True
            assert mock_adapter.send_file_called is True
            assert mock_adapter.last_file_path == file_path
            assert mock_adapter.last_caption == "Test file"
    
    def test_notification_service_set_default_adapter(self):
        """Проверка метода set_default_adapter"""
        mock_adapter1 = MockNotificationAdapter()
        mock_adapter2 = MockNotificationAdapter()
        
        service = NotificationService(default_adapter=mock_adapter1)
        assert service.default_adapter == mock_adapter1
        
        service.set_default_adapter(mock_adapter2)
        assert service.default_adapter == mock_adapter2
    
    def test_notification_service_get_available_adapters(self):
        """Проверка метода get_available_adapters"""
        mock_adapter = MockNotificationAdapter()
        service = NotificationService(default_adapter=mock_adapter)
        
        adapters_info = service.get_available_adapters()
        assert len(adapters_info) == 1
        assert adapters_info[0]["name"] == "MockNotificationAdapter"
        assert adapters_info[0]["provider"] == "Mock"
        assert "test" in adapters_info[0]["features"]
        assert adapters_info[0]["is_default"] is True

class TestPipeline:
    """Тесты для Pipeline"""
    
    def test_pipeline_init(self):
        """Проверка инициализации Pipeline"""
        mock_asr_service = MagicMock()
        mock_analysis_service = MagicMock()
        mock_protocol_service = MagicMock()
        mock_notification_service = MagicMock()
        
        pipeline = Pipeline(
            asr_service=mock_asr_service,
            analysis_service=mock_analysis_service,
            protocol_service=mock_protocol_service,
            notification_service=mock_notification_service
        )
        
        assert pipeline.asr_service == mock_asr_service
        assert pipeline.analysis_service == mock_analysis_service
        assert pipeline.protocol_service == mock_protocol_service
        assert pipeline.notification_service == mock_notification_service
    
    def test_pipeline_init_default_services(self):
        """Проверка инициализации Pipeline с сервисами по умолчанию"""
        with patch("app.core.services.pipeline.ASRService") as mock_asr_service_class, \
             patch("app.core.services.pipeline.MapReduceService") as mock_analysis_service_class, \
             patch("app.core.services.pipeline.ProtocolService") as mock_protocol_service_class, \
             patch("app.core.services.pipeline.NotificationService") as mock_notification_service_class:
            
            mock_asr_service = MagicMock()
            mock_analysis_service = MagicMock()
            mock_protocol_service = MagicMock()
            mock_notification_service = MagicMock()
            
            mock_asr_service_class.return_value = mock_asr_service
            mock_analysis_service_class.return_value = mock_analysis_service
            mock_protocol_service_class.return_value = mock_protocol_service
            mock_notification_service_class.return_value = mock_notification_service
            
            pipeline = Pipeline()
            
            assert pipeline.asr_service == mock_asr_service
            assert pipeline.analysis_service == mock_analysis_service
            assert pipeline.protocol_service == mock_protocol_service
            assert pipeline.notification_service == mock_notification_service
    
    def test_pipeline_process_audio(self):
        """Проверка метода process_audio"""
        # Настраиваем мок-сервисы
        mock_asr_service = MagicMock()
        mock_analysis_service = MagicMock()
        mock_protocol_service = MagicMock()
        mock_notification_service = MagicMock()
        
        # Настраиваем возвращаемые значения
        mock_asr_service.transcribe.return_value = [
            {"text": "Hello", "start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
            {"text": "World", "start": 1.0, "end": 2.0, "speaker": "SPEAKER_02"}
        ]
        
        mock_protocol = MagicMock()
        mock_protocol.metadata = {"title": "Test Meeting", "date": "2025-01-01"}
        # Настраиваем метод to_dict() для корректной сериализации в JSON
        mock_protocol.to_dict.return_value = {
            "metadata": {"title": "Test Meeting", "date": "2025-01-01"},
            "summary": "Test summary",
            "decisions": ["Decision 1"],
            "action_items": [{"who": "John", "what": "Task 1", "due": "2025-01-01"}],
            "participants": [{"name": "John", "role": "Speaker"}],
            "agenda_items": [{"title": "Agenda 1", "summary": "Agenda summary"}]
        }
        # Настраиваем метод to_egl_json() для корректной сериализации в EGL JSON
        mock_protocol.to_egl_json.return_value = {
            "metadata": {"title": "Test Meeting", "date": "2025-01-01"},
            "summary": "Test summary",
            "decisions": ["Decision 1"],
            "actions": [{"assignee": "John", "description": "Task 1", "due_date": "2025-01-01"}]
        }
        mock_analysis_service.process_transcript.return_value = (mock_protocol, "# Test Markdown")
        
        mock_protocol_service.create_protocol_from_segments.return_value = mock_protocol
        
        mock_notification_service.is_enabled.return_value = True
        mock_notification_service.send_protocol_files.return_value = True
        
        # Создаем Pipeline
        pipeline = Pipeline(
            asr_service=mock_asr_service,
            analysis_service=mock_analysis_service,
            protocol_service=mock_protocol_service,
            notification_service=mock_notification_service
        )
        
        # Создаем временный файл и директорию
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio_file, \
             tempfile.TemporaryDirectory() as output_dir_str:
            
            audio_path = Path(audio_file.name)
            output_dir = Path(output_dir_str)
            
            # Вызываем метод process_audio
            md_file, json_file = pipeline.process_audio(
                audio_path=audio_path,
                output_dir=output_dir,
                language="en",
                meeting_info={"title": "Test Meeting", "date": "2025-01-01"},
                skip_notifications=False
            )
            
            # Проверяем, что вызвались нужные методы сервисов
            mock_asr_service.transcribe.assert_called_once_with(audio_path, "en")
            mock_analysis_service.process_transcript.assert_called_once()
            mock_notification_service.send_protocol_files.assert_called_once()
            
            # Проверяем, что файлы были созданы
            assert md_file.exists()
            assert json_file.exists()
    
    def test_pipeline_process_audio_skip_notifications(self):
        """Проверка метода process_audio со skip_notifications=True"""
        # Настраиваем мок-сервисы
        mock_asr_service = MagicMock()
        mock_analysis_service = MagicMock()
        mock_protocol_service = MagicMock()
        mock_notification_service = MagicMock()
        
        # Настраиваем возвращаемые значения
        mock_asr_service.transcribe.return_value = [
            {"text": "Hello", "start": 0.0, "end": 1.0, "speaker": "SPEAKER_01"},
            {"text": "World", "start": 1.0, "end": 2.0, "speaker": "SPEAKER_02"}
        ]
        
        mock_protocol = MagicMock()
        mock_protocol.metadata = {"title": "Test Meeting", "date": "2025-01-01"}
        # Настраиваем метод to_dict() для корректной сериализации в JSON
        mock_protocol.to_dict.return_value = {
            "metadata": {"title": "Test Meeting", "date": "2025-01-01"},
            "summary": "Test summary",
            "decisions": ["Decision 1"],
            "action_items": [{"who": "John", "what": "Task 1", "due": "2025-01-01"}],
            "participants": [{"name": "John", "role": "Speaker"}],
            "agenda_items": [{"title": "Agenda 1", "summary": "Agenda summary"}]
        }
        # Настраиваем метод to_egl_json() для корректной сериализации в EGL JSON
        mock_protocol.to_egl_json.return_value = {
            "metadata": {"title": "Test Meeting", "date": "2025-01-01"},
            "summary": "Test summary",
            "decisions": ["Decision 1"],
            "actions": [{"assignee": "John", "description": "Task 1", "due_date": "2025-01-01"}]
        }
        mock_analysis_service.process_transcript.return_value = (mock_protocol, "# Test Markdown")
        
        mock_protocol_service.create_protocol_from_segments.return_value = mock_protocol
        
        # Создаем Pipeline
        pipeline = Pipeline(
            asr_service=mock_asr_service,
            analysis_service=mock_analysis_service,
            protocol_service=mock_protocol_service,
            notification_service=mock_notification_service
        )
        
        # Создаем временный файл и директорию
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio_file, \
             tempfile.TemporaryDirectory() as output_dir_str:
            
            audio_path = Path(audio_file.name)
            output_dir = Path(output_dir_str)
            
            # Вызываем метод process_audio с skip_notifications=True
            md_file, json_file = pipeline.process_audio(
                audio_path=audio_path,
                output_dir=output_dir,
                language="en",
                meeting_info={"title": "Test Meeting", "date": "2025-01-01"},
                skip_notifications=True
            )
            
            # Проверяем, что вызвались нужные методы сервисов (кроме уведомлений)
            mock_asr_service.transcribe.assert_called_once_with(audio_path, "en")
            mock_analysis_service.process_transcript.assert_called_once()
            mock_notification_service.send_protocol_files.assert_not_called()

if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
