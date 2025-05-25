"""
Тесты для WebFileProcessor и WebTaskManager
"""
import pytest
import asyncio
import tempfile  
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.web_services.file_processor import WebFileProcessor, WebTaskManager, WebMetadataBuilder
from app.core.services.pipeline import Pipeline

class TestWebFileProcessor:
    """Тесты для WebFileProcessor"""
    
    @pytest.fixture
    def mock_pipeline(self):
        """Мок Pipeline для тестирования"""
        pipeline = Mock(spec=Pipeline)
        return pipeline
    
    @pytest.fixture  
    def processor(self, mock_pipeline):
        """Экземпляр WebFileProcessor с мок Pipeline"""
        return WebFileProcessor(mock_pipeline)
    
    @pytest.fixture
    def temp_audio_file(self):
        """Временный аудиофайл для тестирования"""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b'fake audio data')
            temp_path = Path(f.name)
        
        yield temp_path
        
        if temp_path.exists():
            temp_path.unlink()
    
    @pytest.mark.asyncio
    async def test_process_audio_async_success(self, processor, mock_pipeline, temp_audio_file):
        """Тест успешной асинхронной обработки аудио"""
        # Arrange
        expected_md = Path("/fake/output.md")
        expected_json = Path("/fake/output.json")
        mock_pipeline.process_audio.return_value = (expected_md, expected_json)
        
        metadata = {"title": "Test Meeting"}
        
        # Act
        success, md_file, json_file, error_msg = await processor.process_audio_async(
            file_path=temp_audio_file,
            metadata=metadata
        )
        
        # Assert
        assert success is True
        assert md_file == expected_md
        assert json_file == expected_json
        assert error_msg is None
    
    @pytest.mark.asyncio
    async def test_process_audio_async_with_progress(self, processor, mock_pipeline, temp_audio_file):
        """Тест асинхронной обработки с progress callback"""
        # Arrange
        expected_md = Path("/fake/output.md")
        expected_json = Path("/fake/output.json")
        mock_pipeline.process_audio.return_value = (expected_md, expected_json)
        
        progress_calls = []
        
        def progress_callback(stage: str, percent: float, message: str):
            progress_calls.append((stage, percent, message))
        
        # Act
        success, md_file, json_file, error_msg = await processor.process_audio_async(
            file_path=temp_audio_file,
            progress_callback=progress_callback
        )
        
        # Assert
        assert success is True
        assert len(progress_calls) >= 2  # At least initializing and completed
        assert progress_calls[0][0] == "initializing"
        assert progress_calls[-1][0] == "completed"
