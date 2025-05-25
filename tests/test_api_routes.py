"""
Тесты для API маршрутов веб-интерфейса
"""
import os
import json
import uuid
import pytest
from datetime import datetime, date
from fastapi.testclient import TestClient
from pathlib import Path
from unittest.mock import patch, MagicMock

# Патч для сериализации datetime в JSON
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

# Патчим json.dumps для использования нашего энкодера
orig_dumps = json.dumps

def patched_dumps(obj, *args, **kwargs):
    # Если cls уже есть в kwargs, не добавляем его снова
    if 'cls' not in kwargs:
        kwargs['cls'] = DateTimeEncoder
    return orig_dumps(obj, *args, **kwargs)

json.dumps = patched_dumps

# Патчим методы для metrics_collector
from app.utils.metrics import get_metrics_collector
metrics_collector = get_metrics_collector()

# Добавляем недостающие методы
if not hasattr(metrics_collector, 'task_created'):
    metrics_collector.task_created = lambda task_id: None

if not hasattr(metrics_collector, 'task_status_update'):
    metrics_collector.task_status_update = lambda task_id, status, progress: None
    
if not hasattr(metrics_collector, 'decrement_counter'):
    metrics_collector.decrement_counter = lambda counter_name: None

from app.web.app import app
from app.web.models import UploadResponse, StatusResponse, ProtocolsResponse, ProcessingStatus
from app.web.api_routes import tasks_info, update_task_status

client = TestClient(app)

@pytest.fixture
def mock_pipeline():
    """Мок для Pipeline сервиса"""
    with patch("app.web.api_routes.pipeline") as mock:
        yield mock

@pytest.fixture
def mock_uuid():
    """Мок для uuid.uuid4"""
    with patch("uuid.uuid4") as mock:
        mock.return_value = "test-task-id"
        yield mock

@pytest.fixture
def mock_completed_tasks():
    """Мок для завершенных задач с протоколами"""
    # Создаем временные файлы для тестов
    test_dir = Path("test_protocols")
    test_dir.mkdir(exist_ok=True)
    
    # Создаем тестовые JSON-файлы протоколов
    protocol1_path = test_dir / "protocol-1.json"
    protocol2_path = test_dir / "protocol-2.json"
    
    protocol1_data = {
        "metadata": {
            "title": "Meeting 1",
            "date": "2025-05-24",
            "language": "ru"
        },
        "summary": "Summary of meeting 1",
        "participants": ["John Doe", "Jane Smith"],
        "agenda_items": ["Item 1", "Item 2"],
        "decisions": ["Decision 1", "Decision 2"],
        "action_items": ["Action 1", "Action 2"],
        "created_at": "2025-05-24T12:00:00"
    }
    
    protocol2_data = {
        "metadata": {
            "title": "Meeting 2",
            "date": "2025-05-25",
            "language": "en"
        },
        "summary": "Summary of meeting 2",
        "participants": ["Alice", "Bob"],
        "agenda_items": ["Item A", "Item B"],
        "decisions": ["Decision A", "Decision B"],
        "action_items": ["Action A", "Action B"],
        "created_at": "2025-05-25T12:00:00"
    }
    
    with open(protocol1_path, "w") as f:
        json.dump(protocol1_data, f)
    
    with open(protocol2_path, "w") as f:
        json.dump(protocol2_data, f)
    
    # Создаем патч для tasks_info
    tasks_info_patch = {
        "protocol-1": {
            "status": ProcessingStatus.COMPLETED.value,
            "progress": 100,
            "message": "Task completed",
            "result": {
                "protocol_id": "protocol-1",
                "files": {
                    "json": str(protocol1_path)
                }
            },
            "created_at": "2025-05-24T10:00:00Z"
        },
        "protocol-2": {
            "status": ProcessingStatus.COMPLETED.value,
            "progress": 100,
            "message": "Task completed",
            "result": {
                "protocol_id": "protocol-2",
                "files": {
                    "json": str(protocol2_path)
                }
            },
            "created_at": "2025-05-25T10:00:00Z"
        }
    }
    
    try:
        with patch.dict("app.web.api_routes.tasks_info", tasks_info_patch, clear=True):
            yield tasks_info_patch
    finally:
        # Удаляем тестовые файлы
        if protocol1_path.exists():
            os.remove(protocol1_path)
        if protocol2_path.exists():
            os.remove(protocol2_path)
        
        # Удаляем тестовую директорию, если она пуста
        try:
            test_dir.rmdir()
        except OSError:
            pass

@pytest.fixture
def mock_background_tasks():
    """Мок для BackgroundTasks"""
    mock = MagicMock()
    return mock

