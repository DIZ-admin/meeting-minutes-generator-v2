"""
Интеграционные тесты для Meeting Protocol Generator
"""
import pytest
import tempfile
import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, Any, List

# Добавляем родительскую директорию в путь импорта
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

@pytest.fixture
def temp_audio_file():
    """Создает временный 'аудио' файл для тестов"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        # Простые fake WAV данные
        f.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xAC\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
        path = Path(f.name)
    
    yield path
    
    # Cleanup
    if path.exists():
        path.unlink()

@pytest.fixture
def temp_output_dir():
    """Создает временную директорию для выходных файлов"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)

@pytest.fixture
def mock_asr_response():
    """Мок ответ для ASR сервиса"""
    return [
        {
            "text": "Hello, welcome to the meeting.",
            "start": 0.0,
            "end": 3.0,
            "speaker_id": "SPEAKER_00",
            "speaker_confidence": 0.95
        },
        {
            "text": "Today we will discuss the project status.",
            "start": 3.0,
            "end": 7.0,
            "speaker_id": "SPEAKER_00",
            "speaker_confidence": 0.9
        },
        {
            "text": "We need to update the roadmap by next week.",
            "start": 7.0,
            "end": 11.0,
            "speaker_id": "SPEAKER_01",
            "speaker_confidence": 0.85
        }
    ]

@pytest.fixture
def mock_llm_response():
    """Мок ответ для LLM сервиса"""
    return {
        "summary": "Meeting about project status and roadmap updates",
        "decisions": [
            {
                "decision": "Update project roadmap",
                "context": "Current roadmap needs revision to reflect new priorities"
            }
        ],
        "actions": [
            {
                "action": "Update roadmap document",
                "assignee": "Project Manager",
                "due_date": "Next week",
                "context": "Priority update for Q2 planning"
            }
        ]
    }

class TestPipelineIntegration:
    """Интеграционные тесты для Pipeline"""
    
    @patch('app.adapters.asr.replicate_adapter.ReplicateASRAdapter.transcribe')
    @patch('app.adapters.llm.openai_adapter.OpenAILLMAdapter.generate_json')
    def test_pipeline_end_to_end_mock(
        self, 
        mock_llm_generate, 
        mock_asr_transcribe,
        temp_audio_file,
        temp_output_dir,
        mock_asr_response,
        mock_llm_response
    ):
        """Тестирует полный pipeline с моками"""
        try:
            from app.core.services.pipeline import Pipeline
            
            # Настройка моков
            mock_asr_transcribe.return_value = mock_asr_response
            mock_llm_generate.return_value = mock_llm_response
            
            # Создание pipeline
            pipeline = Pipeline()
            
            # Метаданные встречи
            meeting_info = {
                "title": "Test Meeting",
                "date": "2025-05-22",
                "location": "Online",
                "organizer": "Test Organizer"
            }
            
            # Выполнение обработки
            md_file, json_file = pipeline.process_audio(
                audio_path=temp_audio_file,
                output_dir=temp_output_dir,
                language="en",
                meeting_info=meeting_info,
                skip_notifications=True
            )
            
            # Проверки
            assert md_file.exists(), "Markdown file was not created"
            assert json_file.exists(), "JSON file was not created"
            
            # Проверяем содержимое markdown файла
            md_content = md_file.read_text(encoding="utf-8")
            assert "Test Meeting" in md_content
            assert "2025-05-22" in md_content
            
            # Проверяем содержимое JSON файла
            json_content = json.loads(json_file.read_text(encoding="utf-8"))
            assert "metadata" in json_content
            assert json_content["metadata"]["title"] == "Test Meeting"
            
            # Проверяем что ASR и LLM были вызваны
            mock_asr_transcribe.assert_called_once()
            mock_llm_generate.assert_called()
            
        except ImportError:
            pytest.skip("Pipeline components not available")
    
    @pytest.mark.skip("Config validation test needs refactoring - API keys loaded from .env")
    def test_pipeline_config_validation(self):
        """Тестирует валидацию конфигурации в Pipeline"""
        # TODO: Переделать тест чтобы он работал с загруженной из .env конфигурацией
        pass
    
    @patch('app.adapters.asr.replicate_adapter.ReplicateASRAdapter.transcribe')
    def test_pipeline_caching_integration(
        self,
        mock_asr_transcribe,
        temp_audio_file,
        temp_output_dir,
        mock_asr_response
    ):
        """Тестирует интеграцию кеширования в Pipeline"""
        try:
            from app.core.services.pipeline import Pipeline
            from app.utils.cache import get_cache
            
            # Настройка мока
            mock_asr_transcribe.return_value = mock_asr_response
            
            pipeline = Pipeline()
            cache = get_cache()
            
            # Очищаем кеш перед тестом
            cache.clear_namespace("asr")
            
            # Первый вызов - должен попасть в кеш
            pipeline.asr_service.transcribe(
                temp_audio_file,
                language="en",
                use_cache=True
            )
            
            # Второй вызов - должен взять из кеша
            result2 = pipeline.asr_service.transcribe(
                temp_audio_file,
                language="en", 
                use_cache=True
            )
            
            # ASR должен быть вызван только один раз (второй раз из кеша)
            assert mock_asr_transcribe.call_count == 1
            assert result2 == mock_asr_response
            
        except ImportError:
            pytest.skip("Pipeline or cache not available")

