"""
Тесты для API
"""
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.web.app import app
from app.web.models import ProcessingStatus, UploadResponse, StatusResponse, ProtocolResponse

@pytest.fixture
def client():
    """
    Фикстура для создания тестового клиента FastAPI
    """
    return TestClient(app)

@pytest.fixture
def mock_pipeline():
    """
    Фикстура для мока Pipeline
    """
    with patch("app.web.api_routes.pipeline") as mock:
        # Настраиваем мок для метода process_audio_file
        mock_protocol = MagicMock()
        mock_protocol.to_dict.return_value = {
            "metadata": {
                "title": "Test Meeting",
                "date": "2025-05-25"
            },
            "summary": "Test summary",
            "participants": ["John Doe", "Jane Smith"],
            "agenda_items": ["Topic 1", "Topic 2"],
            "decisions": ["Decision 1", "Decision 2"],
            "action_items": ["Action 1", "Action 2"]
        }
        
        mock.process_audio_file.return_value = mock_protocol
        mock.process_transcript_json.return_value = mock_protocol
        
        yield mock

@pytest.fixture
def mock_background_tasks():
    """
    Фикстура для мока BackgroundTasks
    """
    with patch("fastapi.BackgroundTasks.add_task") as mock:
        yield mock

@pytest.fixture
def mock_update_task_status():
    """
    Фикстура для мока update_task_status
    """
    with patch("app.web.api_routes.update_task_status") as mock:
        yield mock

