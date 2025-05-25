"""
Модели данных для протоколов совещаний
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from datetime import datetime, date

@dataclass
class ActionItem:
    """
    Задача/пункт действия из протокола
    """
    what: str  # Описание задачи
    who: str  # Ответственный
    due: Optional[str] = None  # Срок выполнения (в формате YYYY-MM-DD)
    status: str = "Open"  # Статус задачи (Open, In Progress, Done и т.д.)
    id: Optional[str] = None  # Идентификатор задачи (например, "A001")
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует задачу в словарь"""
        return {
            "what": self.what,
            "who": self.who,
            "due": self.due,
            "status": self.status,
            "id": self.id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionItem":
        """
        Создает задачу из словаря
        
        Args:
            data: Словарь с данными задачи
            
        Returns:
            Объект ActionItem
        """
        return cls(
            what=data["what"],
            who=data["who"],
            due=data.get("due"),
            status=data.get("status", "Open"),
            id=data.get("id"),
        )

@dataclass
class Decision:
    """
    Решение из протокола
    """
    description: str  # Описание решения
    id: Optional[str] = None  # Идентификатор решения (например, "D001")
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует решение в словарь"""
        return {
            "description": self.description,
            "id": self.id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Decision":
        """
        Создает решение из словаря
        
        Args:
            data: Словарь с данными решения
            
        Returns:
            Объект Decision
        """
        if isinstance(data, str):
            # Если передана просто строка, создаем решение без ID
            return cls(description=data)
        
        return cls(
            description=data["description"] if "description" in data else data.get("text", ""),
            id=data.get("id"),
        )

@dataclass
class AgendaItem:
    """
    Пункт повестки дня
    """
    topic: str  # Тема пункта повестки
    discussion_summary: str  # Краткий итог обсуждения
    decisions_made: List[Union[Decision, str]] = field(default_factory=list)  # Принятые решения
    action_items_assigned: List[ActionItem] = field(default_factory=list)  # Назначенные задачи
    id: Optional[str] = None  # Идентификатор пункта повестки (например, "T001")
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует пункт повестки в словарь"""
        decisions = []
        for decision in self.decisions_made:
            if isinstance(decision, Decision):
                decisions.append(decision.to_dict())
            else:
                decisions.append({"description": decision})
        
        return {
            "topic": self.topic,
            "discussion_summary": self.discussion_summary,
            "decisions_made": decisions,
            "action_items_assigned": [item.to_dict() for item in self.action_items_assigned],
            "id": self.id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgendaItem":
        """
        Создает пункт повестки из словаря
        
        Args:
            data: Словарь с данными пункта повестки
            
        Returns:
            Объект AgendaItem
        """
        decisions = []
        for decision_data in data.get("decisions_made", []):
            if isinstance(decision_data, str):
                decisions.append(Decision(description=decision_data))
            else:
                decisions.append(Decision.from_dict(decision_data))
        
        actions = [ActionItem.from_dict(action) for action in data.get("action_items_assigned", [])]
        
        return cls(
            topic=data["topic"],
            discussion_summary=data.get("discussion_summary", ""),
            decisions_made=decisions,
            action_items_assigned=actions,
            id=data.get("id"),
        )

@dataclass
class Participant:
    """
    Участник совещания
    """
    name: str  # Имя участника
    role: Optional[str] = None  # Роль участника
    present: bool = True  # Присутствовал ли участник
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует участника в словарь"""
        return {
            "name": self.name,
            "role": self.role,
            "present": self.present,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Participant":
        """
        Создает участника из словаря
        
        Args:
            data: Словарь с данными участника
            
        Returns:
            Объект Participant
        """
        if isinstance(data, str):
            # Если передана просто строка, создаем участника только с именем
            return cls(name=data)
        
        return cls(
            name=data["name"],
            role=data.get("role"),
            present=data.get("present", True),
        )

@dataclass
class Protocol:
    """
    Полный протокол совещания
    """
    metadata: Dict[str, Any]  # Метаданные (заголовок, дата, место и т.д.)
    participants: List[Participant]  # Участники
    agenda_items: List[AgendaItem]  # Пункты повестки
    summary: str  # Общее резюме совещания
    decisions: List[Decision] = field(default_factory=list)  # Глобальные решения
    action_items: List[ActionItem] = field(default_factory=list)  # Глобальные задачи
    created_at: datetime = field(default_factory=datetime.now)  # Дата создания протокола
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует протокол в словарь"""
        # Обработка участников
        participants_list = []
        for participant in self.participants:
            if hasattr(participant, 'to_dict'):
                participants_list.append(participant.to_dict())
            else:
                participants_list.append(str(participant))
        
        # Обработка пунктов повестки
        agenda_items_list = []
        for item in self.agenda_items:
            if hasattr(item, 'to_dict'):
                agenda_items_list.append(item.to_dict())
            else:
                agenda_items_list.append(str(item))
        
        # Обработка решений
        decisions_list = []
        for decision in self.decisions:
            if hasattr(decision, 'to_dict'):
                decisions_list.append(decision.to_dict())
            elif isinstance(decision, dict):
                decisions_list.append(decision)
            else:
                decisions_list.append({"decision": str(decision)})
        
        # Обработка задач
        action_items_list = []
        for item in self.action_items:
            if hasattr(item, 'to_dict'):
                action_items_list.append(item.to_dict())
            elif isinstance(item, dict):
                action_items_list.append(item)
            else:
                action_items_list.append({"action": str(item)})
        
        return {
            "metadata": self.metadata,
            "participants": participants_list,
            "agenda_items": agenda_items_list,
            "summary": self.summary,
            "decisions": decisions_list,
            "action_items": action_items_list,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Protocol":
        """
        Создает протокол из словаря
        
        Args:
            data: Словарь с данными протокола
            
        Returns:
            Объект Protocol
        """
        participants = []
        for participant_data in data.get("participants", []):
            participants.append(Participant.from_dict(participant_data))
        
        agenda_items = []
        for item_data in data.get("agenda_items", []):
            agenda_items.append(AgendaItem.from_dict(item_data))
        
        decisions = []
        for decision_data in data.get("decisions", []):
            decisions.append(Decision.from_dict(decision_data))
        
        action_items = []
        for action_data in data.get("action_items", []):
            action_items.append(ActionItem.from_dict(action_data))
        
        # Преобразуем строку даты/времени в объект datetime
        created_at = data.get("created_at")
        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        else:
            created_at = datetime.now()
        
        return cls(
            metadata=data.get("metadata", {}),
            participants=participants,
            agenda_items=agenda_items,
            summary=data.get("summary", ""),
            decisions=decisions,
            action_items=action_items,
            created_at=created_at,
        )
    
    def to_egl_json(self) -> Dict[str, Any]:
        """
        Преобразует протокол в формат JSON согласно схеме egl_protokoll.json
        
        Returns:
            Словарь в формате, соответствующем схеме egl_protokoll.json
        """
        # Метаданные
        meta = {
            "titel": self.metadata.get("title", "Protokoll"),
            "datum": self.metadata.get("date", datetime.now().strftime("%Y-%m-%d")),
            "ort": self.metadata.get("location", ""),
            "sitzungsleiter": self.metadata.get("organizer", ""),
            "verfasser": self.metadata.get("author", "AI Assistant"),
        }
        
        # Участники
        present = []
        excused = []
        for participant in self.participants:
            if participant.present:
                present.append(participant.name)
            else:
                excused.append(participant.name)
        
        teilnehmer = {
            "anwesend": present,
            "entschuldigt": excused,
        }
        
        # Пункты повестки
        traktanden = []
        for i, item in enumerate(self.agenda_items):
            traktand = {
                "id": item.id or f"T{i+1:03d}",
                "titel": item.topic,
                "diskussion": item.discussion_summary,
                "entscheidungen": [
                    decision.description if isinstance(decision, Decision) else decision
                    for decision in item.decisions_made
                ],
                "pendenzen": [
                    {
                        "wer": action.who,
                        "was": action.what,
                        "frist": action.due,
                    }
                    for action in item.action_items_assigned
                ],
            }
            traktanden.append(traktand)
        
        # Составляем финальный словарь
        return {
            "meta": meta,
            "teilnehmer": teilnehmer,
            "traktanden": traktanden,
            "anhänge": self.metadata.get("attachments", []),
        }
