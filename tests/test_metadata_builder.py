"""
Тесты для MetadataBuilder - сервиса создания метаданных
"""
import pytest
from app.cli_services.file_processor import MetadataBuilder

class TestMetadataBuilder:
    """Тесты для MetadataBuilder"""
    
    def test_from_cli_args_basic(self):
        """Тест базового создания метаданных"""
        # Arrange
        args = {
            "title": "Test Meeting",
            "date": "2025-05-22",
            "location": "Conference Room A",
            "organizer": "John Doe"
        }
        
        # Act
        metadata = MetadataBuilder.from_cli_args(**args)
        
        # Assert
        assert metadata["title"] == "Test Meeting"
        assert metadata["date"] == "2025-05-22"
        assert metadata["location"] == "Conference Room A"
        assert metadata["organizer"] == "John Doe"
        assert metadata["author"] == "AI Assistant"
    
    def test_from_cli_args_with_participants_string(self):
        """Тест обработки участников как строки"""
        # Arrange
        args = {
            "participants": "John Doe, Jane Smith, Bob Wilson"
        }
        
        # Act
        metadata = MetadataBuilder.from_cli_args(**args)
        
        # Assert
        assert metadata["participants"] == ["John Doe", "Jane Smith", "Bob Wilson"]
        assert metadata["author"] == "AI Assistant"
    
    def test_from_cli_args_with_participants_list(self):
        """Тест обработки участников как списка"""
        # Arrange
        participants_list = ["John Doe", "Jane Smith", "Bob Wilson"]
        args = {
            "participants": participants_list
        }
        
        # Act
        metadata = MetadataBuilder.from_cli_args(**args)
        
        # Assert
        assert metadata["participants"] == participants_list
    
    def test_from_cli_args_with_agenda_string(self):
        """Тест обработки повестки как строки"""
        # Arrange
        args = {
            "agenda": "Introduction, Main Topic, Q&A, Next Steps"
        }
        
        # Act
        metadata = MetadataBuilder.from_cli_args(**args)
        
        # Assert
        assert metadata["agenda"] == ["Introduction", "Main Topic", "Q&A", "Next Steps"]
    
    def test_from_cli_args_empty(self):
        """Тест создания метаданных без параметров"""
        # Act
        metadata = MetadataBuilder.from_cli_args()
        
        # Assert
        assert metadata["author"] == "AI Assistant"
        assert len(metadata) == 1  # Только author
    
    def test_from_cli_args_none_values(self):
        """Тест обработки None значений"""
        # Arrange
        args = {
            "title": None,
            "date": None,
            "participants": None,
            "agenda": None
        }
        
        # Act
        metadata = MetadataBuilder.from_cli_args(**args)
        
        # Assert
        assert "title" not in metadata
        assert "date" not in metadata
        assert "participants" not in metadata
        assert "agenda" not in metadata
        assert metadata["author"] == "AI Assistant"
