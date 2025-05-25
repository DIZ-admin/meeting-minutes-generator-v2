"""
Утилиты для преобразования различных форматов транскриптов в единый формат.
"""
import json
import re
import logging
from typing import Dict, List, Any, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)

def convert_plain_text_to_transcript(text: str) -> List[Dict[str, Any]]:
    """
    Преобразует простой текст в формат транскрипта.
    
    Пытается определить говорящих по шаблонам в тексте, например:
    - "Иван: Привет всем"
    - "[Иван] Привет всем"
    - "Иван (10:30): Привет всем"
    
    Если говорящие не определены, весь текст будет присвоен одному говорящему.
    
    Args:
        text: Простой текст транскрипта
        
    Returns:
        Список сегментов транскрипта в формате:
        [
            {
                "speaker": "speaker_1",
                "text": "Текст высказывания",
                "start": 0.0,
                "end": 5.0
            },
            ...
        ]
    """
    segments = []
    
    # Разбиваем текст на строки
    lines = text.strip().split('\n')
    
    # Регулярные выражения для определения говорящих
    speaker_patterns = [
        r'^([^:]+):\s*(.*)',  # Иван: Привет всем
        r'^\[([^\]]+)\]\s*(.*)',  # [Иван] Привет всем
        r'^([^(]+)\s*\(\d+:\d+\):\s*(.*)',  # Иван (10:30): Привет всем
    ]
    
    current_time = 0.0
    speaker_map = {}  # Для отслеживания уникальных говорящих
    speaker_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Пытаемся определить говорящего
        speaker = None
        text = line
        
        for pattern in speaker_patterns:
            match = re.match(pattern, line)
            if match:
                speaker_name = match.group(1).strip()
                text = match.group(2).strip()
                
                # Создаем уникальный идентификатор говорящего
                if speaker_name not in speaker_map:
                    speaker_count += 1
                    speaker_map[speaker_name] = f"speaker_{speaker_count}"
                
                speaker = speaker_map[speaker_name]
                break
        
        # Если говорящий не определен, используем speaker_0
        if not speaker:
            speaker = "speaker_0"
        
        # Оцениваем длительность сегмента (примерно 1 секунда на 5 слов)
        words = len(text.split())
        duration = max(1.0, words / 5)
        
        # Создаем сегмент
        segment = {
            "speaker": speaker,
            "text": text,
            "start": current_time,
            "end": current_time + duration
        }
        
        segments.append(segment)
        current_time += duration
    
    return segments

def convert_file_to_transcript_format(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Преобразует файл в формат транскрипта.
    
    Поддерживаемые форматы:
    - JSON (в различных форматах)
    - TXT (простой текст)
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        Список сегментов транскрипта
        
    Raises:
        ValueError: Если формат файла не поддерживается
        FileNotFoundError: Если файл не найден
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")
    
    # Определяем формат файла по расширению
    file_ext = file_path.suffix.lower()
    
    if file_ext == '.json':
        # Загружаем JSON-файл
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                
                # Если данные уже в правильном формате, возвращаем их
                if isinstance(data, list) and all(isinstance(item, dict) and 'text' in item for item in data):
                    # Проверяем наличие обязательных полей и добавляем их при необходимости
                    for item in data:
                        if 'speaker' not in item:
                            item['speaker'] = 'speaker_0'
                        if 'start' not in item:
                            item['start'] = 0.0
                        if 'end' not in item:
                            item['end'] = item.get('start', 0.0) + 5.0
                    
                    return data
                
                # Если это объект с полем segments
                if isinstance(data, dict) and 'segments' in data and isinstance(data['segments'], list):
                    return data['segments']
                
                # Replicate API формат: объект с полем output содержащим segments
                if isinstance(data, dict) and 'output' in data and isinstance(data['output'], dict):
                    if 'segments' in data['output'] and isinstance(data['output']['segments'], list):
                        return data['output']['segments']
                
                # Если это объект с полем transcript или transcription
                if isinstance(data, dict) and ('transcript' in data or 'transcription' in data):
                    text = data.get('transcript', data.get('transcription', ''))
                    return convert_plain_text_to_transcript(text)
                
                # В противном случае, пробуем преобразовать JSON в строку и обработать как текст
                return convert_plain_text_to_transcript(json.dumps(data))
                
            except json.JSONDecodeError:
                # Если JSON некорректный, пробуем обработать как текст
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                return convert_plain_text_to_transcript(text)
    
    elif file_ext in ['.txt', '.text', '.md', '.markdown']:
        # Обрабатываем текстовый файл
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        return convert_plain_text_to_transcript(text)
    
    else:
        raise ValueError(f"Неподдерживаемый формат файла: {file_ext}")

def save_transcript_format(segments: List[Dict[str, Any]], output_path: Union[str, Path]) -> None:
    """
    Сохраняет транскрипт в формате JSON.
    
    Args:
        segments: Список сегментов транскрипта
        output_path: Путь для сохранения файла
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Транскрипт сохранен в файл: {output_path}")


def validate_transcript_format(data: Union[Dict, List, str]) -> bool:
    """
    Проверяет, является ли формат данных поддерживаемым форматом транскрипта.
    
    Args:
        data: Данные для проверки
        
    Returns:
        True если формат поддерживается, False в противном случае
    """
    if isinstance(data, list):
        # Список сегментов
        return all(isinstance(item, dict) and 'text' in item for item in data)
    
    elif isinstance(data, dict):
        # Объект с полем segments
        if 'segments' in data and isinstance(data['segments'], list):
            return True
            
        # Replicate API формат
        if 'output' in data and isinstance(data['output'], dict):
            if 'segments' in data['output'] and isinstance(data['output']['segments'], list):
                return True
                
        # AWS Transcribe формат
        if 'results' in data:
            return True
            
        # Простой текстовый формат
        if 'transcript' in data or 'transcription' in data:
            return True
    
    elif isinstance(data, str) and data.strip():
        # Простой текст
        return True
    
    return False


def get_supported_formats_info() -> Dict[str, str]:
    """
    Возвращает информацию о поддерживаемых форматах транскриптов.
    
    Returns:
        Словарь с описанием поддерживаемых форматов
    """
    return {
        "list_segments": "Список сегментов: [{'text': '...', 'speaker': '...', 'start': 0.0, 'end': 1.0}]",
        "object_segments": "Объект с segments: {'segments': [...], 'language': 'de'}",
        "replicate_api": "Replicate API: {'output': {'segments': [...], 'language': 'de'}}",
        "aws_transcribe": "AWS Transcribe: {'results': {'items': [...]}}",
        "simple_text": "Простой текст: {'transcript': 'текст...'} или строка",
        "plain_text": "Обычная текстовая строка"
    }
