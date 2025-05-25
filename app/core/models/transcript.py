"""
Модели данных для транскрипций
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from datetime import datetime

@dataclass
class TranscriptSegment:
    """
    Сегмент транскрипции с информацией о спикере и таймштампах
    """
    text: str
    start: float  # Время начала в секундах
    end: float  # Время окончания в секундах
    speaker: str  # Идентификатор спикера (например, "SPEAKER_00")
    speaker_confidence: Optional[float] = None  # Уверенность в определении спикера
    id: Optional[str] = None  # Идентификатор сегмента
    
    def duration(self) -> float:
        """Возвращает продолжительность сегмента в секундах"""
        return self.end - self.start
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует сегмент в словарь"""
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "speaker": self.speaker,
            "speaker_confidence": self.speaker_confidence,
            "id": self.id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TranscriptSegment":
        """
        Создает сегмент из словаря
        
        Args:
            data: Словарь с данными сегмента
            
        Returns:
            Объект TranscriptSegment
        """
        return cls(
            text=data["text"],
            start=data["start"],
            end=data["end"],
            speaker=data.get("speaker", "UNKNOWN"),
            speaker_confidence=data.get("speaker_confidence"),
            id=data.get("id"),
        )

@dataclass
class Transcript:
    """
    Полная транскрипция с метаданными
    """
    segments: List[TranscriptSegment]
    audio_path: str
    language: str
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def total_duration(self) -> float:
        """Возвращает общую продолжительность транскрипции в секундах"""
        if not self.segments:
            return 0.0
        return max(segment.end for segment in self.segments)
    
    def speaker_count(self) -> int:
        """Возвращает количество уникальных спикеров"""
        return len(set(segment.speaker for segment in self.segments))
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует транскрипцию в словарь"""
        return {
            "segments": [segment.to_dict() for segment in self.segments],
            "audio_path": self.audio_path,
            "language": self.language,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transcript":
        """
        Создает транскрипцию из словаря
        
        Args:
            data: Словарь с данными транскрипции
            
        Returns:
            Объект Transcript
        """
        segments = [TranscriptSegment.from_dict(segment) for segment in data["segments"]]
        
        # Преобразуем строку даты/времени в объект datetime
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        else:
            created_at = datetime.now()
        
        return cls(
            segments=segments,
            audio_path=data["audio_path"],
            language=data["language"],
            created_at=created_at,
            metadata=data.get("metadata", {}),
        )
    
    def get_text_by_speaker(self) -> Dict[str, str]:
        """
        Возвращает словарь с текстом от каждого спикера
        
        Returns:
            Словарь, где ключи - идентификаторы спикеров, значения - их речь
        """
        result = {}
        for segment in self.segments:
            if segment.speaker not in result:
                result[segment.speaker] = ""
            result[segment.speaker] += f" {segment.text}"
        
        # Удаляем лишние пробелы
        for speaker in result:
            result[speaker] = result[speaker].strip()
        
        return result
    
    def get_full_text(self) -> str:
        """
        Возвращает полный текст транскрипции
        
        Returns:
            Строка с полным текстом
        """
        return " ".join(segment.text for segment in self.segments)
