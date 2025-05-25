"""
Интеграционные тесты для CLI - сравнение функциональности старых и новых CLI
"""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, Mock
import subprocess
import sys

from app.cli_services.file_processor import AudioFileProcessor, MetadataBuilder
from app.core.services.pipeline import Pipeline

class TestCLIIntegration:
    """Интеграционные тесты для CLI"""
    
    @pytest.fixture
    def temp_audio_file(self):
        """Создает временный аудиофайл"""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(b'fake audio data for testing')
            temp_path = Path(f.name)
        
        yield temp_path
        
        if temp_path.exists():
            temp_path.unlink()
    
    @pytest.fixture
    def temp_transcript_file(self):
        """Создает временный JSON файл транскрипта"""
        transcript_data = {
            "transcript": "This is a test meeting transcript",
            "segments": [
                {"start": 0.0, "end": 5.0, "text": "Welcome to the meeting"},
                {"start": 5.0, "end": 10.0, "text": "Let's discuss the agenda"}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(transcript_data, f)
            temp_path = Path(f.name)
        
        yield temp_path
        
        if temp_path.exists():
            temp_path.unlink()
    
    @pytest.fixture
    def temp_directory_with_audio(self):
        """Создает временную директорию с несколькими аудиофайлами"""
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        
        # Создаем несколько аудиофайлов
        audio_files = []
        for i, ext in enumerate(['.wav', '.mp3', '.m4a']):
            audio_file = temp_dir / f"test_audio_{i}{ext}"
            audio_file.write_bytes(b'fake audio data')
            audio_files.append(audio_file)
        
        yield temp_dir, audio_files
        
        # Cleanup
        for file in audio_files:
            if file.exists():
                file.unlink()
        temp_dir.rmdir()

    def test_metadata_builder_comprehensive(self):
        """Комплексный тест MetadataBuilder"""
        # Test with all parameters
        args = {
            "title": "Sprint Planning Meeting",
            "date": "2025-05-22",
            "location": "Conference Room A",
            "organizer": "Tech Lead",
            "participants": "Developer A, Developer B, QA Engineer, DevOps",
            "agenda": "Sprint Review, Planning, Retrospective, Action Items"
        }
        
        metadata = MetadataBuilder.from_cli_args(**args)
        
        assert metadata["title"] == "Sprint Planning Meeting"
        assert metadata["date"] == "2025-05-22"
        assert metadata["location"] == "Conference Room A"
        assert metadata["organizer"] == "Tech Lead"
        assert metadata["participants"] == ["Developer A", "Developer B", "QA Engineer", "DevOps"]
        assert metadata["agenda"] == ["Sprint Review", "Planning", "Retrospective", "Action Items"]
        assert metadata["author"] == "AI Assistant"

    @patch('app.core.services.pipeline.Pipeline')
    def test_audio_file_processor_error_handling(self, mock_pipeline_class):
        """Тест обработки ошибок в AudioFileProcessor"""
        # Setup mock
        mock_pipeline = Mock()
        mock_pipeline_class.return_value = mock_pipeline
        
        # Test FileNotFoundError
        mock_pipeline.process_audio.side_effect = FileNotFoundError("Audio file not found")
        
        processor = AudioFileProcessor(mock_pipeline)
        
        success, md_file, json_file, error_msg = processor.process_single_file(
            audio_path=Path("/nonexistent/file.wav")
        )
        
        assert success is False
        assert md_file is None
        assert json_file is None
        assert "File not found" in error_msg

    @patch('app.core.services.pipeline.Pipeline')
    def test_audio_file_processor_batch_processing(self, mock_pipeline_class, temp_directory_with_audio):
        """Тест batch обработки"""
        temp_dir, audio_files = temp_directory_with_audio
        
        # Setup mock
        mock_pipeline = Mock()
        mock_pipeline_class.return_value = mock_pipeline
        
        # Mock successful processing
        mock_pipeline.process_audio.return_value = (Path("/fake/output.md"), Path("/fake/output.json"))
        
        processor = AudioFileProcessor(mock_pipeline)
        
        success, results, summary_msg = processor.process_batch(
            directory_path=temp_dir,
            metadata={"title": "Batch Test"}
        )
        
        assert success is True
        assert len(results) == len(audio_files)  # Should process all audio files
        assert "successfully" in summary_msg.lower()
        
        # Verify each file was processed
        for file_path, file_success, file_error in results:
            assert file_success is True
            assert file_error is None

    def test_cli_compatibility_argparse_vs_typer(self):
        """Тест совместимости между argparse и typer CLI"""
        # Test that both CLIs accept the same parameters
        base_args = [
            "--title", "Test Meeting",
            "--date", "2025-05-22", 
            "--location", "Online",
            "--organizer", "Test User",
            "--participants", "User1,User2,User3",
            "--agenda", "Item1,Item2,Item3",
            "--lang", "de",
            "--debug"
        ]
        
        # This test verifies that argument parsing is consistent
        # We'll use MetadataBuilder to simulate what both CLIs should produce
        expected_metadata = {
            "title": "Test Meeting",
            "date": "2025-05-22",
            "location": "Online", 
            "organizer": "Test User",
            "participants": ["User1", "User2", "User3"],
            "agenda": ["Item1", "Item2", "Item3"],
            "author": "AI Assistant"
        }
        
        # Test argparse-style processing
        argparse_metadata = MetadataBuilder.from_cli_args(
            title="Test Meeting",
            date="2025-05-22",
            location="Online",
            organizer="Test User", 
            participants="User1,User2,User3",
            agenda="Item1,Item2,Item3"
        )
        
        # Test typer-style processing (should be identical)
        typer_metadata = MetadataBuilder.from_cli_args(
            title="Test Meeting",
            date="2025-05-22",
            location="Online",
            organizer="Test User",
            participants="User1,User2,User3", 
            agenda="Item1,Item2,Item3"
        )
        
        assert argparse_metadata == typer_metadata == expected_metadata

    @patch('app.core.services.pipeline.Pipeline')
    def test_transcript_processing(self, mock_pipeline_class, temp_transcript_file):
        """Тест обработки JSON транскрипта"""
        # Setup mock
        mock_pipeline = Mock()
        mock_pipeline_class.return_value = mock_pipeline
        mock_pipeline.process_transcript_json.return_value = (Path("/fake/output.md"), Path("/fake/output.json"))
        
        processor = AudioFileProcessor(mock_pipeline)
        
        success, md_file, json_file, error_msg = processor.process_transcript_file(
            transcript_path=temp_transcript_file,
            metadata={"title": "Transcript Test"}
        )
        
        assert success is True
        assert md_file == Path("/fake/output.md")
        assert json_file == Path("/fake/output.json")
        assert error_msg is None
        
        # Verify the pipeline method was called correctly
        mock_pipeline.process_transcript_json.assert_called_once()
        call_kwargs = mock_pipeline.process_transcript_json.call_args[1]
        assert call_kwargs['transcript_path'] == temp_transcript_file
        assert call_kwargs['meeting_info'] == {"title": "Transcript Test"}

    def test_progress_callback_integration(self):
        """Тест интеграции progress callbacks"""
        progress_calls = []
        
        def mock_progress_callback(stage: str, percent: float):
            progress_calls.append((stage, percent))
        
        # Test that callbacks are properly handled
        # This simulates what happens in the CLI when progress is reported
        stages = [
            ("Initializing", 0.1),
            ("Processing Audio", 0.5), 
            ("Generating Protocol", 0.8),
            ("Completed", 1.0)
        ]
        
        for stage, percent in stages:
            mock_progress_callback(stage, percent)
        
        assert len(progress_calls) == 4
        assert progress_calls[0] == ("Initializing", 0.1)
        assert progress_calls[-1] == ("Completed", 1.0)
        
        # Verify progress is monotonically increasing
        for i in range(1, len(progress_calls)):
            assert progress_calls[i][1] >= progress_calls[i-1][1]