def test_upload_audio(mock_pipeline, mock_uuid, mock_background_tasks):
    """Тест загрузки аудиофайла"""
    # Создаем тестовый файл
    test_file_path = Path("test_audio.mp3")
    with open(test_file_path, "wb") as f:
        f.write(b"test audio content")
    
    try:
        # Патчим функцию add_task
        with patch("app.web.api_routes.BackgroundTasks.add_task") as mock_add_task:
            # Отправляем запрос
            with open(test_file_path, "rb") as f:
                response = client.post(
                    "/api/v1/upload",
                    files={"file": ("test_audio.mp3", f, "audio/mpeg")},
                    data={
                        "title": "Test Meeting",
                        "date": "2025-05-25",
                        "language": "ru"
                    }
                )
            
            # Проверяем результат
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-id"
            assert data["status"] == "pending"
            
            # Проверяем, что фоновая задача была добавлена
            mock_add_task.assert_called_once()
    finally:
        # Удаляем тестовый файл
        if test_file_path.exists():
            os.remove(test_file_path)

def test_upload_transcript(mock_pipeline, mock_uuid, mock_background_tasks):
    """Тест загрузки JSON-транскрипта"""
    # Создаем тестовый файл
    test_file_path = Path("test_transcript.json")
    transcript_data = {
        "text": "This is a test transcript",
        "segments": [
            {"start": 0, "end": 5, "text": "This is a test"}
        ]
    }
    
    with open(test_file_path, "w") as f:
        json.dump(transcript_data, f)
    
    try:
        # Патчим функцию add_task
        with patch("app.web.api_routes.BackgroundTasks.add_task") as mock_add_task:
            # Отправляем запрос
            with open(test_file_path, "rb") as f:
                response = client.post(
                    "/api/v1/upload",
                    files={"file": ("test_transcript.json", f, "application/json")},
                    data={
                        "title": "Test Meeting",
                        "date": "2025-05-25",
                        "language": "ru",
                        "is_transcript": "True"
                    }
                )
            
            # Проверяем результат
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-id"
            assert data["status"] == "pending"
            
            # Проверяем, что фоновая задача была добавлена
            mock_add_task.assert_called_once()
    finally:
        # Удаляем тестовый файл
        if test_file_path.exists():
            os.remove(test_file_path)

def test_get_task_status():
    """Тест получения статуса задачи"""
    # Настраиваем задачу в tasks_info
    task_id = "test-task-789"
    
    # Патчим tasks_info
    with patch.dict("app.web.api_routes.tasks_info", {
        task_id: {
            "status": ProcessingStatus.COMPLETED.value,
            "progress": 100,
            "message": "Task completed",
            "result": {"protocol_id": "test-protocol-123"},
            "created_at": "2025-05-25T10:00:00Z"
        }
    }):
        # Отправляем запрос
        response = client.get(f"/api/v1/status/{task_id}")
        
        # Проверяем результат
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] == "completed"
        assert data["progress"] == 100
        assert data["message"] == "Task completed"

def test_get_tasks():
    """Тест получения списка задач"""
    # Патчим tasks_info
    with patch.dict("app.web.api_routes.tasks_info", {
        "task-1": {
            "status": ProcessingStatus.COMPLETED.value,
            "progress": 100,
            "message": "Task completed",
            "result": {"protocol_id": "protocol-1"},
            "created_at": "2025-05-24T10:00:00Z"
        },
        "task-2": {
            "status": ProcessingStatus.PROCESSING.value,
            "progress": 50,
            "message": "Processing transcript",
            "result": None,
            "created_at": "2025-05-25T10:00:00Z"
        }
    }):
        # Отправляем запрос
        response = client.get("/api/v1/tasks")
        
        # Проверяем результат
        assert response.status_code == 200
        data = response.json()
        
        # Проверяем, что в ответе есть задачи
        assert "tasks" in data
        assert len(data["tasks"]) > 0
        
        # Проверяем, что наши тестовые задачи присутствуют в ответе
        task_ids = [task["task_id"] for task in data["tasks"]]
        assert "task-1" in task_ids
        assert "task-2" in task_ids
        
        # Проверяем содержимое наших тестовых задач
        tasks = {task["task_id"]: task for task in data["tasks"]}
        assert tasks["task-1"]["status"] == "completed"
        assert tasks["task-2"]["status"] == "processing"

def test_get_protocols(mock_completed_tasks):
    """Тест получения списка протоколов"""
    # Отправляем запрос
    response = client.get("/api/v1/protocols")
    
    # Проверяем результат
    assert response.status_code == 200
    data = response.json()
    assert len(data["protocols"]) == 2
    
    # Проверяем содержимое протоколов
    protocol_titles = [p["metadata"]["title"] for p in data["protocols"]]
    assert "Meeting 1" in protocol_titles
    assert "Meeting 2" in protocol_titles
    
    # Проверяем, что все обязательные поля присутствуют
    for protocol in data["protocols"]:
        assert "metadata" in protocol
        assert "summary" in protocol
        assert "participants" in protocol
        assert "agenda_items" in protocol
        assert "decisions" in protocol
        assert "action_items" in protocol

