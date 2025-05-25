"""
Тесты для функции извлечения метаданных из имени файла
"""
import pytest
from unittest.mock import patch, MagicMock
import datetime

import re
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, parent_dir)

def extract_metadata(filename: str):
    """
    Извлекает метаданные протокола из имени файла
    
    Args:
        filename: Имя файла без расширения
        
    Returns:
        Словарь с метаданными протокола
    """
    # Базовые метаданные
    metadata = {
        "title": "Meeting Protocol",
        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "location": "Online Meeting",
        "organizer": "",
        "author": "AI Assistant"
    }
    
    # Пытаемся извлечь дату из имени файла (формат "meeting_2025-06-01" или "eGL_2025-06-01")
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if date_match:
        metadata["date"] = date_match.group(1)
    
    # Пытаемся извлечь название из имени файла
    # Удаляем дату и специальные символы, преобразуем подчеркивания в пробелы
    title = filename
    if date_match:
        title = title.replace(date_match.group(1), "")
    
    # Удаляем специальные символы и лишние пробелы
    title = re.sub(r'[^\w\s]', ' ', title)
    title = re.sub(r'_', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Если название не пустое, используем его
    if title:
        metadata["title"] = title.title()  # Преобразуем в Title Case
    
    return metadata

class TestExtractMetadata:
    """Тесты для функции extract_metadata"""
    
    def test_extract_metadata_with_date_in_filename(self):
        """Проверка извлечения метаданных, когда дата есть в имени файла"""
        # Тестируем извлечение метаданных из имени файла с датой
        filename = "meeting_eGL_2024-07-15_extra_info"
        metadata = extract_metadata(filename)
        
        # Проверяем извлеченные метаданные
        assert metadata["date"] == "2024-07-15"
        assert "Meeting Egl Extra Info" in metadata["title"]
    
    @patch('datetime.datetime')
    def test_extract_metadata_no_date_in_filename(self, mock_datetime):
        """Проверка извлечения метаданных, когда даты нет в имени файла (используется текущая)"""
        # Мокируем datetime.now()
        mock_now = MagicMock()
        mock_now.strftime.return_value = "2023-10-20"
        mock_datetime.now.return_value = mock_now
        
        # Тестируем извлечение метаданных из имени файла без даты
        filename = "random_meeting_audio"
        metadata = extract_metadata(filename)
        
        # Проверяем извлеченные метаданные
        assert metadata["date"] == "2023-10-20"
        assert "Random Meeting Audio" in metadata["title"]
    
    @patch('datetime.datetime')
    def test_extract_metadata_empty_filename(self, mock_datetime):
        """Проверка извлечения метаданных из пустого имени файла"""
        # Мокируем datetime.now()
        mock_now = MagicMock()
        mock_now.strftime.return_value = "2023-10-20"
        mock_datetime.now.return_value = mock_now
        
        # Тестируем извлечение метаданных из пустого имени файла
        filename = ""
        metadata = extract_metadata(filename)
        
        # Проверяем, что метаданные содержат значения по умолчанию
        assert metadata["date"] == "2023-10-20"
        assert metadata["title"] == "Meeting Protocol"
        assert metadata["location"] == "Online Meeting"
        assert metadata["author"] == "AI Assistant"

if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
