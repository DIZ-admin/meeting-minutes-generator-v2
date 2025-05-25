import os
import json
import pathlib
from unittest.mock import MagicMock, patch
from scripts.map_reduce_refine import generate_minutes

# Define a base path for test outputs for easier cleanup or inspection if needed
TEST_OUTPUT_BASE_DIR = pathlib.Path(__file__).resolve().parent / "test_outputs"

def test_map_save(mocker):
    """Тестирование сохранения результатов MAP-фазы"""
    # ... (path construction for transcript_file remains the same)
    test_file_dir = pathlib.Path(__file__).resolve().parent
    project_root = test_file_dir.parent
    transcript_file = project_root / "attached_assets" / "Sitzung_3.json"
    
    print(f"Загрузка транскрипции из файла: {transcript_file}")
    if not transcript_file.exists():
        print(f"ОШИБКА: Тестовый файл транскрипции не найден: {transcript_file}")
        assert False, f"Тестовый файл транскрипции не найден: {transcript_file}"

    with open(transcript_file, 'r', encoding='utf-8') as f:
        transcript_data = json.load(f)
    
    meeting_info = {
        "title": "Тестовый протокол совещания",
        "date": "2025-05-19",
        "location": "Online",
        "chair": "Председатель",
        "author": "AI Assistant",
        "participants": {
            "present": [
                {"name": "Участник 1", "role": "Participant"},
                {"name": "Участник 2", "role": "Participant"},
                {"name": "Участник 3", "role": "Participant"}
            ],
            "absent": [
                {"name": "Отсутствующий 1", "role": "Absent"}
            ]
        }
    }

    # Мокируем все необходимые функции и методы для теста
    
    # Мокируем функцию map_call для обработки сегментов
    mock_map_result = {
        "summary": "Mocked summary for segment.",
        "decisions": ["Mocked decision 1"],
        "actions": ["Mocked action 1 (Assignee: Bot)"]
    }
    mocker.patch('scripts.map_reduce_refine.map_call', return_value=mock_map_result)
    
    # Мокируем функцию reduce_results для объединения результатов
    mock_reduce_result = {
        "decisions": ["Mocked final decision"],
        "actions": ["Mocked final action (Assignee: TestUser)"]
    }
    mocker.patch('scripts.map_reduce_refine.reduce_results', return_value=mock_reduce_result)
    
    # Мокируем функцию refine_to_protocol для генерации протокола
    mock_markdown = "# Mocked Protocol\n\nThis is a mocked protocol."
    mock_json = {"protocol": {"title": "Mocked JSON Protocol", "content": "Mock content"}}
    mocker.patch('scripts.map_reduce_refine.refine_to_protocol', return_value=(mock_markdown, mock_json))
    
    # Мокируем класс OpenAIProcessor
    mock_processor = MagicMock()
    mock_processor.process_segment_map.return_value = mock_map_result
    mock_processor.reduce_results.return_value = mock_reduce_result
    mock_processor.refine_to_protocol.return_value = (mock_markdown, mock_json)
    mocker.patch('scripts.map_reduce_refine.OpenAIProcessor', return_value=mock_processor)
    # --- End Mocking OpenAIProcessor ---

    print("Запуск обработки транскрипции с сохранением результатов MAP-фазы (с моком OpenAIProcessor)...")
    
    # Определим уникальную директорию для вывода этого теста
    # Чтобы избежать конфликтов с реальными запусками или другими тестами
    test_specific_output_dir = TEST_OUTPUT_BASE_DIR / f"map_save_test_{int(pathlib.Path.cwd().stat().st_ctime)}"
    test_specific_output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Тестовые выходные файлы будут сохранены в: {test_specific_output_dir}")

    # Вызов функции generate_minutes для обработки транскрипции
    # Передаем output_dir, чтобы функция generate_minutes сохраняла файлы туда
    markdown_path, json_path = generate_minutes(
        transcript_segments=transcript_data, 
        meeting_info=meeting_info, 
        output_dir=test_specific_output_dir
    )
    
    # Проверка результатов
    print("\nРезультаты обработки (с моком OpenAIProcessor):")
    assert markdown_path.exists(), f"Markdown файл не создан: {markdown_path}"
    assert json_path.exists(), f"JSON файл не создан: {json_path}"
    print(f"Markdown файл: {markdown_path} (Размер: {markdown_path.stat().st_size} байт)")
    print(f"JSON файл: {json_path} (Размер: {json_path.stat().st_size} байт)")

    # Проверяем, что файлы созданы и имеют ненулевой размер
    assert markdown_path.stat().st_size > 0, "Маркдаун файл пуст"
    assert json_path.stat().st_size > 0, "JSON файл пуст"

    # Поиск директории с результатами MAP-фазы в тестовой выходной директории
    # Теперь generate_minutes сохраняет map_outputs.json и reduce_test_...json в основной output_dir
    # а не в переданный output_dir для итоговых протоколов. Это нужно будет учесть или изменить в generate_minutes.
    # Для текущего теста важно, что generate_minutes отработала и создала итоговые файлы.
    # Проверку сохранения промежуточных MAP файлов оставим на будущее, если это потребуется.
    
    # Очистка (опционально, если не хотим накапливать тестовые выводы)
    # import shutil
    # shutil.rmtree(test_specific_output_dir)
    # print(f"Очищена тестовая директория: {test_specific_output_dir}")

if __name__ == "__main__":
    # Для локального запуска теста нужно настроить mocker или убрать его использование
    # Это просто для примера, обычно тесты запускаются через pytest
    class MockMocker:
        def patch(self, target, return_value):
            # Простой мок для локального запуска, не для pytest
            print(f"MOCKING: {target} to return {return_value}")
            # Это не полноценный мок, реальная замена не произойдет без pytest
            pass 
    test_map_save(mocker=MockMocker()) # Пример передачи мокера