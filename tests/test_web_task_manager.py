"""
Тесты для WebTaskManager
"""
import pytest
from datetime import datetime, timedelta

from app.web_services.file_processor import WebTaskManager, WebMetadataBuilder

class TestWebTaskManager:
    """Тесты для WebTaskManager"""
    
    @pytest.fixture
    def task_manager(self):
        """Экземпляр WebTaskManager для тестирования"""
        return WebTaskManager()
    
    def test_create_task(self, task_manager):
        """Тест создания задачи"""
        # Act
        task_id = task_manager.create_task("test_processing")
        
        # Assert
        assert task_id is not None
        assert len(task_id) > 10  # UUID должен быть достаточно длинным
        
        task = task_manager.get_task(task_id)
        assert task is not None
        assert task["id"] == task_id
        assert task["type"] == "test_processing"
        assert task["status"] == "created"
        assert task["progress"] == 0.0
    
    def test_update_task(self, task_manager):
        """Тест обновления задачи"""
        # Arrange
        task_id = task_manager.create_task()
        
        # Act
        task_manager.update_task(
            task_id=task_id,
            status="processing",
            progress=0.5,
            message="Half way done"
        )
        
        # Assert
        task = task_manager.get_task(task_id)
        assert task["status"] == "processing"
        assert task["progress"] == 0.5
        assert task["message"] == "Half way done"
        assert "updated_at" in task
    
    def test_get_nonexistent_task(self, task_manager):
        """Тест получения несуществующей задачи"""
        # Act
        task = task_manager.get_task("nonexistent-id")
        
        # Assert
        assert task is None
    
    def test_delete_task(self, task_manager):
        """Тест удаления задачи"""
        # Arrange
        task_id = task_manager.create_task()
        
        # Act
        deleted = task_manager.delete_task(task_id)
        
        # Assert
        assert deleted is True
        assert task_manager.get_task(task_id) is None
    
    def test_get_all_tasks(self, task_manager):
        """Тест получения всех задач"""
        # Arrange
        task_id1 = task_manager.create_task("type1")
        task_id2 = task_manager.create_task("type2")
        
        # Act
        all_tasks = task_manager.get_all_tasks()
        
        # Assert
        assert len(all_tasks) == 2
        task_ids = [task["id"] for task in all_tasks]
        assert task_id1 in task_ids
        assert task_id2 in task_ids

class TestWebMetadataBuilder:
    """Тесты для WebMetadataBuilder"""
    
    def test_from_web_form_basic(self):
        """Тест базового создания метаданных из веб-формы"""
        # Act
        metadata = WebMetadataBuilder.from_web_form(
            title="Web Meeting",
            date="2025-05-22",
            location="Online",
            organizer="Web User"
        )
        
        # Assert
        assert metadata["title"] == "Web Meeting"
        assert metadata["date"] == "2025-05-22" 
        assert metadata["location"] == "Online"
        assert metadata["organizer"] == "Web User"
        assert metadata["author"] == "AI Assistant"
    
    def test_from_web_form_with_participants(self):
        """Тест обработки участников из веб-формы"""
        # Act - тестируем разные форматы разделителей
        metadata = WebMetadataBuilder.from_web_form(
            participants="User1, User2,User3\nUser4\n User5 "
        )
        
        # Assert
        expected_participants = ["User1", "User2", "User3", "User4", "User5"]
        assert metadata["participants"] == expected_participants
    
    def test_from_web_form_with_agenda(self):
        """Тест обработки повестки из веб-формы"""
        # Act
        metadata = WebMetadataBuilder.from_web_form(
            agenda="Item 1, Item 2\nItem 3,Item 4"
        )
        
        # Assert
        expected_agenda = ["Item 1", "Item 2", "Item 3", "Item 4"]
        assert metadata["agenda"] == expected_agenda
    
    def test_from_web_form_empty_values(self):
        """Тест обработки пустых значений"""
        # Act
        metadata = WebMetadataBuilder.from_web_form(
            title="",
            participants="",
            agenda="  "
        )
        
        # Assert
        assert "title" not in metadata
        assert "participants" not in metadata  
        assert "agenda" not in metadata
        assert metadata["author"] == "AI Assistant"