@pytest.fixture
def mock_protocol_file():
    """Мок для файла протокола"""
    # Создаем временную директорию для тестов
    test_dir = Path("test_protocol_files")
    test_dir.mkdir(exist_ok=True)
    
    # Создаем тестовый JSON-файл протокола
    protocol_id = "test-protocol-123"
    protocol_path = test_dir / f"{protocol_id}.json"
    markdown_path = test_dir / f"{protocol_id}.md"
    
    protocol_data = {
        "metadata": {
            "title": "Test Meeting",
            "date": "2025-05-25",
            "language": "ru",
            "location": "Конференц-зал",
            "organizer": "Иван Иванов"
        },
        "summary": "This is a test summary",
        "participants": ["John Doe", "Jane Smith"],
        "agenda_items": ["Item 1", "Item 2"],
        "decisions": ["Decision 1", "Decision 2"],
        "action_items": ["Action 1", "Action 2"],
        "created_at": "2025-05-25T12:00:00"
    }
    
    # Создаем JSON-файл
    with open(protocol_path, "w") as f:
        json.dump(protocol_data, f)
    
    # Создаем Markdown-файл
    markdown_content = "# Test Meeting\n\n## Summary\nThis is a test summary\n\n## Participants\n- John Doe\n- Jane Smith"
    with open(markdown_path, "w") as f:
        f.write(markdown_content)
    
    # Создаем патч для tasks_info
    tasks_info_patch = {
        protocol_id: {
            "status": "completed",
            "progress": 100,
            "message": "Task completed",
            "markdown_file": str(markdown_path),
            "json_file": str(protocol_path),
            "created_at": "2025-05-25T10:00:00Z"
        }
    }
    
    try:
        # Получаем ссылку на tasks_info и добавляем тестовые данные
        from app.web.api_routes import tasks_info
        tasks_info.update(tasks_info_patch)
        
        yield {
            "protocol_id": protocol_id,
            "protocol_data": protocol_data,
            "markdown_content": markdown_content,
            "json_path": protocol_path,
            "markdown_path": markdown_path
        }
    finally:
        # Удаляем тестовые файлы
        if protocol_path.exists():
            os.remove(protocol_path)
        if markdown_path.exists():
            os.remove(markdown_path)
        
        # Удаляем тестовую директорию, если она пуста
        try:
            test_dir.rmdir()
        except OSError:
            pass

def test_get_protocol(mock_protocol_file):
    """Тест получения протокола по ID"""
    protocol_id = mock_protocol_file["protocol_id"]
    
    # Отправляем запрос
    response = client.get(f"/api/v1/protocols/{protocol_id}")
    
    # Проверяем результат
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["title"] == "Test Meeting"
    assert data["metadata"]["date"] == "2025-05-25"
    assert data["metadata"]["language"] == "ru"
    assert data["summary"] == "This is a test summary"
    assert len(data["participants"]) == 2
    assert len(data["agenda_items"]) == 2
    assert len(data["decisions"]) == 2
    assert len(data["action_items"]) == 2

def test_download_protocol_markdown(mock_protocol_file):
    """Тест скачивания протокола в формате Markdown"""
    protocol_id = mock_protocol_file["protocol_id"]
    markdown_content = mock_protocol_file["markdown_content"]
    
    # Отправляем запрос
    response = client.get(f"/api/v1/protocols/{protocol_id}/download?format=markdown")
    
    # Проверяем результат
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown"
    assert response.headers["content-disposition"] == f'attachment; filename="protocol_{protocol_id}.md"'
    assert response.content.decode() == markdown_content

def test_download_protocol_json(mock_protocol_file):
    """Тест скачивания протокола в формате JSON"""
    protocol_id = mock_protocol_file["protocol_id"]
    protocol_data = mock_protocol_file["protocol_data"]
    
    # Отправляем запрос
    response = client.get(f"/api/v1/protocols/{protocol_id}/download?format=json")
    
    # Проверяем результат
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"] == f'attachment; filename="protocol_{protocol_id}.json"'
    
    # Проверяем содержимое JSON
    response_data = json.loads(response.content)
    assert response_data["metadata"]["title"] == protocol_data["metadata"]["title"]
    assert response_data["metadata"]["date"] == protocol_data["metadata"]["date"]
    assert response_data["summary"] == protocol_data["summary"]
    assert len(response_data["participants"]) == len(protocol_data["participants"])
