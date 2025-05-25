import unittest
from unittest.mock import patch, MagicMock, mock_open
import pathlib
import json
import sys
import os
from datetime import datetime

# Добавляем корневую директорию проекта в sys.path для корректного импорта модулей из scripts
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from scripts.cli import extract_meeting_info, process_audio, main

class TestExtractMeetingInfo(unittest.TestCase):
    """Тесты для функции extract_meeting_info"""

    @patch('scripts.cli.datetime')
    def test_extract_info_with_date_in_filename(self, mock_datetime):
        """Проверка извлечения информации, когда дата есть в имени файла"""
        # Мокируем datetime.now() на случай, если re не найдет дату (хотя он должен)
        mock_datetime.now.return_value = datetime(2023, 1, 1, 10, 0, 0)
        mock_datetime.now.strftime.return_value = "2023-01-01"

        filename = "meeting_eGL_2024-07-15_extra_info.m4a"
        expected_info = {
            "title": "Protokoll eGL",
            "date": "2024-07-15",
            "location": "Online Meeting",
            "chair": "",
            "author": "AI Assistant",
            "participants": [],
            "absent": []
        }
        info = extract_meeting_info(filename)
        self.assertEqual(info, expected_info)

    @patch('scripts.cli.datetime')
    def test_extract_info_no_date_in_filename(self, mock_datetime):
        """Проверка извлечения информации, когда даты нет в имени файла (используется текущая)"""
        # Создаем полный mock для datetime
        mock_now = MagicMock()
        mock_now.strftime.return_value = "2023-10-20"
        mock_datetime.now.return_value = mock_now

        filename = "random_meeting_audio.mp3"
        expected_info = {
            "title": "Protokoll eGL",
            "date": "2023-10-20", # Ожидаем мокированную текущую дату
            "location": "Online Meeting",
            "chair": "",
            "author": "AI Assistant",
            "participants": [],
            "absent": []
        }
        info = extract_meeting_info(filename)
        # Сверяем поля по отдельности, т.к. strftime мокируется хитро
        self.assertEqual(info["title"], expected_info["title"])
        self.assertEqual(info["date"], expected_info["date"])
        self.assertEqual(info["location"], expected_info["location"])
        self.assertEqual(info["author"], expected_info["author"])

    def test_extract_info_default_fields(self):
        """Проверка значений по умолчанию для остальных полей"""
        # Используем имя файла без даты, чтобы дата установилась по умолчанию (но она не проверяется здесь)
        info = extract_meeting_info("any_filename.wav")
        self.assertEqual(info["title"], "Protokoll eGL")
        self.assertEqual(info["location"], "Online Meeting")
        self.assertEqual(info["chair"], "")
        self.assertEqual(info["author"], "AI Assistant")
        self.assertEqual(info["participants"], [])
        self.assertEqual(info["absent"], [])

if __name__ == '__main__':
    unittest.main()
