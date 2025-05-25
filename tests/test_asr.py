import unittest
import os
import sys
import json
from unittest.mock import patch, MagicMock
import tempfile
import pathlib
from replicate import exceptions as replicate_exceptions

# Добавляем корневую директорию в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем модуль transcribe
from scripts.asr import transcribe, ReplicateASRClient

class TestASR(unittest.TestCase):
    """Тестирование функции-обертки transcribe из модуля ASR"""

    def setUp(self):
        """Настройка тестового окружения"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audio_file = os.path.join(self.temp_dir.name, "test_audio.mp3")
        
        # Создаем фиктивный аудиофайл для теста
        with open(self.audio_file, "wb") as f:
            f.write(b"This is a test audio file")
    
    def tearDown(self):
        """Очистка тестового окружения"""
        self.temp_dir.cleanup()
    
    @patch('scripts.asr.ReplicateASRClient') 
    def test_transcribe_calls_client_correctly(self, MockReplicateASRClient):
        """Тестирование, что transcribe правильно инстанцирует и вызывает ReplicateASRClient"""
        # Настраиваем мок для экземпляра клиента и его метода
        mock_client_instance = MockReplicateASRClient.return_value
        expected_result = [
            {"text": "Это тестовый текст", "speaker": "SPEAKER_01", "timestamp": [0.0, 3.0]}
        ]
        mock_client_instance.transcribe_audio.return_value = expected_result
        
        audio_path_obj = pathlib.Path(self.audio_file)
        # Вызываем функцию транскрипции
        result = transcribe(audio_path_obj)
        
        # Проверяем, что ReplicateASRClient был инстанцирован
        MockReplicateASRClient.assert_called_once_with() 
        
        # Проверяем, что метод transcribe_audio был вызван с правильными аргументами
        mock_client_instance.transcribe_audio.assert_called_once_with(audio_path_obj, lang=None)
        
        # Проверяем результат
        self.assertEqual(result, expected_result)

class TestReplicateASRClient(unittest.TestCase):
    """Тестирование клиента ReplicateASRClient для транскрипции аудио"""

    def setUp(self):
        """Настройка тестового окружения"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audio_file_path = pathlib.Path(self.temp_dir.name) / "test_audio.mp3"
        
        # Создаем фиктивный аудиофайл для теста
        with open(self.audio_file_path, "wb") as f:
            f.write(b"This is a test audio file content")
        
        self.client = ReplicateASRClient()
    
    def tearDown(self):
        """Очистка тестового окружения"""
        self.temp_dir.cleanup()

    @patch('scripts.asr.replicate.run')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data=b"dummy audio data")
    def test_transcribe_audio_default_params(self, mock_open_file, mock_replicate_run):
        """Тестирование transcribe_audio с параметрами по умолчанию (язык авто, без указания кол-ва спикеров)"""
        expected_segments = [
            {"text": "Это тестовый текст", "speaker": "SPEAKER_01", "timestamp": [0.0, 3.0]},
            {"text": "Проверка работы транскрипции", "speaker": "SPEAKER_02", "timestamp": [3.5, 7.0]}
        ]
        mock_replicate_run.return_value = {"segments": expected_segments}
        
        result = self.client.transcribe_audio(self.audio_file_path)
        
        self.assertEqual(result, expected_segments)
        mock_open_file.assert_called_once_with(self.audio_file_path, "rb")
        mock_replicate_run.assert_called_once()
        args, kwargs = mock_replicate_run.call_args
        self.assertEqual(args[0], f"{self.client.model_identifier}")
        self.assertIn("file", kwargs["input"])
        self.assertEqual(kwargs["input"]["language"], "") # API ожидает пустую строку для автодетекции
        self.assertIsNone(kwargs["input"]["num_speakers"]) # По умолчанию None

    @patch('scripts.asr.replicate.run')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data=b"dummy audio data")
    def test_transcribe_audio_custom_language(self, mock_open_file, mock_replicate_run):
        """Тестирование transcribe_audio с указанным языком"""
        expected_segments = [
            {"text": "This is a test", "speaker": "SPEAKER_01", "timestamp": [0.0, 3.0]}
        ]
        mock_replicate_run.return_value = {"segments": expected_segments}
        
        result = self.client.transcribe_audio(self.audio_file_path, lang="english")
        
        self.assertEqual(result, expected_segments)
        mock_open_file.assert_called_once_with(self.audio_file_path, "rb")
        mock_replicate_run.assert_called_once()
        args, kwargs = mock_replicate_run.call_args
        self.assertEqual(kwargs["input"]["language"], "english")
        self.assertIsNone(kwargs["input"]["num_speakers"]) # Не указан, должен быть None

    @patch('scripts.asr.replicate.run')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data=b"dummy audio data")
    def test_transcribe_audio_with_num_speakers(self, mock_open_file, mock_replicate_run):
        """Тестирование transcribe_audio с указанным количеством спикеров"""
        expected_segments = [
            {"text": "Speaker one says hello", "speaker": "SPEAKER_01", "timestamp": [0.0, 3.0]}
        ]
        mock_replicate_run.return_value = {"segments": expected_segments}
        
        result = self.client.transcribe_audio(self.audio_file_path, num_speakers=2)
        
        self.assertEqual(result, expected_segments)
        mock_open_file.assert_called_once_with(self.audio_file_path, "rb")
        mock_replicate_run.assert_called_once()
        args, kwargs = mock_replicate_run.call_args
        self.assertEqual(kwargs["input"]["language"], "") # Язык по умолчанию
        self.assertEqual(kwargs["input"]["num_speakers"], 2)

    @patch('scripts.asr.replicate.run')
    def test_transcribe_audio_replicate_api_error(self, mock_replicate_run):
        """Тестирование ошибки Replicate API (replicate.exceptions.ReplicateError)"""
        original_error_message = 'API communication failed'
        mock_replicate_run.side_effect = replicate_exceptions.ReplicateError(original_error_message)
        
        # ReplicateError.__str__() добавляет детали, поэтому мы должны их ожидать.
        # Строка ошибки выглядит так: "ReplicateError Details:\ntype: API communication failed"
        # Нам нужно эскейпить перенос строки для regex.
        expected_exception_details = f"ReplicateError Details:\\ntype: {original_error_message}"
        expected_runtime_error_message = f"Failed to transcribe audio due to Replicate API error: {expected_exception_details}"
        
        with self.assertRaisesRegex(RuntimeError, expected_runtime_error_message):
            self.client.transcribe_audio(self.audio_file_path)
        
        mock_replicate_run.assert_called_once()

    @patch('builtins.open')
    def test_transcribe_audio_file_not_found(self, mock_open_file):
        """Тестирование ошибки, когда аудиофайл не найден (FileNotFoundError)"""
        mock_open_file.side_effect = FileNotFoundError('Audio file is missing')
        
        expected_error_message = f"Audio file not found: {self.audio_file_path}"
        with self.assertRaisesRegex(RuntimeError, expected_error_message):
            self.client.transcribe_audio(self.audio_file_path)
        
        # Убедимся, что была попытка открыть файл
        mock_open_file.assert_called_once_with(self.audio_file_path, "rb")

    @patch('scripts.asr.replicate.run')
    @patch('builtins.print') # Мокируем print для проверки предупреждения
    def test_transcribe_audio_unexpected_api_response(self, mock_print, mock_replicate_run):
        """Тестирование неожиданного ответа от Replicate API (None или без 'segments')"""
        unexpected_responses = [
            None,
            {"other_key": "some_value"}
        ]

        for i, response in enumerate(unexpected_responses):
            with self.subTest(f"Unexpected response scenario {i}", response=response):
                mock_replicate_run.reset_mock() # Сбрасываем мок для каждого subtest
                mock_print.reset_mock()
                
                mock_replicate_run.return_value = response
                
                result = self.client.transcribe_audio(self.audio_file_path)
                
                self.assertEqual(result, [])
                mock_replicate_run.assert_called_once()
                mock_print.assert_called_once()
                # Проверяем, что предупреждение содержит ожидаемый текст
                args, _ = mock_print.call_args
                self.assertIn("Replicate API returned an unexpected response", args[0])

    @patch('scripts.asr.replicate.run')
    def test_transcribe_audio_other_unexpected_error(self, mock_replicate_run):
        """Тестирование других неожиданных ошибок во время вызова API"""
        mock_replicate_run.side_effect = Exception('Some other runtime problem')
        
        with self.assertRaisesRegex(RuntimeError, 
                                 "Failed to transcribe audio due to an unexpected error: Some other runtime problem"):
            self.client.transcribe_audio(self.audio_file_path)
        
        mock_replicate_run.assert_called_once()

if __name__ == '__main__':
    unittest.main()