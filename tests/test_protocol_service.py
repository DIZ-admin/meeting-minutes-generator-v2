"""
Тесты для ProtocolService
"""
import unittest
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

# Импортируем тестируемые модули
from app.core.services.protocol_service import ProtocolService
from app.core.models.protocol import Protocol
from app.core.exceptions import ValidationError

class TestProtocolService(unittest.TestCase):
    """
    Тесты для ProtocolService
    """
    def setUp(self):
        """
        Подготовка к тестам
        """
        self.protocol_service = ProtocolService()
        
        # Создаем тестовые данные
        self.test_protocol_json = {
            "metadata": {
                "title": "Test Meeting",
                "date": "2025-05-25",
                "participants": ["John Doe", "Jane Smith"]
            },
            "summary": "This is a test summary",
            "decisions": [
                {"text": "Decision 1", "owner": "John Doe"},
                {"text": "Decision 2", "owner": "Jane Smith"}
            ],
            "action_items": [
                {"text": "Action 1", "owner": "John Doe", "due_date": "2025-06-01"},
                {"text": "Action 2", "owner": "Jane Smith", "due_date": "2025-06-02"}
            ],
            "participants": [
                {"name": "John Doe", "role": "Manager"},
                {"name": "Jane Smith", "role": "Developer"}
            ],
            "agenda_items": [
                {"title": "Item 1", "notes": "Notes for item 1"},
                {"title": "Item 2", "notes": "Notes for item 2"}
            ]
        }
        
        # Тестовые данные с альтернативной структурой
        self.alt_protocol_json = {
            "metadata": {
                "title": "Alternative Meeting",
                "date": "2025-05-25"
            },
            "summary": "This is an alternative summary",
            "decisions": [
                "Decision 1 without owner",
                "Decision 2 without owner"
            ],
            "actions": [  # Обратите внимание на 'actions' вместо 'action_items'
                "Action 1 without details",
                "Action 2 without details"
            ],
            "participants": [
                "John Doe",
                "Jane Smith"
            ],
            "agenda_items": [
                "Item 1 without notes",
                "Item 2 without notes"
            ]
        }
        
        # Тестовые данные с минимальной структурой
        self.minimal_protocol_json = {
            "summary": "Minimal summary"
        }
    
    def test_create_protocol_from_json_complete(self):
        """
        Тест создания протокола из полного JSON
        """
        protocol = self.protocol_service._create_protocol_from_json(self.test_protocol_json)
        
        # Проверяем, что протокол создан корректно
        self.assertIsInstance(protocol, Protocol)
        self.assertEqual(protocol.metadata.get("title"), "Test Meeting")
        self.assertEqual(protocol.summary, "This is a test summary")
        self.assertEqual(len(protocol.decisions), 2)
        self.assertEqual(len(protocol.action_items), 2)
        self.assertEqual(len(protocol.participants), 2)
        self.assertEqual(len(protocol.agenda_items), 2)
    
    def test_create_protocol_from_json_alternative(self):
        """
        Тест создания протокола из JSON с альтернативной структурой
        """
        protocol = self.protocol_service._create_protocol_from_json(self.alt_protocol_json)
        
        # Проверяем, что протокол создан корректно
        self.assertIsInstance(protocol, Protocol)
        self.assertEqual(protocol.metadata.get("title"), "Alternative Meeting")
        self.assertEqual(protocol.summary, "This is an alternative summary")
        self.assertEqual(len(protocol.decisions), 2)
        self.assertEqual(len(protocol.action_items), 2)  # Должно быть преобразовано из 'actions'
        self.assertEqual(len(protocol.participants), 2)
        self.assertEqual(len(protocol.agenda_items), 2)
    
    def test_create_protocol_from_json_minimal(self):
        """
        Тест создания протокола из минимального JSON
        """
        protocol = self.protocol_service._create_protocol_from_json(self.minimal_protocol_json)
        
        # Проверяем, что протокол создан корректно
        self.assertIsInstance(protocol, Protocol)
        self.assertEqual(protocol.summary, "Minimal summary")
        # После schema fix, metadata будет содержать minimal required fields
        self.assertIn("title", protocol.metadata)
        self.assertIn("date", protocol.metadata)
        self.assertEqual(protocol.decisions, [])
        self.assertEqual(protocol.action_items, [])
        self.assertEqual(protocol.participants, [])
        self.assertEqual(protocol.agenda_items, [])
    
    def test_create_protocol_from_json_with_error(self):
        """
        Тест обработки ошибок при создании протокола
        """
        # Создаем некорректный JSON
        invalid_json = {"invalid_field": "value"}
        
        # Патчим Protocol.__init__ для вызова исключения
        with patch('app.core.models.protocol.Protocol.__init__', side_effect=ValueError("Test error")):
            protocol = self.protocol_service._create_protocol_from_json(invalid_json)
            
            # Проверяем, что создан пустой протокол с информацией об ошибке
            self.assertIsInstance(protocol, Protocol)
            self.assertTrue("Failed to create protocol" in protocol.summary)
            self.assertEqual(protocol.decisions, [])
            self.assertEqual(protocol.action_items, [])
            self.assertEqual(protocol.participants, [])
            self.assertEqual(protocol.agenda_items, [])

    @patch('app.utils.schemas.validate_protocol_json')
    def test_create_protocol_with_validation(self, mock_validate):
        """
        Тест валидации протокола при создании
        """
        protocol = self.protocol_service._create_protocol_from_json(self.test_protocol_json)
        
        # Проверяем, что была вызвана функция валидации
        mock_validate.assert_called_once()
        
        # Проверяем, что протокол создан корректно
        self.assertIsInstance(protocol, Protocol)
        self.assertEqual(protocol.metadata.get("title"), "Test Meeting")

    def test_create_protocol_with_mixed_format_data(self):
        """
        Тест создания протокола из данных со смешанным форматом
        """
        # Создаем данные со смешанным форматом
        mixed_format_data = {
            "metadata": {
                "title": "Mixed Format Meeting",
                "date": "2025-05-25"
            },
            "summary": "This is a test with mixed format data",
            "decisions": [
                "Simple decision as string",
                {"text": "Decision with owner", "owner": "John Doe"},
                {"decision": "Decision with old format"}
            ],
            "action_items": [
                "Simple action as string",
                {"text": "Action with owner", "owner": "Jane Smith", "due_date": "2025-06-01"},
                {"action": "Action with old format", "assignee": "Bob Johnson"}
            ],
            "participants": [
                "Simple participant as string",
                {"name": "Complex Participant", "role": "Manager", "email": "manager@example.com"}
            ],
            "agenda_items": [
                "Simple agenda item as string",
                {"title": "Complex agenda item", "notes": "Some notes", "duration": "30 minutes"},
                {"topic": "Old format agenda item", "description": "Old description"}
            ]
        }
        
        # Создаем протокол из смешанных данных
        protocol = self.protocol_service._create_protocol_from_json(mixed_format_data)
        
        # Проверяем, что протокол создан корректно
        self.assertIsInstance(protocol, Protocol)
        self.assertEqual(protocol.metadata.get("title"), "Mixed Format Meeting")
        self.assertEqual(len(protocol.decisions), 3)
        self.assertEqual(len(protocol.action_items), 3)
        self.assertEqual(len(protocol.participants), 2)
        self.assertEqual(len(protocol.agenda_items), 3)

if __name__ == '__main__':
    unittest.main()
