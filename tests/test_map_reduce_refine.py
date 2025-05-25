import unittest
import os
import sys
import json
import json as std_json
from unittest.mock import patch, MagicMock, call, mock_open, DEFAULT
import tempfile
import pathlib
import jsonschema
import re

# Добавляем корневую директорию в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.map_reduce_refine import (
    split_transcript, 
    map_call, 
    reduce_results, 
    refine_to_protocol,
    generate_minutes,
    OpenAIProcessor
)

class TestMapReduceRefine(unittest.TestCase):
    """Тестирование модуля map_reduce_refine"""

    def setUp(self):
        """Настройка тестового окружения"""
        self.maxDiff = None
        # Не создаем реальный процессор здесь, если он будет мокаться в большинстве тестов
        # self.processor = OpenAIProcessor(api_key="fake_key") 

        self.test_transcript_segments = [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_01", "text": "Добрый день, коллеги."},
            {"start": 5.5, "end": 8.0, "speaker": "SPEAKER_02", "text": "Давайте начнем собрание."},
            {"start": 8.5, "end": 12.0, "speaker": "SPEAKER_01", "text": "Первый вопрос - отчет за квартал."}
        ]
        
        self.test_meeting_info = {
            "filename": "test_transcript.txt",
            "title": "Исправленное тестовое собрание",
            "date": "2025-07-20",
            "location": "Онлайн",
            "organizer": "Тест Организатор",
            "author": "Тест Протоколист",
            "participants": {
                "present": [{"name": "Участник 1"}, {"name": "Участник 2"}],
                "absent": [{"name": "Участник 3"}]
            }
        }

        # This data is used to build the prompt for the LLM in refine_to_protocol
        self.test_data_for_refine = {
            "decisions": ["Genehmigter Plan A", "Neuer Ansatz B"],
            "actions": [
                # This 'actions' key with who/what/due is from reduced_data and used to build the PROMPT for LLM.
                # The prompt asks LLM to convert this to wer/was/frist.
                {"wer": "Анна (из reduced_data)", "was": "Обновить документацию по API", "frist": "2025-07-25"},
                {"wer": "Борис (из reduced_data)", "was": "Провести ревью кода", "frist": "2025-07-30"}
            ],
            "summary_text": "Это краткое содержание для refine_to_protocol.",
            "title": "Default Meeting Title from Reduced Data"
        }

        # This is the MOCKED LLM JSON response string for refine_to_protocol.
        # This structure is what `current_protocol_json` becomes in `refine_to_protocol`.
        self.sample_llm_json_output_for_refine = {
            "meta": {
                "titel": self.test_meeting_info.get('title', 'Тестовое собрание'),
                "datum": self.test_meeting_info.get('date', '2024-01-01'),
                "ort": self.test_meeting_info.get('location', 'Тестовое место'),
                "sitzungsleiter": self.test_meeting_info.get('organizer', 'Тестовый организатор'),
                "verfasser": self.test_meeting_info.get('author', 'Тестовый автор протокола'),
                "dateiname": self.test_meeting_info.get('filename', 'test_transcript.txt')
            },
            "teilnehmer": {
                "anwesend": [p['name'] for p in self.test_meeting_info.get("participants", {}).get("present", [])],
                "abwesend": [p['name'] for p in self.test_meeting_info.get("participants", {}).get("absent", [])],
                # 'protokoll' может быть специфичным для LLM, оставляем как есть или берем из test_meeting_info['author']
                "protokoll": self.test_meeting_info.get('author', 'Тестовый автор протокола') 
            },
            "traktanden": [
                {
                    "nummer": "1.0",
                    "titel": "Главный пункт повестки",
                    "diskussion": "Детальное обсуждение главного пункта.",
                    "entscheidungen": [ # Changed from beschluesse
                        "Финальное решение 1",
                        "Финальное решение 2"
                    ],
                    "pendenzen": [
                        {"wer": "Исполнитель Альфа", "was": "Ключевая задача Альфа", "frist": "2025-08-01"},
                        {"wer": "Исполнитель Бета", "was": "Ключевая задача Бета", "frist": "2025-08-15"}
                    ]
                }
            ],
            "sonstiges": "Никаких дополнительных вопросов.",
            "naechste_sitzung": {"datum": "2025-09-01", "zeit": "14:00", "ort": "Офис"}
        }

        # This is what the json_output from refine_to_protocol is asserted against.
        # It should match sample_llm_json_output_for_refine if refine_to_protocol doesn't change the JSON structure.
        self.expected_refined_json_output = std_json.loads(std_json.dumps(self.sample_llm_json_output_for_refine)) # Deep copy
        # Ensure teilnehmer in expected output matches the list of strings for simpler assertion if needed, or keep as list of dicts
        # For current markdown generation, list of dicts with 'name' is fine.

        self.temp_dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.temp_dir.name, "schema"), exist_ok=True)
        self.schema_path = os.path.join(self.temp_dir.name, "schema", "egl_protokoll.json")
        
        self.test_schema = {
            "type": "object",
            "required": ["meta", "teilnehmer", "traktanden"],
            "properties": {
                "meta": {
                    "type": "object",
                    "properties": {
                        "titel": {"type": "string"},
                        "datum": {"type": "string"},
                        "ort": {"type": "string"},
                        "sitzungsleiter": {"type": "string"},
                        "verfasser": {"type": "string"}
                    }
                },
                "teilnehmer": {
                    "type": "object",
                    "properties": {
                        "anwesend": {"type": "array", "items": {"type": "string"}},
                        "abwesend": {"type": "array", "items": {"type": "string"}} # Изменено с entschuldigt
                    }
                },
                "traktanden": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "titel": {"type": "string"},
                            "diskussion": {"type": "string"},
                            "entscheidungen": {"type": "array", "items": {"type": "string"}},
                            "pendenzen": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "wer": {"type": "string"},
                                        "was": {"type": "string"},
                                        "frist": {"type": ["string", "null"]}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        with open(self.schema_path, 'w') as f:
            std_json.dump(self.test_schema, f)
    
        self.test_meeting_info_german_keys = {
            "titel": self.test_meeting_info["title"],
            "datum": self.test_meeting_info["date"],
            "ort": self.test_meeting_info["location"],
            "sitzungsleiter": self.test_meeting_info["organizer"],
            "verfasser": self.test_meeting_info["author"],
            "participants": { # Ensure this matches structure expected by refine_to_protocol if used directly
                "present": [p for p in self.test_meeting_info["participants"]["present"]],
                "absent": [p for p in self.test_meeting_info["participants"]["absent"]]
            }
        }

    def tearDown(self):
        """Очистка тестового окружения"""
        self.temp_dir.cleanup()
    
    def test_split_transcript_list_dict_format(self):
        """Тестирование функции split_transcript с форматом списка словарей"""
        chunks = split_transcript(self.test_transcript_segments)
        
        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 0)
        self.assertIsInstance(chunks[0], str)
        
        # Проверяем, что текст из исходных сегментов присутствует в результате
        for segment in self.test_transcript_segments:
            self.assertIn(segment["text"], " ".join(chunks))
    
    def test_split_transcript_replicate_format(self):
        """Тестирование функции split_transcript с форматом Replicate API"""
        # Создаем тестовые данные в формате Replicate API (Sitzung_3.json)
        replicate_data = {
            "output": [
                {"text": "Тестовый текст 1", "speaker": "SPEAKER_01"},
                {"text": "Тестовый текст 2", "speaker": "SPEAKER_02"}
            ]
        }
        
        chunks = split_transcript(replicate_data)
        
        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 0)
        self.assertIn("Тестовый текст 1", " ".join(chunks))
        self.assertIn("Тестовый текст 2", " ".join(chunks))
    
    def test_split_transcript_alternate_format(self):
        """Тестирование функции split_transcript с альтернативным форматом Replicate API"""
        # Создаем тестовые данные в формате Sitzung_2.json
        alternate_data = {
            "output": {
                "segments": [
                    {"text": "Альтернативный текст 1", "speaker": "SPEAKER_01"},
                    {"text": "Альтернативный текст 2", "speaker": "SPEAKER_02"}
                ]
            }
        }
        
        chunks = split_transcript(alternate_data)
        
        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 0)
        self.assertIn("Альтернативный текст 1", " ".join(chunks))
        self.assertIn("Альтернативный текст 2", " ".join(chunks))
    
    @patch('scripts.map_reduce_refine.OpenAIProcessor')
    def test_map_call(self, MockOpenAIProcessor):
        """Тестирование функции map_call"""
        # Configure the mock instance that will be created by OpenAIProcessor()
        mock_processor_instance = MockOpenAIProcessor.return_value
        
        # Configure the map_segment method of this mock instance
        expected_map_result = {
            "summary": "Краткое содержание сегмента.",
            "decisions": ["Решение 1", "Решение 2"],
            "actions": [
                {"who": "Иванов", "what": "Подготовить отчет", "due": "2025-05-26"}
            ]
        }
        mock_processor_instance.map_segment.return_value = expected_map_result
        
        # Вызываем функцию. map_call will internally create an OpenAIProcessor if one is not passed.
        result = map_call("Тестовый текст для анализа")
        
        # Проверяем результат
        self.assertIsInstance(result, dict)
        self.assertEqual(result, expected_map_result)
        
        # Проверяем, что OpenAIProcessor был инстанцирован (неявно через map_call)
        MockOpenAIProcessor.assert_called_once_with() 
        
        # Проверяем, что map_segment был вызван на экземпляре с правильным сегментом
        mock_processor_instance.map_segment.assert_called_once_with(segment_text="Тестовый текст для анализа")
    
    @patch('scripts.map_reduce_refine.OpenAIProcessor')
    def test_reduce_results(self, MockOpenAIProcessor):
        """Тестирование функции reduce_results"""
        mock_processor_instance = MockOpenAIProcessor.return_value
        
        # Тестовые данные
        map_outputs = [
            {
                "summary": "Сегмент 1: обсуждение квартального отчета.",
                "decisions": ["Утвердить отчет"],
                "actions": [{"who": "Иванов", "what": "Опубликовать отчет", "due": "2025-05-30"}]
            },
            {
                "summary": "Сегмент 2: планирование следующего квартала.",
                "decisions": ["Запланировать встречу с клиентами"],
                "actions": [{"who": "Петров", "what": "Составить план встреч", "due": "2025-06-05"}]
            }
        ]
        
        # Ожидаемый результат от LLM (reduce_content)
        expected_reduced_data = {
            "decisions": ["Утвердить отчет", "Запланировать встречу с клиентами"],
            "actions": [
                {"who": "Иванов", "what": "Опубликовать отчет", "due": "2025-05-30"},
                {"who": "Петров", "what": "Составить план встреч", "due": "2025-06-05"}
            ]
        }
        mock_processor_instance.reduce_content.return_value = expected_reduced_data
        
        # Вызываем функцию
        result = reduce_results(map_outputs)
        
        # Проверяем результат
        self.assertIsInstance(result, dict)
        self.assertEqual(result, expected_reduced_data)

        # Проверяем, что OpenAIProcessor был инстанцирован
        MockOpenAIProcessor.assert_called_once_with()
        
        # Проверяем, что reduce_content был вызван
        # (Проверка аргумента combined_text может быть сложной, т.к. он формируется внутри функции.
        # Достаточно проверить, что метод был вызван.)
        mock_processor_instance.reduce_content.assert_called_once()
        # Если нужно проверить аргумент, можно использовать mock_processor_instance.reduce_content.call_args

    def test_refine_to_protocol(self):
        """Тестирование функции refine_to_protocol"""
        reduced_data = self.test_data_for_refine

        # Create a MagicMock instance for OpenAIProcessor
        mock_processor = MagicMock(spec=OpenAIProcessor)

        # DEBUG PRINTS START
        print(f"CASCADE_DEBUG_TEST: self.test_meeting_info['participants'] = {self.test_meeting_info['participants']}")
        print(f"CASCADE_DEBUG_TEST: self.sample_llm_json_output_for_refine['teilnehmer']['anwesend'] = {self.sample_llm_json_output_for_refine['teilnehmer']['anwesend']}")
        mock_input_json_str = std_json.dumps(self.sample_llm_json_output_for_refine, ensure_ascii=False, indent=2)
        print(f"CASCADE_DEBUG_TEST: Mock JSON string for json.loads: {mock_input_json_str}")
        # DEBUG PRINTS END

        # Configure the mock method on the instance
        mock_processor.refine_to_protocol_json_str.return_value = mock_input_json_str

        # Вызов тестируемой функции, передавая мок-объект процессора
        markdown_output, json_output = refine_to_protocol(reduced_data, self.test_meeting_info, processor=mock_processor, schema_path=self.schema_path)
        
        # Проверяем JSON результат
        # Make sure to compare against the structure the mock LLM call is set to return
        self.assertIsInstance(json_output, dict)
        self.assertEqual(json_output, self.sample_llm_json_output_for_refine) # Overall check
        self.assertEqual(json_output["meta"]["titel"], self.test_meeting_info["title"])
        # Compare against self.sample_llm_json_output_for_refine as it's the direct source for json_output via mock
        self.assertEqual(json_output["traktanden"][0]["entscheidungen"], self.sample_llm_json_output_for_refine["traktanden"][0]["entscheidungen"])
        self.assertEqual(json_output["traktanden"][0]["pendenzen"], self.sample_llm_json_output_for_refine["traktanden"][0]["pendenzen"])
        
        # Проверяем, что информация о совещании присутствует
        self.assertIn(self.test_meeting_info["title"], markdown_output)
        self.assertIn(self.test_meeting_info["date"], markdown_output)

        print(f"DEBUG_TEST: Generated Markdown Output:\n{markdown_output}")

        # Проверяем, что ключи из test_meeting_info (немецкие) присутствуют
        self.assertIn(self.test_meeting_info["title"], markdown_output)
        self.assertIn(self.test_meeting_info["date"], markdown_output)

        # Проверяем, что решения из self.sample_llm_json_output_for_refine (которые являются результатом мока)
        # присутствуют в сгенерированном markdown
        if self.sample_llm_json_output_for_refine.get("traktanden") and \
           len(self.sample_llm_json_output_for_refine["traktanden"]) > 0 and \
           self.sample_llm_json_output_for_refine["traktanden"][0].get("entscheidungen"):
            for decision in self.sample_llm_json_output_for_refine["traktanden"][0]["entscheidungen"]:
                self.assertIn(decision, markdown_output)

        # Проверяем, что задачи (pendenzen) из self.sample_llm_json_output_for_refine (результат мока)
        # присутствуют в сгенерированном markdown
        if self.sample_llm_json_output_for_refine.get("traktanden") and \
           len(self.sample_llm_json_output_for_refine["traktanden"]) > 0 and \
           self.sample_llm_json_output_for_refine["traktanden"][0].get("pendenzen"):
            for action in self.sample_llm_json_output_for_refine["traktanden"][0]["pendenzen"]:
                self.assertIn(action["wer"], markdown_output)
                self.assertIn(action["was"], markdown_output)
                self.assertIn(action["frist"], markdown_output)
        else:
            # If sample_llm_json_output_for_refine is defined to have pendenzen, this path indicates a problem.
            # Depending on test intent, this might be self.fail() or pass if optional.
            # For this test, we expect pendenzen from the mock LLM output.
            self.fail("Pendenzen missing in self.sample_llm_json_output_for_refine or markdown, which is unexpected for this test.")

        # Проверяем JSON выход
        self.assertIsNotNone(json_output)

    @patch('scripts.map_reduce_refine.OpenAIProcessor') # Mock the constructor
    def test_reduce_results(self, MockOpenAIProcessor):
        """Тестирование функции reduce_results"""
        mock_processor_instance = MockOpenAIProcessor.return_value
        
        # Тестовые данные
        map_outputs = [
            {
                "summary": "Сегмент 1: обсуждение квартального отчета.",
                "decisions": ["Утвердить отчет"],
                "actions": [{"who": "Иванов", "what": "Опубликовать отчет", "due": "2025-05-30"}]
            },
            {
                "summary": "Сегмент 2: планирование следующего квартала.",
                "decisions": ["Запланировать встречу с клиентами"],
                "actions": [{"who": "Петров", "what": "Составить план встреч", "due": "2025-06-05"}]
            }
        ]
        
        # Ожидаемый результат от LLM (reduce_content)
        expected_reduced_data = {
            "decisions": ["Утвердить отчет", "Запланировать встречу с клиентами"],
            "actions": [
                {"who": "Иванов", "what": "Опубликовать отчет", "due": "2025-05-30"},
                {"who": "Петров", "what": "Составить план встреч", "due": "2025-06-05"}
            ]
        }
        mock_processor_instance.reduce_content.return_value = expected_reduced_data
        
        # Вызываем функцию
        result = reduce_results(map_outputs)
        
        # Проверяем результат
        self.assertIsInstance(result, dict)
        self.assertEqual(result, expected_reduced_data)

        # Проверяем, что OpenAIProcessor был инстанцирован
        MockOpenAIProcessor.assert_called_once_with()
        
        # Проверяем, что reduce_content был вызван
        # (Проверка аргумента combined_text может быть сложной, т.к. он формируется внутри функции.
        # Достаточно проверить, что метод был вызван.)
        mock_processor_instance.reduce_content.assert_called_once()
        # Если нужно проверить аргумент, можно использовать mock_processor_instance.reduce_content.call_args

    def test_refine_to_protocol(self):
        """Тестирование функции refine_to_protocol"""
        reduced_data = self.test_data_for_refine

        # Create a MagicMock instance for OpenAIProcessor
        mock_processor = MagicMock(spec=OpenAIProcessor)

        # DEBUG PRINTS START
        print(f"CASCADE_DEBUG_TEST: self.test_meeting_info['participants'] = {self.test_meeting_info['participants']}")
        print(f"CASCADE_DEBUG_TEST: self.sample_llm_json_output_for_refine['teilnehmer']['anwesend'] = {self.sample_llm_json_output_for_refine['teilnehmer']['anwesend']}")
        mock_input_json_str = std_json.dumps(self.sample_llm_json_output_for_refine, ensure_ascii=False, indent=2)
        print(f"CASCADE_DEBUG_TEST: Mock JSON string for json.loads: {mock_input_json_str}")
        # DEBUG PRINTS END

        # Configure the mock method on the instance
        mock_processor.refine_to_protocol_json_str.return_value = mock_input_json_str

        # Вызов тестируемой функции, передавая мок-объект процессора
        markdown_output, json_output = refine_to_protocol(reduced_data, self.test_meeting_info, processor=mock_processor, schema_path=self.schema_path)
        
        # Проверяем JSON результат
        # Make sure to compare against the structure the mock LLM call is set to return
        self.assertIsInstance(json_output, dict)
        self.assertEqual(json_output, self.sample_llm_json_output_for_refine) # Overall check
        self.assertEqual(json_output["meta"]["titel"], self.test_meeting_info["title"])
        # Compare against self.sample_llm_json_output_for_refine as it's the direct source for json_output via mock
        self.assertEqual(json_output["traktanden"][0]["entscheidungen"], self.sample_llm_json_output_for_refine["traktanden"][0]["entscheidungen"])
        self.assertEqual(json_output["traktanden"][0]["pendenzen"], self.sample_llm_json_output_for_refine["traktanden"][0]["pendenzen"])
        
        # Проверяем, что информация о совещании присутствует
        self.assertIn(self.test_meeting_info["title"], markdown_output)
        self.assertIn(self.test_meeting_info["date"], markdown_output)

        print(f"DEBUG_TEST: Generated Markdown Output:\n{markdown_output}")

        # Проверяем, что ключи из test_meeting_info (немецкие) присутствуют
        self.assertIn(self.test_meeting_info["title"], markdown_output)
        self.assertIn(self.test_meeting_info["date"], markdown_output)

        # Проверяем, что решения из self.sample_llm_json_output_for_refine (которые являются результатом мока)
        # присутствуют в сгенерированном markdown
        if self.sample_llm_json_output_for_refine.get("traktanden") and \
           len(self.sample_llm_json_output_for_refine["traktanden"]) > 0 and \
           self.sample_llm_json_output_for_refine["traktanden"][0].get("entscheidungen"):
            for decision in self.sample_llm_json_output_for_refine["traktanden"][0]["entscheidungen"]:
                self.assertIn(decision, markdown_output)

        # Проверяем, что задачи (pendenzen) из self.sample_llm_json_output_for_refine (результат мока)
        # присутствуют в сгенерированном markdown
        if self.sample_llm_json_output_for_refine.get("traktanden") and \
           len(self.sample_llm_json_output_for_refine["traktanden"]) > 0 and \
           self.sample_llm_json_output_for_refine["traktanden"][0].get("pendenzen"):
            for action in self.sample_llm_json_output_for_refine["traktanden"][0]["pendenzen"]:
                self.assertIn(action["wer"], markdown_output)
                self.assertIn(action["was"], markdown_output)
                self.assertIn(action["frist"], markdown_output)
        else:
            # If sample_llm_json_output_for_refine is defined to have pendenzen, this path indicates a problem.
            # Depending on test intent, this might be self.fail() or pass if optional.
            # For this test, we expect pendenzen from the mock LLM output.
            self.fail("Pendenzen missing in self.sample_llm_json_output_for_refine or markdown, which is unexpected for this test.")

        # Проверяем JSON выход
        self.assertIsNotNone(json_output)

    @patch('scripts.map_reduce_refine.OpenAIProcessor') # Mock the constructor
    def test_generate_minutes_empty_transcript(self, MockOpenAIProcessor):
        mock_processor_instance = MockOpenAIProcessor.return_value
        # Optionally, if client attribute access is an issue deeper:
        # mock_processor_instance.client = MagicMock()

        # Call the function with empty transcript content
        markdown_output, json_output = generate_minutes(
            None, # transcript_file_content
            self.test_meeting_info
        )
        # Check that map_segment (formerly summarize_chunk) on the mock instance was not called
        mock_processor_instance.map_segment.assert_not_called()

        # Assert basic error/empty indicators in output
        self.assertIn("Protokoll für leeres Transkript", markdown_output) # Corrected assertion
        self.assertIn("Das Transkript war leer oder konnte nicht verarbeitet werden.", markdown_output) # Corrected assertion

    @patch('scripts.map_reduce_refine.OpenAIProcessor') # ИЗМЕНЕНО: Мокируем класс целиком
    @patch('scripts.map_reduce_refine.json.loads')
    @patch('jsonschema.validate') # ИЗМЕНЕНО: scripts.map_reduce_refine.validate_json_with_schema -> jsonschema.validate
    def test_refine_to_protocol_json_loads_fallback_and_schema_error(self, mock_openai_processor_class, mock_json_loads_llm_output, mock_validate_on_fallback):
        """
        Тест: refine_to_protocol падает на json.loads(LLM_output),
        затем падает на validate_json_with_schema(fallback_json).
        Должен вернуть fallback JSON с ошибками и соответствующий Markdown.
        """
        llm_raw_error_output_str = "невалидный json {[" 

        # Настраиваем мок экземпляра OpenAIProcessor и его метода refine_to_protocol_json_str
        mock_processor_instance = MagicMock()
        mock_processor_instance.refine_to_protocol_json_str.return_value = llm_raw_error_output_str
        mock_openai_processor_class.return_value = mock_processor_instance

        # Настраиваем мок для json.loads (ответ LLM)
        # Первый вызов (для LLM response) -> ошибка
        # Второй вызов (для загрузки схемы из файла) -> успешная загрузка схемы
        mock_json_loads_llm_output.side_effect = [
            json.JSONDecodeError("Mocked LLM JSON parsing error", llm_raw_error_output_str, 0),
            self.test_schema # ИЗМЕНЕНО: self.sample_json_schema -> self.test_schema
        ]

        # Настраиваем мок для validate_json_with_schema (вызывается для fallback JSON)
        # В этом тесте валидация fallback JSON должна вызывать ошибку
        mock_validate_on_fallback.side_effect = jsonschema.exceptions.ValidationError("Mocked schema validation error for fallback JSON")

        # Ожидаемое сообщение должно точно совпадать с тем, что генерирует refine_to_protocol
        expected_error_message = "Failed to parse LLM response as JSON, and fallback JSON schema validation failed with: Mocked schema validation error for fallback JSON"
        
        # Используем re.escape для большей надежности, если сообщение содержит спецсимволы regex
        with self.assertRaisesRegex(ValueError, re.escape(expected_error_message)):
            refine_to_protocol(
                self.test_data_for_refine,
                self.test_meeting_info,
                schema_path=self.schema_path # Передаем schema_path
            )

    @patch('scripts.map_reduce_refine.OpenAIProcessor') # Добавлен недостающий декоратор
    def test_map_call_empty_segment(self, MockOpenAIProcessor):
        mock_processor_instance = MockOpenAIProcessor.return_value
        
        # Configure the map_segment method of this mock instance
        expected_map_result = {
            "summary": "",
            "decisions": [],
            "actions": []
        }
        mock_processor_instance.map_segment.return_value = expected_map_result
        
        # Вызываем функцию. map_call will internally create an OpenAIProcessor if one is not passed.
        result = map_call("")
        
        # Проверяем результат
        self.assertIsInstance(result, dict)
        self.assertEqual(result, expected_map_result)
        
        # Проверяем, что OpenAIProcessor был инстанцирован (неявно через map_call)
        MockOpenAIProcessor.assert_called_once_with() 
        
        # Проверяем, что map_segment был вызван на экземпляре с правильным сегментом
        mock_processor_instance.map_segment.assert_called_once_with(segment_text="")

if __name__ == '__main__':
    unittest.main()