"""
Тесты для извлечения метаданных в Pipeline
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from pathlib import Path

from app.core.services.pipeline import Pipeline

class TestPipelineMetadata:
    """Тесты для метода _extract_metadata в классе Pipeline"""
    
    @patch('app.core.services.asr_service.ASRService')
    @patch('app.core.services.analysis_service.MapReduceService')
    @patch('app.core.services.protocol_service.ProtocolService')
    @patch('app.core.services.notification_service.NotificationService')
    def test_extract_metadata_with_date_in_filename(self, mock_notification, mock_protocol, mock_analysis, mock_asr):
        """Проверка извлечения метаданных, когда дата есть в имени файла"""
        # Настраиваем моки для сервисов
        mock_asr.return_value = MagicMock()
        mock_analysis.return_value = MagicMock()
        mock_protocol.return_value = MagicMock()
        mock_notification.return_value = MagicMock()
        
        # Создаем экземпляр Pipeline с мокированными сервисами
        pipeline = Pipeline()
        
        # Тестируем извлечение метаданных из имени файла с датой
        filename = "meeting_eGL_2024-07-15_extra_info"
        metadata = pipeline._extract_metadata(filename)
        
        # Проверяем извлеченные метаданные
        assert metadata["date"] == "2024-07-15"
        assert "Meeting Egl Extra Info" in metadata["title"]
    
    @patch('app.core.services.pipeline.datetime')
    @patch('app.core.services.asr_service.ASRService')
    @patch('app.core.services.analysis_service.MapReduceService')
    @patch('app.core.services.protocol_service.ProtocolService')
    @patch('app.core.services.notification_service.NotificationService')
    def test_extract_metadata_no_date_in_filename(self, mock_notification, mock_protocol, mock_analysis, mock_asr, mock_datetime):
        """Проверка извлечения метаданных, когда даты нет в имени файла (используется текущая)"""
        # Мокируем datetime.now()
        mock_now = MagicMock()
        mock_now.strftime.return_value = "2023-10-20"
        mock_datetime.now.return_value = mock_now
        
        # Настраиваем моки для сервисов
        mock_asr.return_value = MagicMock()
        mock_analysis.return_value = MagicMock()
        mock_protocol.return_value = MagicMock()
        mock_notification.return_value = MagicMock()
        
        # Создаем экземпляр Pipeline с мокированными сервисами
        pipeline = Pipeline()
        
        # Тестируем извлечение метаданных из имени файла без даты
        filename = "random_meeting_audio"
        metadata = pipeline._extract_metadata(filename)
        
        # Проверяем извлеченные метаданные
        assert metadata["date"] == "2023-10-20"
        assert "Random Meeting Audio" in metadata["title"]
    
    @patch('app.core.services.asr_service.ASRService')
    @patch('app.core.services.analysis_service.MapReduceService')
    @patch('app.core.services.protocol_service.ProtocolService')
    @patch('app.core.services.notification_service.NotificationService')
    def test_extract_metadata_empty_filename(self, mock_notification, mock_protocol, mock_analysis, mock_asr):
        """Проверка извлечения метаданных из пустого имени файла"""
        # Настраиваем моки для сервисов
        mock_asr.return_value = MagicMock()
        mock_analysis.return_value = MagicMock()
        mock_protocol.return_value = MagicMock()
        mock_notification.return_value = MagicMock()
        
        # Создаем экземпляр Pipeline с мокированными сервисами
        pipeline = Pipeline()
        
        # Тестируем извлечение метаданных из пустого имени файла
        filename = ""
        metadata = pipeline._extract_metadata(filename)
        
        # Проверяем, что метаданные содержат значения по умолчанию
        assert "date" in metadata
        assert metadata["title"] == "Meeting Protocol"
        assert metadata["location"] == "Online Meeting"
        assert metadata["author"] == "AI Assistant"

if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