class TestWebInterfaceIntegration:
    """Интеграционные тесты для веб-интерфейса"""
    
    @pytest.fixture
    def client(self):
        """Создает тестовый клиент FastAPI"""
        try:
            from fastapi.testclient import TestClient
            from app.web.app import app
            
            return TestClient(app)
        except ImportError:
            pytest.skip("FastAPI or web app not available")
    
    def test_health_endpoint(self, client):
        """Тестирует health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "components" in data
        assert "version" in data
    
    def test_cache_stats_endpoint(self, client):
        """Тестирует endpoint статистики кеша"""
        response = client.get("/api/v1/cache/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert "healthy" in data
        assert "timestamp" in data
        assert "redis_available" in data
    
    def test_cache_clear_endpoint(self, client):
        """Тестирует endpoint очистки кеша"""
        response = client.post("/api/v1/cache/clear")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "message" in data
    
    @patch('app.core.services.pipeline.Pipeline')
    def test_upload_audio_endpoint(self, mock_pipeline_class, client, temp_audio_file):
        """Тестирует endpoint загрузки аудио"""
        # Настройка мока
        mock_pipeline = MagicMock()
        mock_pipeline_class.return_value = mock_pipeline
        
        # Открываем файл для загрузки
        with open(temp_audio_file, "rb") as f:
            response = client.post(
                "/api/upload",
                files={"file": ("test.wav", f, "audio/wav")},
                data={
                    "title": "Test Meeting",
                    "language": "en"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "message" in data

class TestAdaptersIntegration:
    """Интеграционные тесты для адаптеров"""
    
    def test_asr_adapter_initialization(self):
        """Тестирует инициализацию ASR адаптеров"""
        try:
            from app.adapters.asr.replicate_adapter import ReplicateASRAdapter
            from app.adapters.asr.openai_adapter import OpenAIASRAdapter
            
            # Проверяем что адаптеры можно создать (даже без API ключей)
            with patch.dict(os.environ, {"REPLICATE_API_TOKEN": "test_token"}):
                replicate_adapter = ReplicateASRAdapter()
                assert replicate_adapter is not None
            
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
                openai_adapter = OpenAIASRAdapter()
                assert openai_adapter is not None
                
        except ImportError:
            pytest.skip("ASR adapters not available")
    
    def test_llm_adapter_initialization(self):
        """Тестирует инициализацию LLM адаптеров"""
        try:
            from app.adapters.llm.openai_adapter import OpenAILLMAdapter
            from app.adapters.llm.async_openai_adapter import AsyncOpenAILLMAdapter
            
            # Проверяем что адаптеры можно создать
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
                sync_adapter = OpenAILLMAdapter()
                assert sync_adapter is not None
                
                async_adapter = AsyncOpenAILLMAdapter()
                assert async_adapter is not None
                
        except ImportError:
            pytest.skip("LLM adapters not available")
    
    @patch('app.adapters.llm.openai_adapter.OpenAI')
    def test_llm_adapter_caching(self, mock_openai_class):
        """Тестирует кеширование в LLM адаптере"""
        try:
            from app.adapters.llm.openai_adapter import OpenAILLMAdapter
            from app.utils.cache import get_cache
            
            # Настройка мока
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            
            mock_completion = MagicMock()
            mock_choice = MagicMock()
            mock_message = MagicMock()
            mock_message.content = "Test response"
            mock_choice.message = mock_message
            mock_completion.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_completion
            
            # Создаем адаптер
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
                adapter = OpenAILLMAdapter()
            
            cache = get_cache()
            cache.clear_namespace("llm")
            
            # Первый вызов - низкая температура для кеширования
            result1 = adapter.generate_text(
                prompt="Test prompt",
                temperature=0.2,
                use_cache=True
            )
            
            # Второй вызов - должен взять из кеша
            result2 = adapter.generate_text(
                prompt="Test prompt", 
                temperature=0.2,
                use_cache=True
            )
            
            assert result1 == result2 == "Test response"
            # OpenAI API должен быть вызван только один раз
            assert mock_client.chat.completions.create.call_count == 1
            
        except ImportError:
            pytest.skip("LLM adapter not available")

class TestErrorHandling:
    """Тесты обработки ошибок"""
    
    def test_config_error_handling(self):
        """Тестирует обработку ошибок конфигурации"""
        try:
            from app.core.exceptions import ConfigError
            from app.utils.config_validator import ConfigValidator
            from app.config.config import AppConfig
            
            # Создаем мок-конфигурацию с отсутствующими API ключами
            class MockConfig:
                def __init__(self):
                    self.openai_api_key = None
                    self.replicate_api_token = None
                    self.default_lang = "en"
                    self.output_dir = Path("/tmp/test_output")
                    self.cache_dir = Path("/tmp/test_cache")
                    self.log_dir = Path("/tmp/test_logs")
                    
            mock_config = MockConfig()
            validator = ConfigValidator(mock_config)
            
            with pytest.raises(ConfigError):
                validator.validate_all()
                    
        except ImportError:
            pytest.skip("Config validation not available")
    
    def test_asr_error_handling(self):
        """Тестирует обработку ошибок ASR"""
        try:
            from app.core.exceptions import ASRError
            from app.core.services.asr_service import ASRService
            from app.adapters.asr.base import ASRAdapter
            
            # Создаем мок адаптер который всегда падает
            class FailingASRAdapter(ASRAdapter):
                def transcribe(self, audio_path, language=None, **kwargs):
                    raise Exception("Mock ASR failure")
                
                def get_adapter_info(self):
                    return {"name": "FailingAdapter"}
            
            service = ASRService(adapter=FailingASRAdapter())
            
            with pytest.raises(ASRError):
                service.transcribe("fake_path.wav")
                
        except ImportError:
            pytest.skip("ASR components not available")
    
    def test_retry_mechanism(self):
        """Тестирует retry механизм"""
        try:
            from app.utils.retry import retry_sync, RetryConfig
            
            call_count = 0
            
            @retry_sync(RetryConfig(max_attempts=3, base_delay=0.01))
            def flaky_function():
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ConnectionError("Temporary failure")
                return "success"
            
            result = flaky_function()
            assert result == "success"
            assert call_count == 3
            
        except ImportError:
            pytest.skip("Retry utils not available")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
