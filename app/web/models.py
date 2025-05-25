"""
Модели данных для веб-интерфейса
"""
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel, Field, EmailStr, HttpUrl, validator

class ProcessingStatus(str, Enum):
    """
    Статусы обработки аудиофайла
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class MeetingInfo(BaseModel):
    """
    Информация о встрече
    """
    title: str
    date: date
    location: Optional[str] = None
    organizer: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "properties": {
                "title": {"description": "Название встречи"},
                "date": {"description": "Дата встречи"},
                "location": {"description": "Место проведения встречи"},
                "organizer": {"description": "Организатор встречи"}
            }
        }
    }

class UploadResponse(BaseModel):
    """
    Ответ на загрузку аудиофайла
    """
    task_id: str
    message: str
    status: ProcessingStatus = ProcessingStatus.PENDING
    
    model_config = {
        "json_schema_extra": {
            "properties": {
                "task_id": {"description": "Идентификатор задачи"},
                "message": {"description": "Сообщение о статусе"},
                "status": {"description": "Статус обработки"}
            }
        }
    }

class StatusResponse(BaseModel):
    """
    Ответ на запрос статуса обработки
    """
    task_id: str
    status: ProcessingStatus
    progress: float
    message: str
    estimated_completion: Optional[datetime] = None
    
    model_config = {
        "json_schema_extra": {
            "properties": {
                "task_id": {"description": "Идентификатор задачи"},
                "status": {"description": "Статус обработки"},
                "progress": {"description": "Прогресс обработки в процентах", "minimum": 0, "maximum": 100},
                "message": {"description": "Дополнительная информация о статусе"},
                "estimated_completion": {"description": "Предполагаемое время завершения"}
            }
        }
    }

class ParticipantBase(BaseModel):
    """
    Базовая модель участника
    """
    name: str
    role: Optional[str] = None
    email: Optional[EmailStr] = None
    
    model_config = {
        "json_schema_extra": {
            "properties": {
                "name": {"description": "Имя участника"},
                "role": {"description": "Роль участника"},
                "email": {"description": "Email участника"}
            }
        }
    }

class AgendaItemBase(BaseModel):
    """
    Базовая модель пункта повестки
    """
    title: str
    notes: Optional[str] = None
    duration: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "properties": {
                "title": {"description": "Заголовок пункта повестки"},
                "notes": {"description": "Заметки по пункту повестки"},
                "duration": {"description": "Продолжительность обсуждения"}
            }
        }
    }

class DecisionBase(BaseModel):
    """
    Базовая модель решения
    """
    text: str
    owner: Optional[str] = None
    context: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "properties": {
                "text": {"description": "Текст решения"},
                "owner": {"description": "Ответственный за решение"},
                "context": {"description": "Контекст принятия решения"}
            }
        }
    }

class ActionItemBase(BaseModel):
    """
    Базовая модель задачи
    """
    text: str
    owner: Optional[str] = None
    due_date: Optional[date] = None
    
    model_config = {
        "json_schema_extra": {
            "properties": {
                "text": {"description": "Текст задачи"},
                "owner": {"description": "Ответственный"},
                "due_date": {"description": "Срок выполнения"}
            }
        }
    }

class ProtocolMetadata(BaseModel):
    """
    Метаданные протокола
    """
    title: str
    date: date
    location: Optional[str] = None
    organizer: Optional[str] = None
    language: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "properties": {
                "title": {"description": "Название встречи"},
                "date": {"description": "Дата встречи"},
                "location": {"description": "Место проведения встречи"},
                "organizer": {"description": "Организатор встречи"},
                "language": {"description": "Язык протокола"}
            }
        }
    }

class Protocol(BaseModel):
    """
    Модель протокола встречи
    """
    metadata: ProtocolMetadata
    summary: str
    participants: List[Union[str, ParticipantBase]] = []
    agenda_items: List[Union[str, AgendaItemBase]] = []
    decisions: List[Union[str, DecisionBase]] = []
    action_items: List[Union[str, ActionItemBase]] = []
    created_at: datetime = Field(default_factory=datetime.now)
    
    model_config = {
        "json_schema_extra": {
            "properties": {
                "metadata": {"description": "Метаданные протокола"},
                "summary": {"description": "Краткое содержание встречи"},
                "participants": {"description": "Участники встречи"},
                "agenda_items": {"description": "Пункты повестки"},
                "decisions": {"description": "Принятые решения"},
                "action_items": {"description": "Поставленные задачи"},
                "created_at": {"description": "Время создания протокола"}
            },
            "example": {
                "metadata": {
                    "title": "Еженедельное совещание",
                    "date": "2025-05-25",
                    "location": "Конференц-зал",
                    "organizer": "Иван Иванов",
                    "language": "ru"
                },
                "summary": "Обсуждение текущих проектов и планирование на следующую неделю",
                "participants": [
                    "Иван Иванов",
                    {
                        "name": "Петр Петров",
                        "role": "Менеджер проекта",
                        "email": "petr@example.com"
                    }
                ],
                "agenda_items": [
                    "Обзор текущих проектов",
                    {
                        "title": "Планирование на следующую неделю",
                        "notes": "Обсуждение приоритетов и распределение задач"
                    }
                ],
                "decisions": [
                    "Утвердить план работ на следующую неделю",
                    {
                        "text": "Выделить дополнительные ресурсы для проекта X",
                        "owner": "Иван Иванов"
                    }
                ],
                "action_items": [
                    "Подготовить отчет о проделанной работе",
                    {
                        "text": "Организовать встречу с клиентом",
                        "owner": "Петр Петров",
                        "due_date": "2025-06-01"
                    }
                ],
                "created_at": "2025-05-25T10:00:00Z"
            }
        }
    }

class ErrorResponse(BaseModel):
    """
    Модель ответа с ошибкой
    """
    detail: str
    status_code: int
    path: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
    model_config = {
        "json_schema_extra": {
            "properties": {
                "detail": {"description": "Детальное описание ошибки"},
                "status_code": {"description": "HTTP-код ошибки"},
                "path": {"description": "Путь, на котором произошла ошибка"},
                "timestamp": {"description": "Время возникновения ошибки"}
            }
        }
    }

# Модели для списков задач и протоколов

class TaskInfo(BaseModel):
    """
    Информация о задаче
    """
    task_id: str = Field(..., description="Идентификатор задачи")
    status: ProcessingStatus = Field(..., description="Статус обработки")
    message: str = Field("", description="Дополнительная информация о статусе")
    progress: float = Field(0, ge=0, le=100, description="Прогресс обработки в процентах")
    created_at: str = Field(..., description="Время создания задачи")
    updated_at: str = Field(..., description="Время последнего обновления задачи")
    file_name: Optional[str] = Field(None, description="Имя файла")
    task_type: str = Field("audio_processing", description="Тип задачи")

class TasksResponse(BaseModel):
    """
    Ответ на запрос списка задач
    """
    tasks: List[TaskInfo] = Field([], description="Список задач")

class ProtocolsResponse(BaseModel):
    """
    Ответ на запрос списка протоколов
    """
    protocols: List[Protocol] = Field([], description="Список протоколов")

# Модели для конвертации из внутренних моделей
class ProtocolResponse(Protocol):
    """
    Модель ответа с протоколом
    """
    
    @classmethod
    def from_internal(cls, protocol: Any) -> 'ProtocolResponse':
        """
        Создает модель ответа из внутренней модели протокола
        
        Args:
            protocol: Внутренняя модель протокола
            
        Returns:
            Модель ответа с протоколом
        """
        # Преобразуем внутреннюю модель в словарь
        data = protocol.to_dict() if hasattr(protocol, 'to_dict') else protocol
        
        return cls.model_validate(data)
