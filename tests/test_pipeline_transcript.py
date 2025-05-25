"""
Тесты для метода process_transcript_json класса Pipeline
"""
import os
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.services.pipeline import Pipeline
from app.core.models.transcript import Transcript, TranscriptSegment
from app.core.models.protocol import Protocol
from app.core.exceptions import LLMError, ValidationError

class TestPipelineTranscript:
    """Тесты для обработки транскриптов в Pipeline"""
    
    @pytest.fixture
    def mock_services(self):
        """Фикстура для создания моков сервисов"""
        asr_service = MagicMock()
        protocol_service = MagicMock()
        notification_service = MagicMock()
        
        # Настраиваем protocol_service для возврата протокола
        protocol = Protocol(
            metadata={"title": "Test Meeting", "date": "2025-05-24"},
            summary="Test summary",
            decisions=["Decision 1"],
            action_items=["Action 1"],
            participants=[],
            agenda_items=[]
        )
        protocol_service.create_protocol_from_segments.return_value = protocol
        
        return asr_service, protocol_service, notification_service
    
    @pytest.fixture
    def sample_transcript_path(self, tmp_path):
        """Создает временный файл транскрипта для тестирования"""
        transcript_data = [
            {
                "speaker": "Speaker 1",
                "text": "Hello, this is a test transcript.",
                "start": 0.0,
                "end": 5.0
            },
            {
                "speaker": "Speaker 2",
                "text": "Yes, we are testing the pipeline.",
                "start": 5.5,
                "end": 10.0
            }
        ]
        
        transcript_path = tmp_path / "test_transcript.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f)
        
        return transcript_path
    
    @pytest.fixture
    def sample_complex_transcript_path(self, tmp_path):
        """Создает временный файл транскрипта в формате с segments для тестирования"""
        transcript_data = {
            "metadata": {
                "title": "Complex Test",
                "date": "2025-05-24"
            },
            "language": "en",
            "segments": [
                {
                    "speaker": "Speaker 1",
                    "text": "This is a complex transcript format.",
                    "start": 0.0,
                    "end": 5.0
                },
                {
                    "speaker": "Speaker 2",
                    "text": "It has metadata and language fields.",
                    "start": 5.5,
                    "end": 10.0
                }
            ]
        }
        
        transcript_path = tmp_path / "complex_transcript.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f)
        
        return transcript_path
    
    def test_successful_transcript_processing(self, mock_services, sample_transcript_path, tmp_path):
        """Тест успешной обработки транскрипта"""
        asr_service, protocol_service, notification_service = mock_services
        
        # Создаем экземпляр Pipeline с моками
        pipeline = Pipeline(
            asr_service=asr_service,
            protocol_service=protocol_service,
            notification_service=notification_service
        )
        
        # Создаем директорию для выходных файлов
        output_dir = tmp_path / "output"
        
        # Обрабатываем транскрипт
        md_file, json_file = pipeline.process_transcript_json(
            transcript_path=sample_transcript_path,
            output_dir=output_dir,
            language="en",
            meeting_info={"title": "Test Meeting"},
            skip_notifications=True
        )
        
        # Проверяем, что файлы созданы
        assert md_file.exists()
        assert json_file.exists()
        
        # Проверяем, что метод create_protocol_from_segments был вызван
        protocol_service.create_protocol_from_segments.assert_called_once()
        
        # Проверяем, что notification_service не вызывался (skip_notifications=True)
        notification_service.send_protocol_files.assert_not_called()
    
    def test_complex_transcript_format(self, mock_services, sample_complex_transcript_path, tmp_path):
        """Тест обработки транскрипта в сложном формате с метаданными"""
        asr_service, protocol_service, notification_service = mock_services
        
        # Создаем экземпляр Pipeline с моками
        pipeline = Pipeline(
            asr_service=asr_service,
            protocol_service=protocol_service,
            notification_service=notification_service
        )
        
        # Создаем директорию для выходных файлов
        output_dir = tmp_path / "output"
        
        # Проверяем содержимое транскрипта
        with open(sample_complex_transcript_path, "r", encoding="utf-8") as f:
            transcript_data = json.load(f)
            assert transcript_data["language"] == "en"
            assert transcript_data["metadata"]["title"] == "Complex Test"
        
        # Обрабатываем транскрипт
        md_file, json_file = pipeline.process_transcript_json(
            transcript_path=sample_complex_transcript_path,
            output_dir=output_dir,
            skip_notifications=True
        )
        
        # Проверяем, что файлы созданы
        assert md_file.exists()
        assert json_file.exists()
        
        # Проверяем, что метод create_protocol_from_segments был вызван
        protocol_service.create_protocol_from_segments.assert_called_once()
        
        # Проверяем, что файлы созданы с правильными именами
        # В нашем тесте мы используем мок для protocol_service, который возвращает фиксированный заголовок "Test Meeting"
        assert "Test_Meeting" in md_file.name
    
    def test_error_handling_in_protocol_creation(self, mock_services, sample_transcript_path, tmp_path):
        """Тест обработки ошибок при создании протокола"""
        asr_service, protocol_service, notification_service = mock_services
        
        # Настраиваем protocol_service для генерации ошибки
        protocol_service.create_protocol_from_segments.side_effect = LLMError("Test error")
        
        # Создаем экземпляр Pipeline с моками
        pipeline = Pipeline(
            asr_service=asr_service,
            protocol_service=protocol_service,
            notification_service=notification_service
        )
        
        # Создаем директорию для выходных файлов
        output_dir = tmp_path / "output"
        
        # Обрабатываем транскрипт (должен создать протокол с ошибкой)
        md_file, json_file = pipeline.process_transcript_json(
            transcript_path=sample_transcript_path,
            output_dir=output_dir,
            language="en",
            skip_notifications=True
        )
        
        # Проверяем, что файлы созданы, несмотря на ошибку
        assert md_file.exists()
        assert json_file.exists()
        
        # Проверяем, что в файле содержится информация об ошибке
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Failed to generate protocol content due to error" in content
    
    def test_save_intermediates(self, mock_services, sample_transcript_path, tmp_path):
        """Тест сохранения промежуточных результатов"""
        asr_service, protocol_service, notification_service = mock_services
        
        # Настраиваем map_reduce_service для protocol_service
        map_reduce_service = MagicMock()
        map_reduce_service.process_map_stage.return_value = [{"result": "map result"}]
        map_reduce_service.process_reduce_stage.return_value = {"result": "reduce result"}
        protocol_service.map_reduce_service = map_reduce_service
        
        # Создаем экземпляр Pipeline с моками
        pipeline = Pipeline(
            asr_service=asr_service,
            protocol_service=protocol_service,
            notification_service=notification_service
        )
        
        # Создаем директорию для выходных файлов
        output_dir = tmp_path / "output"
        
        # Обрабатываем транскрипт с сохранением промежуточных результатов
        md_file, json_file = pipeline.process_transcript_json(
            transcript_path=sample_transcript_path,
            output_dir=output_dir,
            language="en",
            skip_notifications=True,
            save_intermediates=True
        )
        
        # Проверяем, что промежуточные файлы созданы
        assert (output_dir / "transcript.json").exists()
        assert (output_dir / "map_results.json").exists()
        assert (output_dir / "reduce_results.json").exists()
        
        # Проверяем содержимое файлов
        with open(output_dir / "map_results.json", "r", encoding="utf-8") as f:
            map_data = json.load(f)
            assert map_data == [{"result": "map result"}]
        
        with open(output_dir / "reduce_results.json", "r", encoding="utf-8") as f:
            reduce_data = json.load(f)
            assert reduce_data == {"result": "reduce result"}
    
    def test_progress_callback(self, mock_services, sample_transcript_path, tmp_path):
        """Тест функции обратного вызова для отслеживания прогресса"""
        asr_service, protocol_service, notification_service = mock_services
        
        # Создаем экземпляр Pipeline с моками
        pipeline = Pipeline(
            asr_service=asr_service,
            protocol_service=protocol_service,
            notification_service=notification_service
        )
        
        # Создаем директорию для выходных файлов
        output_dir = tmp_path / "output"
        
        # Создаем мок для функции обратного вызова
        progress_callback = MagicMock()
        
        # Обрабатываем транскрипт
        pipeline.process_transcript_json(
            transcript_path=sample_transcript_path,
            output_dir=output_dir,
            language="en",
            skip_notifications=True,
            progress_callback=progress_callback
        )
        
        # Проверяем, что функция обратного вызова была вызвана с разными этапами
        assert progress_callback.call_count >= 5
        
        # Проверяем, что первый вызов был с инициализацией
        args, kwargs = progress_callback.call_args_list[0]
        assert args[0] == "Инициализация"
        assert args[1] == 0.01
        
        # Проверяем, что последний вызов был с завершением
        args, kwargs = progress_callback.call_args_list[-1]
        assert args[0] == "Завершено"
        assert args[1] == 1.0
