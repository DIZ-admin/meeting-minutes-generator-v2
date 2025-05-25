"""
Тесты для AudioFileProcessor - основного сервиса CLI
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

from app.cli_services.file_processor import AudioFileProcessor, MetadataBuilder
from app.core.services.pipeline import Pipeline

class TestAudioFileProcessor:
    """Тесты для AudioFileProcessor"""
    
    @pytest.fixture
    def mock_pipeline(self):
        """Мок Pipeline для тестирования"""
        pipeline = Mock(spec=Pipeline)
        return pipeline
    
    @pytest.fixture
    def processor(self, mock_pipeline):
        """Экземпляр AudioFileProcessor с мок Pipeline"""
        return AudioFileProcessor(mock_pipeline)
    
    @pytest.fixture
    def temp_audio_file(self):
        """Временный аудиофайл для тестирования"""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b'fake audio data')
            temp_path = Path(f.name)
        
        yield temp_path
        
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()
    
    @pytest.fixture
    def temp_transcript_file(self):
        """Временный JSON файл транскрипта"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"transcript": "test transcript"}')
            temp_path = Path(f.name)
        
        yield temp_path
        
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()
    
    def test_process_single_file_success(self, processor, mock_pipeline, temp_audio_file):
        """Тест успешной обработки одного файла"""
        # Arrange
        expected_md = Path("/fake/output.md")
        expected_json = Path("/fake/output.json")
        mock_pipeline.process_audio.return_value = (expected_md, expected_json)
        
        metadata = {"title": "Test Meeting"}
        
        # Act
        success, md_file, json_file, error_msg = processor.process_single_file(
            audio_path=temp_audio_file,
            metadata=metadata
        )
        
        # Assert
        assert success is True
        assert md_file == expected_md
        assert json_file == expected_json
        assert error_msg is None