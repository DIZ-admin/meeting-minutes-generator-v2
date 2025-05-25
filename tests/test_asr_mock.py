import unittest
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

# Мок-функция для имитации работы с ASR
def mock_transcribe(audio_path, lang=None):
    """Имитация функции транскрипции аудио"""
    print(f"Мок-транскрипция файла: {audio_path}, язык: {lang or 'auto'}")
    
    # Возвращаем фиксированную транскрипцию
    return [
        {
            "start": 0.0,
            "end": 5.0,
            "speaker": "1",
            "text": "Добрый день, коллеги. Начинаем наше совещание."
        },
        {
            "start": 5.5,
            "end": 10.0,
            "speaker": "2",
            "text": "Давайте обсудим результаты за прошлый квартал."
        },
        {
            "start": 10.5,
            "end": 15.0,
            "speaker": "1", 
            "text": "Согласен. У нас есть хорошие новости по продажам."
        }
    ]

# Мок-функция для генерации протокола
def mock_generate_minutes(transcript_segments, meeting_info=None):
    """Имитация функции генерации протокола совещания"""
    if meeting_info is None:
        meeting_info = {
            "title": "Тестовое совещание",
            "date": "2025-05-19",
            "location": "Онлайн",
            "chair": "Тестовый председатель",
            "author": "AI Assistant",
            "participants": ["Участник 1", "Участник 2"],
            "absent": []
        }
    
    print(f"Генерация протокола из {len(transcript_segments)} сегментов")
    
    # Markdown-протокол
    markdown = f"""# {meeting_info['title']}

**Дата:** {meeting_info['date']}  
**Место:** {meeting_info['location']}  
**Председатель:** {meeting_info['chair']}  
**Автор:** {meeting_info['author']}

## Участники
{', '.join(meeting_info['participants'])}

## Отсутствуют
{', '.join(meeting_info['absent']) if meeting_info['absent'] else 'Нет'}

## Обсуждения и решения

### 1. Обзор результатов
Обсуждение результатов за прошлый квартал. Отмечены хорошие показатели по продажам.

### 2. Решения
- Утвердить отчет за прошлый квартал
- Подготовить план на следующий квартал

### 3. Поручения
| Кому | Что | Срок |
| --- | --- | --- |
| Участник 1 | Подготовить презентацию результатов | 2025-05-26 |
| Участник 2 | Сформировать план продаж | 2025-05-30 |
"""

    # JSON-структура
    json_data = {
        "meta": {
            "titel": meeting_info['title'],
            "datum": meeting_info['date'],
            "ort": meeting_info['location'],
            "sitzungsleiter": meeting_info['chair'],
            "verfasser": meeting_info['author']
        },
        "teilnehmer": {
            "anwesend": meeting_info['participants'],
            "entschuldigt": meeting_info['absent']
        },
        "traktanden": [
            {
                "id": "1",
                "titel": "Обзор результатов",
                "diskussion": "Обсуждение результатов за прошлый квартал. Отмечены хорошие показатели по продажам.",
                "entscheidungen": [
                    "Утвердить отчет за прошлый квартал",
                    "Подготовить план на следующий квартал"
                ],
                "pendenzen": [
                    {
                        "wer": "Участник 1",
                        "was": "Подготовить презентацию результатов",
                        "frist": "2025-05-26"
                    },
                    {
                        "wer": "Участник 2",
                        "was": "Сформировать план продаж",
                        "frist": "2025-05-30"
                    }
                ]
            }
        ]
    }
    
    return markdown, json_data

class TestASRMock(unittest.TestCase):
    """Тестирование цепочки обработки с использованием мок-функций"""
    
    def setUp(self):
        """Настройка тестового окружения"""
        # Создаем временную директорию для тестовых файлов
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audio_path = os.path.join(self.temp_dir.name, "test_audio.wav")
        self.output_dir = os.path.join(self.temp_dir.name, "output")
        
        # Создаем пустой аудиофайл для теста
        with open(self.audio_path, "wb") as f:
            f.write(b"test audio data")
        
        # Создаем директорию для вывода
        os.makedirs(self.output_dir, exist_ok=True)
    
    def tearDown(self):
        """Очистка тестового окружения"""
        self.temp_dir.cleanup()
    
    def test_full_pipeline(self):
        """Тестирование всей цепочки обработки"""
        # 1. Транскрипция аудио
        transcript = mock_transcribe(self.audio_path, lang="ru")
        self.assertIsNotNone(transcript)
        self.assertGreater(len(transcript), 0)
        print(f"Получено {len(transcript)} сегментов транскрипции")
        
        # 2. Создание информации о встрече
        meeting_info = {
            "title": "Тестовое совещание по продажам",
            "date": "2025-05-19",
            "location": "Zoom",
            "chair": "Иван Петров",
            "author": "AI Assistant",
            "participants": ["Иван Петров", "Мария Сидорова", "Алексей Иванов"],
            "absent": ["Петр Смирнов"]
        }
        
        # 3. Генерация протокола
        markdown, json_data = mock_generate_minutes(transcript, meeting_info)
        self.assertIsNotNone(markdown)
        self.assertIsNotNone(json_data)
        print("Протокол успешно создан")
        
        # 4. Сохранение результатов
        md_path = os.path.join(self.output_dir, "minutes.md")
        json_path = os.path.join(self.output_dir, "minutes.json")
        
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        # Проверка, что файлы созданы
        self.assertTrue(os.path.exists(md_path))
        self.assertTrue(os.path.exists(json_path))
        print(f"Файлы сохранены в {self.output_dir}")
        
        # 5. Проверка содержимого файлов
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        
        with open(json_path, "r", encoding="utf-8") as f:
            json_content = json.load(f)
        
        self.assertIn(meeting_info["title"], md_content)
        self.assertEqual(json_content["meta"]["datum"], meeting_info["date"])
        self.assertEqual(len(json_content["teilnehmer"]["anwesend"]), len(meeting_info["participants"]))
        print("Содержимое файлов корректно")

if __name__ == "__main__":
    unittest.main()