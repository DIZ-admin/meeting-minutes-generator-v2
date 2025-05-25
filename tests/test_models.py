"""
Тесты для моделей данных
"""
import pytest
import json
from datetime import datetime
from pathlib import Path

import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, parent_dir)

from app.core.models.transcript import Transcript, TranscriptSegment
from app.core.models.protocol import Protocol, AgendaItem, Decision, ActionItem, Participant

class TestTranscriptModel:
    """Тесты для модели Transcript"""

    def test_transcript_segment_init(self):
        """Проверка создания объекта TranscriptSegment"""
        segment = TranscriptSegment(
            text="Hello, this is a test",
            start=0.0,
            end=5.0,
            speaker="SPEAKER_01",
            speaker_confidence=0.95,
            id="segment_1"
        )
        
        assert segment.text == "Hello, this is a test"
        assert segment.start == 0.0
        assert segment.end == 5.0
        assert segment.speaker == "SPEAKER_01"
        assert segment.speaker_confidence == 0.95
        assert segment.id == "segment_1"
    
    def test_transcript_segment_duration(self):
        """Проверка метода duration объекта TranscriptSegment"""
        segment = TranscriptSegment(
            text="Hello, this is a test",
            start=10.5,
            end=15.25,
            speaker="SPEAKER_01"
        )
        
        assert segment.duration() == 4.75
    
    def test_transcript_segment_to_dict(self):
        """Проверка метода to_dict объекта TranscriptSegment"""
        segment = TranscriptSegment(
            text="Hello, this is a test",
            start=0.0,
            end=5.0,
            speaker="SPEAKER_01",
            speaker_confidence=0.95,
            id="segment_1"
        )
        
        expected = {
            "text": "Hello, this is a test",
            "start": 0.0,
            "end": 5.0,
            "speaker": "SPEAKER_01",
            "speaker_confidence": 0.95,
            "id": "segment_1"
        }
        
        assert segment.to_dict() == expected
    
    def test_transcript_segment_from_dict(self):
        """Проверка метода from_dict объекта TranscriptSegment"""
        data = {
            "text": "Hello, this is a test",
            "start": 0.0,
            "end": 5.0,
            "speaker": "SPEAKER_01",
            "speaker_confidence": 0.95,
            "id": "segment_1"
        }
        
        segment = TranscriptSegment.from_dict(data)
        
        assert segment.text == "Hello, this is a test"
        assert segment.start == 0.0
        assert segment.end == 5.0
        assert segment.speaker == "SPEAKER_01"
        assert segment.speaker_confidence == 0.95
        assert segment.id == "segment_1"
    
    def test_transcript_init(self):
        """Проверка создания объекта Transcript"""
        segments = [
            TranscriptSegment(
                text="Hello, this is segment 1",
                start=0.0,
                end=5.0,
                speaker="SPEAKER_01"
            ),
            TranscriptSegment(
                text="This is segment 2",
                start=5.0,
                end=10.0,
                speaker="SPEAKER_02"
            )
        ]
        
        transcript = Transcript(
            segments=segments,
            audio_path="/path/to/audio.mp3",
            language="en",
            metadata={"sample_rate": 16000}
        )
        
        assert len(transcript.segments) == 2
        assert transcript.audio_path == "/path/to/audio.mp3"
        assert transcript.language == "en"
        assert transcript.metadata == {"sample_rate": 16000}
    
    def test_transcript_total_duration(self):
        """Проверка метода total_duration объекта Transcript"""
        segments = [
            TranscriptSegment(
                text="Hello, this is segment 1",
                start=0.0,
                end=5.0,
                speaker="SPEAKER_01"
            ),
            TranscriptSegment(
                text="This is segment 2",
                start=5.0,
                end=10.0,
                speaker="SPEAKER_02"
            )
        ]
        
        transcript = Transcript(
            segments=segments,
            audio_path="/path/to/audio.mp3",
            language="en"
        )
        
        assert transcript.total_duration() == 10.0
    
    def test_transcript_speaker_count(self):
        """Проверка метода speaker_count объекта Transcript"""
        segments = [
            TranscriptSegment(
                text="Hello, this is segment 1",
                start=0.0,
                end=5.0,
                speaker="SPEAKER_01"
            ),
            TranscriptSegment(
                text="This is segment 2",
                start=5.0,
                end=10.0,
                speaker="SPEAKER_02"
            ),
            TranscriptSegment(
                text="This is segment 3",
                start=10.0,
                end=15.0,
                speaker="SPEAKER_01"
            )
        ]
        
        transcript = Transcript(
            segments=segments,
            audio_path="/path/to/audio.mp3",
            language="en"
        )
        
        assert transcript.speaker_count() == 2
    
    def test_transcript_to_dict(self):
        """Проверка метода to_dict объекта Transcript"""
        segments = [
            TranscriptSegment(
                text="Hello, this is segment 1",
                start=0.0,
                end=5.0,
                speaker="SPEAKER_01"
            ),
            TranscriptSegment(
                text="This is segment 2",
                start=5.0,
                end=10.0,
                speaker="SPEAKER_02"
            )
        ]
        
        created_at = datetime.now()
        
        transcript = Transcript(
            segments=segments,
            audio_path="/path/to/audio.mp3",
            language="en",
            created_at=created_at,
            metadata={"sample_rate": 16000}
        )
        
        result = transcript.to_dict()
        
        assert len(result["segments"]) == 2
        assert result["audio_path"] == "/path/to/audio.mp3"
        assert result["language"] == "en"
        assert result["created_at"] == created_at.isoformat()
        assert result["metadata"] == {"sample_rate": 16000}

