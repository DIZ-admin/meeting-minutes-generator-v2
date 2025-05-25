"""
Интеграционные тесты для Pipeline
"""
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, parent_dir)

from app.core.services.pipeline import Pipeline

class TestPipelineIntegration:
    """Интеграционные тесты для Pipeline"""

    @patch('app.core.services.pipeline.ASRService')
    @patch('app.core.services.pipeline.MapReduceService')
    @patch('app.core.services.pipeline.ProtocolService')
    @patch('app.core.services.pipeline.NotificationService')
    def test_pipeline_initialization(self, mock_notification_service, mock_protocol_service, 
                                    mock_analysis_service, mock_asr_service):
        """Тестирование инициализации Pipeline"""
        # Настройка моков
        mock_asr_service_instance = mock_asr_service.return_value
        mock_analysis_service_instance = mock_analysis_service.return_value
        mock_protocol_service_instance = mock_protocol_service.return_value
        mock_notification_service_instance = mock_notification_service.return_value
        
        # Создаем экземпляр Pipeline
        pipeline = Pipeline(
            asr_service=mock_asr_service_instance,
            analysis_service=mock_analysis_service_instance,
            protocol_service=mock_protocol_service_instance,
            notification_service=mock_notification_service_instance
        )
        
        # Проверки
        assert pipeline is not None
        assert pipeline.asr_service == mock_asr_service_instance
        assert pipeline.analysis_service == mock_analysis_service_instance
        assert pipeline.protocol_service == mock_protocol_service_instance
        assert pipeline.notification_service == mock_notification_service_instance

    @patch('app.core.services.pipeline.Path.exists')
    def test_pipeline_file_not_found(self, mock_exists):
        """Тестирование обработки ошибки отсутствия файла в Pipeline"""
        # Настройка мока для имитации отсутствия файла
        mock_exists.return_value = False
        
        # Создаем экземпляр Pipeline с моками
        pipeline = Pipeline(
            asr_service=MagicMock(),
            analysis_service=MagicMock(),
            protocol_service=MagicMock(),
            notification_service=MagicMock()
        )
        
        # Мокируем метод _extract_meeting_info
        pipeline._extract_meeting_info = MagicMock(return_value={
            "title": "Test Meeting",
            "date": "2025-05-20",
            "location": "Online Meeting",
            "organizer": "",
            "author": "AI Assistant"
        })
        
        # Вызов метода process_audio и проверка, что исключение обрабатывается
        with pytest.raises(FileNotFoundError):
            pipeline.process_audio(
                audio_path=Path("/path/to/nonexistent/audio.mp3"),
                output_dir=Path("/tmp/output")
            )
