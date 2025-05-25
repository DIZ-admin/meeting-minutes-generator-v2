"""
Тесты для модуля schemas.py
"""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.utils.schemas import validate_json, validate_protocol_json

class TestSchemas(unittest.TestCase):
    """
    Тесты для функций валидации схем
    """
    
    def setUp(self):
        """
        Подготовка к тестам
        """
        # Создаем тестовые данные для протокола
        self.valid_protocol = {
            "metadata": {
                "title": "Test Meeting",
                "date": "2025-05-25"
            },
            "summary": "Test summary",
            "participants": [
                {"name": "John Doe", "role": "Manager"},
                {"name": "Jane Smith", "role": "Developer"}
            ],
            "agenda_items": [
                {"topic": "Topic 1", "description": "Description 1"},
                {"topic": "Topic 2", "description": "Description 2"}
            ],
            "decisions": [
                {"decision": "Decision 1", "context": "Context 1"},
                {"decision": "Decision 2", "context": "Context 2"}
            ],
            "action_items": [
                {"action": "Action 1", "assignee": "John Doe", "due_date": "2025-06-01"},
                {"action": "Action 2", "assignee": "Jane Smith", "due_date": "2025-06-02"}
            ]
        }
        
        # Создаем протокол с альтернативным форматом данных
        self.alt_format_protocol = {
            "metadata": {
                "title": "Alternative Format Meeting",
                "date": "2025-05-25"
            },
            "summary": "Test with alternative format",
            "participants": [
                "John Doe",
                "Jane Smith"
            ],
            "agenda_items": [
                "Topic 1",
                "Topic 2"
            ],
            "decisions": [
                "Decision 1",
                "Decision 2"
            ],
            "actions": [  # Обратите внимание на 'actions' вместо 'action_items'
                "Action 1",
                "Action 2"
            ]
        }
        
        # Создаем протокол с недостающими обязательными полями
        self.incomplete_protocol = {
            "summary": "Incomplete protocol"
            # Отсутствуют metadata и другие поля
        }
        
        # Создаем протокол с некорректными данными
        self.invalid_protocol = {
            "metadata": "not_a_dict",  # Должен быть словарь
            "summary": 12345,  # Должен быть строкой
            "participants": "not_an_array"  # Должен быть массивом
        }
    
    @patch('app.utils.schemas.validate_json')
    def test_validate_protocol_json_valid(self, mock_validate_json):
        """
        Тест валидации корректного протокола
        """
        # Настраиваем мок для имитации успешной валидации
        mock_validate_json.return_value = self.valid_protocol
        
        # Вызываем функцию валидации
        result = validate_protocol_json(self.valid_protocol)
        
        # Проверяем, что validate_json был вызван с правильными параметрами
        mock_validate_json.assert_called_once()
        
        # Проверяем результат
        self.assertEqual(result, self.valid_protocol)
    
    @patch('app.utils.schemas.validate_json')
    def test_validate_protocol_json_alternative_format(self, mock_validate_json):
        """
        Тест валидации протокола с альтернативным форматом данных
        """
        # Настраиваем мок для имитации успешной валидации
        mock_validate_json.return_value = self.alt_format_protocol
        
        # Вызываем функцию валидации
        result = validate_protocol_json(self.alt_format_protocol)
        
        # Проверяем, что validate_json был вызван с правильными параметрами
        mock_validate_json.assert_called_once()
        
        # Проверяем результат
        self.assertEqual(result, self.alt_format_protocol)
    
    @patch('app.utils.schemas.validate_json')
    def test_validate_protocol_json_fix_incomplete(self, mock_validate_json):
        """
        Тест исправления неполного протокола в нестрогом режиме
        """
        # Настраиваем мок для имитации ошибки валидации
        mock_validate_json.side_effect = Exception("Validation error")
        
        # Вызываем функцию валидации в нестрогом режиме
        result = validate_protocol_json(self.incomplete_protocol, strict=False)
        
        # Проверяем, что validate_json был вызван
        mock_validate_json.assert_called_once()
        
        # Проверяем, что результат содержит исправленные данные
        self.assertIn("metadata", result)
        self.assertIn("title", result["metadata"])
        self.assertIn("date", result["metadata"])
        self.assertEqual(result["summary"], "Incomplete protocol")
        self.assertIn("participants", result)
        self.assertIn("agenda_items", result)
        self.assertIn("decisions", result)
        self.assertIn("action_items", result)
        self.assertIn("created_at", result)
    
    @patch('app.utils.schemas.validate_json')
    def test_validate_protocol_json_strict_mode(self, mock_validate_json):
        """
        Тест валидации в строгом режиме
        """
        # Настраиваем мок для имитации ошибки валидации
        mock_validate_json.side_effect = Exception("Validation error")
        
        # Проверяем, что в строгом режиме исключение пробрасывается дальше
        with self.assertRaises(Exception):
            validate_protocol_json(self.invalid_protocol, strict=True)
    
    def test_validate_protocol_json_with_string_data(self):
        """
        Тест валидации протокола из строки JSON
        """
        # Создаем временный файл с данными протокола
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
            json.dump(self.valid_protocol, temp_file)
            temp_path = temp_file.name
        
        try:
            # Патчим validate_json, чтобы он возвращал данные без реальной валидации
            with patch('app.utils.schemas.validate_json', return_value=self.valid_protocol):
                # Тестируем валидацию из строки JSON
                json_str = json.dumps(self.valid_protocol)
                result_from_str = validate_protocol_json(json_str)
                self.assertEqual(result_from_str, self.valid_protocol)
                
                # Тестируем валидацию из пути к файлу
                result_from_path = validate_protocol_json(temp_path)
                self.assertEqual(result_from_path, self.valid_protocol)
                
                # Тестируем валидацию из объекта Path
                result_from_path_obj = validate_protocol_json(Path(temp_path))
                self.assertEqual(result_from_path_obj, self.valid_protocol)
        finally:
            # Удаляем временный файл
            Path(temp_path).unlink()
    
    def test_validate_protocol_json_invalid_input(self):
        """
        Тест валидации с некорректным входным форматом
        """
        # Патчим validate_json, чтобы он вызывал исключение
        with patch('app.utils.schemas.validate_json', side_effect=Exception("Validation error")):
            # Тестируем валидацию с некорректным типом данных
            with self.assertRaises(ValueError):
                validate_protocol_json(123)  # Не словарь, не строка и не Path

if __name__ == '__main__':
    unittest.main()