class TestAPI:
    """
    Тесты для API
    """
    
    def test_health_check(self, client):
        """
        Тест для эндпоинта /health
        """
        response = client.get("/health")
        assert response.status_code == 200
        assert "status" in response.json()
        assert "config" in response.json()
        assert "directories" in response.json()
        assert "cache" in response.json()
        assert "metrics" in response.json()
        assert "version" in response.json()
    
    def test_upload_audio_success(self, client, mock_pipeline, mock_background_tasks, mock_update_task_status):
        """
        Тест успешной загрузки аудиофайла
        """
        # Создаем временный аудиофайл
        with tempfile.NamedTemporaryFile(suffix=".mp3") as temp_file:
            # Заполняем файл тестовыми данными
            temp_file.write(b"test audio data")
            temp_file.flush()
            
            # Создаем данные для запроса
            meeting_info = json.dumps({
                "title": "Test Meeting",
                "date": "2025-05-25",
                "location": "Test Location",
                "organizer": "Test Organizer"
            })
            
            # Отправляем запрос
            with open(temp_file.name, "rb") as f:
                response = client.post(
                    "/api/v1/upload",
                    files={"file": ("test.mp3", f, "audio/mpeg")},
                    data={
                        "is_transcript": "false",
                        "meeting_info": meeting_info,
                        "language": "en",
                        "skip_notifications": "false"
                    }
                )
            
            # Проверяем ответ
            assert response.status_code == 200
            
            # Проверяем структуру ответа
            response_data = response.json()
            assert "task_id" in response_data
            assert "message" in response_data
            assert "status" in response_data
            assert response_data["status"] == ProcessingStatus.PENDING.value
            
            # Проверяем, что задача добавлена в фоновые задачи
            mock_background_tasks.assert_called_once()
    
    def test_upload_transcript_success(self, client, mock_pipeline, mock_background_tasks, mock_update_task_status):
        """
        Тест успешной загрузки JSON-транскрипта
        """
        # Создаем временный JSON-файл
        with tempfile.NamedTemporaryFile(suffix=".json") as temp_file:
            # Заполняем файл тестовыми данными
            json_data = {
                "segments": [
                    {"speaker": "Speaker 1", "text": "Hello, this is a test."},
                    {"speaker": "Speaker 2", "text": "Yes, this is a test."}
                ]
            }
            temp_file.write(json.dumps(json_data).encode())
            temp_file.flush()
            
            # Создаем данные для запроса
            meeting_info = json.dumps({
                "title": "Test Transcript",
                "date": "2025-05-25"
            })
            
            # Отправляем запрос
            with open(temp_file.name, "rb") as f:
                response = client.post(
                    "/api/v1/upload",
                    files={"file": ("test.json", f, "application/json")},
                    data={
                        "is_transcript": "true",
                        "meeting_info": meeting_info,
                        "language": "en",
                        "skip_notifications": "false"
                    }
                )
            
            # Проверяем ответ
            assert response.status_code == 200
            
            # Проверяем структуру ответа
            response_data = response.json()
            assert "task_id" in response_data
            assert "message" in response_data
            assert "status" in response_data
            assert response_data["status"] == ProcessingStatus.PENDING.value
            
            # Проверяем, что задача добавлена в фоновые задачи
            mock_background_tasks.assert_called_once()
    
    def test_upload_invalid_file_format(self, client):
        """
        Тест загрузки файла с неподдерживаемым форматом
        """
        # Создаем временный файл с неподдерживаемым форматом
        with tempfile.NamedTemporaryFile(suffix=".txt") as temp_file:
            # Заполняем файл тестовыми данными
            temp_file.write(b"test data")
            temp_file.flush()
            
            # Отправляем запрос
            with open(temp_file.name, "rb") as f:
                response = client.post(
                    "/api/v1/upload",
                    files={"file": ("test.txt", f, "text/plain")},
                    data={
                        "is_transcript": "false",
                        "language": "en"
                    }
                )
            
            # Проверяем ответ
            assert response.status_code == 415
            assert "detail" in response.json()
            assert "Неподдерживаемый формат" in response.json()["detail"]
    
    def test_get_task_status(self, client):
        """
        Тест получения статуса задачи
        """
        # Добавляем тестовую задачу в tasks_info
        from app.web.api_routes import tasks_info
        task_id = "test_task_id"
        tasks_info[task_id] = {
            "task_id": task_id,
            "file_name": "test.mp3",
            "status": ProcessingStatus.PROCESSING,
            "progress": 50.0,
            "message": "Обработка: транскрипция",
            "created_at": "2025-05-25T10:00:00",
            "updated_at": "2025-05-25T10:05:00"
        }
        
        # Отправляем запрос
        response = client.get(f"/api/v1/status/{task_id}")
        
        # Проверяем ответ
        assert response.status_code == 200
        
        # Проверяем структуру ответа
        response_data = response.json()
        assert "task_id" in response_data
        assert "status" in response_data
        assert "progress" in response_data
        assert "message" in response_data
        assert response_data["task_id"] == task_id
        assert response_data["status"] == ProcessingStatus.PROCESSING.value
        assert response_data["progress"] == 50.0
        
        # Удаляем тестовую задачу
        del tasks_info[task_id]
    
    def test_get_task_status_not_found(self, client):
        """
        Тест получения статуса несуществующей задачи
        """
        # Отправляем запрос с несуществующим task_id
        response = client.get("/api/v1/status/non_existent_task_id")
        
        # Проверяем ответ
        assert response.status_code == 404
        assert "detail" in response.json()
        assert "не найдена" in response.json()["detail"]
    
    def test_get_protocol(self, client):
        """
        Тест получения протокола
        """
        # Добавляем тестовую задачу в tasks_info
        from app.web.api_routes import tasks_info
        task_id = "test_task_id"
        
        # Создаем временные файлы для результатов
        with tempfile.TemporaryDirectory() as temp_dir:
            # Создаем JSON-файл
            json_file = os.path.join(temp_dir, "test.json")
            with open(json_file, "w") as f:
                json.dump({
                    "metadata": {
                        "title": "Test Meeting",
                        "date": "2025-05-25"
                    },
                    "summary": "Test summary",
                    "participants": ["John Doe", "Jane Smith"],
                    "agenda_items": ["Topic 1", "Topic 2"],
                    "decisions": ["Decision 1", "Decision 2"],
                    "action_items": ["Action 1", "Action 2"]
                }, f)
            
            # Создаем Markdown-файл
            md_file = os.path.join(temp_dir, "test.md")
            with open(md_file, "w") as f:
                f.write("# Test Meeting\n\n## Summary\n\nTest summary\n\n")
            
            # Добавляем задачу в tasks_info
            tasks_info[task_id] = {
                "task_id": task_id,
                "file_name": "test.mp3",
                "status": ProcessingStatus.COMPLETED,
                "progress": 100.0,
                "message": "Обработка завершена успешно",
                "created_at": "2025-05-25T10:00:00",
                "updated_at": "2025-05-25T10:10:00",
                "result": {
                    "protocol": {
                        "metadata": {
                            "title": "Test Meeting",
                            "date": "2025-05-25"
                        },
                        "summary": "Test summary",
                        "participants": ["John Doe", "Jane Smith"],
                        "agenda_items": ["Topic 1", "Topic 2"],
                        "decisions": ["Decision 1", "Decision 2"],
                        "action_items": ["Action 1", "Action 2"]
                    },
                    "output_dir": temp_dir,
                    "files": {
                        "json": json_file,
                        "md": md_file
                    }
                }
            }
            
            # Отправляем запрос для получения протокола в формате JSON
            response = client.get(f"/api/v1/protocol/{task_id}")
            
            # Проверяем ответ
            assert response.status_code == 200
            
            # Проверяем структуру ответа
            response_data = response.json()
            assert "metadata" in response_data
            assert "summary" in response_data
            assert "participants" in response_data
            assert "agenda_items" in response_data
            assert "decisions" in response_data
            assert "action_items" in response_data
            assert response_data["metadata"]["title"] == "Test Meeting"
            assert response_data["summary"] == "Test summary"
            
            # Отправляем запрос для получения протокола в формате Markdown
            response = client.get(f"/api/v1/protocol/{task_id}?format=markdown")
            
            # Проверяем ответ
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/markdown")
            assert "Test Meeting" in response.text
            assert "Test summary" in response.text
        
        # Удаляем тестовую задачу
        del tasks_info[task_id]
    
    def test_get_protocol_not_found(self, client):
        """
        Тест получения несуществующего протокола
        """
        # Отправляем запрос с несуществующим task_id
        response = client.get("/api/v1/protocol/non_existent_task_id")
        
        # Проверяем ответ
        assert response.status_code == 404
        assert "detail" in response.json()
        assert "не найдена" in response.json()["detail"]
    
    def test_get_protocol_not_completed(self, client):
        """
        Тест получения протокола для незавершенной задачи
        """
        # Добавляем тестовую задачу в tasks_info
        from app.web.api_routes import tasks_info
        task_id = "test_task_id"
        tasks_info[task_id] = {
            "task_id": task_id,
            "file_name": "test.mp3",
            "status": ProcessingStatus.PROCESSING,
            "progress": 50.0,
            "message": "Обработка: транскрипция",
            "created_at": "2025-05-25T10:00:00",
            "updated_at": "2025-05-25T10:05:00"
        }
        
        # Отправляем запрос
        response = client.get(f"/api/v1/protocol/{task_id}")
        
        # Проверяем ответ
        assert response.status_code == 422
        assert "detail" in response.json()
        assert "не завершена" in response.json()["detail"]
        
        # Удаляем тестовую задачу
        del tasks_info[task_id]
