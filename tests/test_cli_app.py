"""
Тесты для CLI приложения
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

from app.cli import prepare_metadata, process_single_file, process_batch
from app.core.services.pipeline import Pipeline
from app.core.exceptions import ASRError, LLMError, ConfigError

class TestPrepareMetadata:
    """Тесты для функции prepare_metadata"""
    
    def test_prepare_metadata_defaults(self):
        """Проверка значений по умолчанию для метаданных"""
        # Создаем мок для args с минимальными параметрами
        args = MagicMock()
        args.title = None
        args.date = None
        args.location = None
        args.organizer = None
        args.participants = None
        args.agenda = None
        
        # Вызываем функцию prepare_metadata
        metadata = prepare_metadata(args)
        
        # Проверяем, что метаданные содержат ожидаемые значения по умолчанию
        assert "author" in metadata
        assert metadata["author"] == "AI Assistant"
    
    def test_prepare_metadata_custom_values(self):
        """Проверка пользовательских значений для метаданных"""
        # Создаем мок для args с пользовательскими параметрами
        args = MagicMock()
        args.title = "Test Meeting"
        args.date = "2025-05-20"
        args.location = "Conference Room"
        args.organizer = "John Doe"
        args.participants = "Alice,Bob,Charlie"
        args.agenda = None
        
        # Вызываем функцию prepare_metadata
        metadata = prepare_metadata(args)
        
        # Проверяем, что метаданные содержат пользовательские значения
        assert metadata["title"] == "Test Meeting"
        assert metadata["date"] == "2025-05-20"
        assert metadata["location"] == "Conference Room"
        assert metadata["organizer"] == "John Doe"
        assert "author" in metadata
        assert metadata["author"] == "AI Assistant"

class TestProcessSingleFile:
    """Тесты для функции process_single_file"""
    
    def test_process_single_file_nonexistent_file(self):
        """Проверка обработки несуществующего файла"""
        # Создаем моки для параметров
        mock_pipeline = MagicMock()
        # Настраиваем process_audio, чтобы он вызывал ошибку
        mock_pipeline.process_audio.side_effect = Exception("File not found")
        
        audio_path = Path("/path/to/nonexistent.wav")
        output_dir = None
        language = "en"
        metadata = {"title": "Test Meeting"}
        skip_notifications = True
        
        # Вызываем функцию process_single_file
        result = process_single_file(
            pipeline=mock_pipeline,
            audio_path=audio_path,
            output_dir=output_dir,
            language=language,
            metadata=metadata,
            skip_notifications=skip_notifications
        )
        
        # Проверяем, что функция вернула False (ошибка)
        assert result is False
    
    @patch("app.cli.Path.exists")
    def test_process_single_file_success(self, mock_exists):
        """Проверка успешной обработки файла"""
        # Настраиваем мок для проверки существования файла
        mock_exists.return_value = True
        
        # Создаем моки для параметров
        mock_pipeline = MagicMock()
        mock_pipeline.process_audio.return_value = (Path("/path/to/output.md"), Path("/path/to/output.json"))
        
        audio_path = Path("/path/to/audio.wav")
        output_dir = Path("/path/to/output")
        language = "en"
        metadata = {"title": "Test Meeting"}
        skip_notifications = True
        
        # Вызываем функцию process_single_file
        result = process_single_file(
            pipeline=mock_pipeline,
            audio_path=audio_path,
            output_dir=output_dir,
            language=language,
            metadata=metadata,
            skip_notifications=skip_notifications
        )
        
        # Проверяем, что функция вернула True (успех)
        assert result is True
        # Проверяем, что pipeline.process_audio вызывался с правильными параметрами
        mock_pipeline.process_audio.assert_called_once_with(
            audio_path=audio_path,
            output_dir=output_dir,
            language=language,
            metadata=metadata,
            skip_notifications=skip_notifications
        )
    
    @patch("app.cli.Path.exists")
    def test_process_single_file_pipeline_error(self, mock_exists):
        """Проверка обработки ошибки в pipeline"""
        # Настраиваем мок для проверки существования файла
        mock_exists.return_value = True
        
        # Создаем моки для параметров
        mock_pipeline = MagicMock()
        mock_pipeline.process_audio.side_effect = ASRError("ASR error")
        
        audio_path = Path("/path/to/audio.wav")
        output_dir = Path("/path/to/output")
        language = "en"
        metadata = {"title": "Test Meeting"}
        skip_notifications = True
        
        # Вызываем функцию process_single_file
        result = process_single_file(
            pipeline=mock_pipeline,
            audio_path=audio_path,
            output_dir=output_dir,
            language=language,
            metadata=metadata,
            skip_notifications=skip_notifications
        )
        
        # Проверяем, что функция вернула False (ошибка)
        assert result is False
        # Проверяем, что pipeline.process_audio вызывался
        mock_pipeline.process_audio.assert_called_once()

class TestProcessBatch:
    """Тесты для функции process_batch"""
    
    @patch("app.cli.Path.is_dir")
    def test_process_batch_not_a_directory(self, mock_is_dir):
        """Проверка обработки не-директории"""
        # Настраиваем мок для проверки, является ли путь директорией
        mock_is_dir.return_value = False
        
        # Создаем моки для параметров
        mock_pipeline = MagicMock()
        directory_path = Path("/path/to/not_a_directory")
        output_dir = None
        language = "en"
        metadata = {"title": "Test Meeting"}
        skip_notifications = True
        
        # Вызываем функцию process_batch
        result = process_batch(
            pipeline=mock_pipeline,
            directory_path=directory_path,
            output_dir=output_dir,
            language=language,
            metadata=metadata,
            skip_notifications=skip_notifications
        )
        
        # Проверяем, что функция вернула False (ошибка)
        assert result is False
    
    @patch("app.cli.Path.is_dir")
    @patch("app.cli.Path.iterdir")
    def test_process_batch_no_audio_files(self, mock_iterdir, mock_is_dir):
        """Проверка обработки директории без аудиофайлов"""
        # Настраиваем моки
        mock_is_dir.return_value = True
        mock_iterdir.return_value = []  # Нет файлов в директории
        
        # Создаем моки для параметров
        mock_pipeline = MagicMock()
        directory_path = Path("/path/to/directory")
        output_dir = None
        language = "en"
        metadata = {"title": "Test Meeting"}
        skip_notifications = True
        
        # Вызываем функцию process_batch
        result = process_batch(
            pipeline=mock_pipeline,
            directory_path=directory_path,
            output_dir=output_dir,
            language=language,
            metadata=metadata,
            skip_notifications=skip_notifications
        )
        
        # Проверяем, что функция вернула False (ошибка)
        assert result is False
    
    @patch("app.cli.Path.is_dir")
    @patch("app.cli.Path.iterdir")
    @patch("app.cli.Path.is_file")
    @patch("app.cli.Path.suffix", new_callable=MagicMock)
    def test_process_batch_with_audio_files(self, mock_suffix, mock_is_file, mock_iterdir, mock_is_dir):
        """Проверка обработки директории с аудиофайлами"""
        # Настраиваем моки
        mock_is_dir.return_value = True
        
        # Создаем моки для файлов
        audio_file1 = Path("/path/to/directory/audio1.wav")
        audio_file2 = Path("/path/to/directory/audio2.wav")
        mock_iterdir.return_value = [audio_file1, audio_file2]
        
        # Настраиваем моки для проверки файлов
        mock_is_file.return_value = True
        mock_suffix.lower.return_value = ".wav"
        
        # Создаем моки для параметров
        mock_pipeline = MagicMock()
        mock_pipeline.process_batch.return_value = [(Path("/path/to/output1.md"), Path("/path/to/output1.json")), 
                                                 (Path("/path/to/output2.md"), Path("/path/to/output2.json"))]
        
        directory_path = Path("/path/to/directory")
        output_dir = Path("/path/to/output")
        language = "en"
        metadata = {"title": "Test Meeting"}
        skip_notifications = True
        
        # Вызываем функцию process_batch
        result = process_batch(
            pipeline=mock_pipeline,
            directory_path=directory_path,
            output_dir=output_dir,
            language=language,
            metadata=metadata,
            skip_notifications=skip_notifications
        )
        
        # Проверяем, что функция вернула True (успех)
        assert result is True
        # Проверяем, что pipeline.process_batch вызывался с правильными параметрами
        mock_pipeline.process_batch.assert_called_once()

if __name__ == "__main__":
    pytest.main(["-xvs", __file__])

if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
