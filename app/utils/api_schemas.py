"""
Схемы данных для API веб-интерфейса
"""
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator

class TaskStatus(str, Enum):
    """Статусы задачи"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ProcessingStage(str, Enum):
    """Этапы обработки"""
    INITIALIZATION = "initialization"
    AUDIO_LOADING = "audio_loading"
    TRANSCRIPTION = "transcription"
    TRANSCRIPT_LOADING = "transcript_loading"
    TRANSCRIPT_CONVERSION = "transcript_conversion"
    ANALYSIS = "analysis"
    PROTOCOL_GENERATION = "protocol_generation"
    SAVING = "saving"
    NOTIFICATION = "notification"
    COMPLETION = "completion"

class AudioUploadRequest(BaseModel):
    """Запрос на загрузку аудиофайла"""
    title: Optional[str] = Field(None, description="Название встречи")
    date: Optional[str] = Field(None, description="Дата встречи в формате YYYY-MM-DD")
    location: Optional[str] = Field(None, description="Место проведения встречи")
    organizer: Optional[str] = Field(None, description="Организатор встречи")
    participants: Optional[str] = Field(None, description="Список участников (через запятую)")
    agenda: Optional[str] = Field(None, description="Повестка встречи")
    language: Optional[str] = Field(None, description="Язык аудио (например, 'ru', 'en', 'de')")
    skip_notifications: bool = Field(False, description="Пропустить отправку уведомлений")
    is_transcript: bool = Field(False, description="Файл является JSON-транскриптом")
    
    @validator('date')
    def validate_date(cls, v):
        """Валидация даты"""
        if v:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Дата должна быть в формате YYYY-MM-DD")
        return v

class TaskResponse(BaseModel):
    """Ответ на создание задачи"""
    task_id: str = Field(..., description="Уникальный идентификатор задачи")
    message: str = Field(..., description="Сообщение о создании задачи")
    status: TaskStatus = Field(TaskStatus.PENDING, description="Статус задачи")

class TaskStatusResponse(BaseModel):
    """Ответ на запрос статуса задачи"""
    task_id: str = Field(..., description="Уникальный идентификатор задачи")
    status: TaskStatus = Field(..., description="Статус задачи")
    progress: float = Field(..., description="Прогресс выполнения (от 0.0 до 1.0)")
    message: str = Field(..., description="Сообщение о текущем этапе обработки")
    stage: ProcessingStage = Field(..., description="Текущий этап обработки")
    created_at: datetime = Field(..., description="Время создания задачи")
    updated_at: datetime = Field(..., description="Время последнего обновления статуса")
    result: Optional[Dict[str, Any]] = Field(None, description="Результат выполнения задачи (если завершена)")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class TaskListResponse(BaseModel):
    """Ответ на запрос списка задач"""
    tasks: List[TaskStatusResponse] = Field(..., description="Список задач")
    count: int = Field(..., description="Общее количество задач")

class ProtocolSegment(BaseModel):
    """Сегмент протокола"""
    speaker: str = Field(..., description="Идентификатор говорящего")
    text: str = Field(..., description="Текст сегмента")
    start: float = Field(..., description="Время начала сегмента (в секундах)")
    end: float = Field(..., description="Время окончания сегмента (в секундах)")

class Participant(BaseModel):
    """Участник встречи"""
    name: str = Field(..., description="Имя участника")
    role: Optional[str] = Field(None, description="Роль участника")

class AgendaItem(BaseModel):
    """Пункт повестки"""
    topic: str = Field(..., description="Тема")
    description: Optional[str] = Field(None, description="Описание")

class Decision(BaseModel):
    """Решение"""
    decision: str = Field(..., description="Текст решения")
    context: Optional[str] = Field(None, description="Контекст принятия решения")

class ActionItem(BaseModel):
    """Задача"""
    action: str = Field(..., description="Текст задачи")
    assignee: Optional[str] = Field(None, description="Ответственный")
    due_date: Optional[str] = Field(None, description="Срок выполнения")

class Protocol(BaseModel):
    """Протокол встречи"""
    metadata: Dict[str, Any] = Field(..., description="Метаданные протокола")
    participants: List[Participant] = Field([], description="Участники встречи")
    agenda_items: List[AgendaItem] = Field([], description="Пункты повестки")
    summary: str = Field(..., description="Краткое содержание встречи")
    decisions: List[Decision] = Field([], description="Принятые решения")
    action_items: List[ActionItem] = Field([], description="Поставленные задачи")
    created_at: datetime = Field(..., description="Время создания протокола")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ErrorResponse(BaseModel):
    """Ответ с ошибкой"""
    detail: str = Field(..., description="Описание ошибки")
    error_code: Optional[str] = Field(None, description="Код ошибки")
    timestamp: datetime = Field(default_factory=datetime.now, description="Время возникновения ошибки")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