class TestProtocolModel:
    """Тесты для модели Protocol"""
    
    def test_protocol_init(self):
        """Проверка создания объекта Protocol"""
        metadata = {
            "title": "Test Meeting",
            "date": "2025-01-01",
            "location": "Online"
        }
        
        participants = [
            Participant(name="John Doe", role="Manager"),
            Participant(name="Jane Smith", role="Developer")
        ]
        
        agenda_items = [
            AgendaItem(
                topic="Project Status",
                discussion_summary="Discussed current project status",
                decisions_made=[Decision(description="Continue with current plan")],
                action_items_assigned=[ActionItem(who="John", what="Update roadmap")]
            )
        ]
        
        decisions = [Decision(description="Approve budget")]
        
        action_items = [ActionItem(who="Jane", what="Prepare report")]
        
        protocol = Protocol(
            metadata=metadata,
            participants=participants,
            agenda_items=agenda_items,
            summary="This is a test meeting",
            decisions=decisions,
            action_items=action_items
        )
        
        assert protocol.metadata == metadata
        assert len(protocol.participants) == 2
        assert len(protocol.agenda_items) == 1
        assert protocol.summary == "This is a test meeting"
        assert len(protocol.decisions) == 1
        assert len(protocol.action_items) == 1
    
    def test_protocol_to_dict(self):
        """Проверка метода to_dict объекта Protocol"""
        metadata = {
            "title": "Test Meeting",
            "date": "2025-01-01",
            "location": "Online"
        }
        
        participants = [
            Participant(name="John Doe", role="Manager"),
            Participant(name="Jane Smith", role="Developer")
        ]
        
        agenda_items = [
            AgendaItem(
                topic="Project Status",
                discussion_summary="Discussed current project status",
                decisions_made=[Decision(description="Continue with current plan")],
                action_items_assigned=[ActionItem(who="John", what="Update roadmap")]
            )
        ]
        
        decisions = [Decision(description="Approve budget")]
        
        action_items = [ActionItem(who="Jane", what="Prepare report")]
        
        protocol = Protocol(
            metadata=metadata,
            participants=participants,
            agenda_items=agenda_items,
            summary="This is a test meeting",
            decisions=decisions,
            action_items=action_items
        )
        
        result = protocol.to_dict()
        
        assert result["metadata"] == metadata
        assert len(result["participants"]) == 2
        assert len(result["agenda_items"]) == 1
        assert result["summary"] == "This is a test meeting"
        assert len(result["decisions"]) == 1
        assert len(result["action_items"]) == 1
    
    def test_protocol_to_egl_json(self):
        """Проверка метода to_egl_json объекта Protocol"""
        metadata = {
            "title": "Test Meeting",
            "date": "2025-01-01",
            "location": "Online",
            "organizer": "John Doe",
            "author": "AI Assistant"
        }
        
        participants = [
            Participant(name="John Doe", role="Manager", present=True),
            Participant(name="Jane Smith", role="Developer", present=True),
            Participant(name="Bob Brown", role="Designer", present=False)
        ]
        
        agenda_items = [
            AgendaItem(
                id="T001",
                topic="Project Status",
                discussion_summary="Discussed current project status",
                decisions_made=[Decision(description="Continue with current plan")],
                action_items_assigned=[ActionItem(who="John", what="Update roadmap", due="2025-01-15")]
            )
        ]
        
        decisions = [Decision(description="Approve budget")]
        
        action_items = [ActionItem(who="Jane", what="Prepare report")]
        
        protocol = Protocol(
            metadata=metadata,
            participants=participants,
            agenda_items=agenda_items,
            summary="This is a test meeting",
            decisions=decisions,
            action_items=action_items
        )
        
        result = protocol.to_egl_json()
        
        assert result["meta"]["titel"] == "Test Meeting"
        assert result["meta"]["datum"] == "2025-01-01"
        assert result["meta"]["ort"] == "Online"
        assert result["meta"]["sitzungsleiter"] == "John Doe"
        assert result["meta"]["verfasser"] == "AI Assistant"
        
        assert len(result["teilnehmer"]["anwesend"]) == 2
        assert "John Doe" in result["teilnehmer"]["anwesend"]
        assert "Jane Smith" in result["teilnehmer"]["anwesend"]
        
        assert len(result["teilnehmer"]["entschuldigt"]) == 1
        assert "Bob Brown" in result["teilnehmer"]["entschuldigt"]
        
        assert len(result["traktanden"]) == 1
        assert result["traktanden"][0]["id"] == "T001"
        assert result["traktanden"][0]["titel"] == "Project Status"
        assert result["traktanden"][0]["diskussion"] == "Discussed current project status"
        assert result["traktanden"][0]["entscheidungen"] == ["Continue with current plan"]
        assert len(result["traktanden"][0]["pendenzen"]) == 1
        assert result["traktanden"][0]["pendenzen"][0]["wer"] == "John"
        assert result["traktanden"][0]["pendenzen"][0]["was"] == "Update roadmap"
        assert result["traktanden"][0]["pendenzen"][0]["frist"] == "2025-01-15"

if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
