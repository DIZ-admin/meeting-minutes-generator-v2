"""
Performance тесты для Meeting Protocol Generator

Используя pytest-benchmark для измерения производительности
"""
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.services.pipeline import Pipeline
from app.core.services.asr_service import ASRService
from app.adapters.asr.replicate_adapter import ReplicateASRAdapter
from app.utils.cache import get_cache

class TestPerformance:
    """Тесты производительности основных компонентов"""
    
    @pytest.fixture
    def sample_audio_file(self):
        """Создает временный аудиофайл для тестов"""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            # Создаем минимальный WAV файл
            wav_header = b'RIFF\x24\x08\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x22\x56\x00\x00\x44\xAC\x00\x00\x02\x00\x10\x00data\x00\x08\x00\x00'
            tmp.write(wav_header)
            tmp.write(b'\x00' * 2048)  # Данные аудио
            return Path(tmp.name)
    
    @pytest.fixture
    def mock_transcription_result(self):
        """Мок результат транскрипции"""
        return [
            {
                'start': 0.0,
                'end': 3.0,
                'text': 'Hello, this is a test transcription.',
                'speaker_id': 'SPEAKER_00',
                'speaker_confidence': 0.95
            },
            {
                'start': 3.0,
                'end': 6.0,
                'text': 'This is the second segment of speech.',
                'speaker_id': 'SPEAKER_01',
                'speaker_confidence': 0.88
            }
        ]
    
    @pytest.mark.skip("Performance tests require pytest-benchmark")
    def test_asr_service_performance(self, sample_audio_file, mock_transcription_result):
        """Тест производительности ASR сервиса"""
        
        # Создаем мок адаптер для изоляции от внешних API
        with patch.object(ReplicateASRAdapter, 'transcribe', return_value=mock_transcription_result):
            asr_service = ASRService()
            
            # Простой тест без benchmark для совместимости
            result = asr_service.transcribe(sample_audio_file, language="en")
            
            # Проверяем что результат валидный
            assert len(result) == 2
            assert result[0]['text'] == 'Hello, this is a test transcription.'
