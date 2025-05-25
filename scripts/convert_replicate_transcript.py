#!/usr/bin/env python
"""
Скрипт для преобразования транскрипта из формата Replicate в формат, 
который ожидает система генерации протоколов.
"""
import json
import sys
import os
from pathlib import Path

def convert_replicate_transcript(input_file, output_file=None):
    """
    Преобразует транскрипт из формата Replicate в формат для системы протоколов.
    
    Args:
        input_file: Путь к входному JSON-файлу
        output_file: Путь к выходному JSON-файлу (если None, создается автоматически)
    
    Returns:
        Путь к выходному файлу
    """
    # Загружаем входной файл
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Проверяем, что это файл от Replicate
    if not isinstance(data, dict) or 'output' not in data or 'segments' not in data['output']:
        raise ValueError("Входной файл не соответствует формату Replicate")
    
    # Извлекаем сегменты
    segments = data['output']['segments']
    
    # Создаем новый формат
    converted_segments = []
    for segment in segments:
        if 'text' not in segment:
            continue
            
        # Определяем спикера из слов или используем ID сегмента
        speaker = None
        if 'words' in segment and segment['words']:
            # Берем спикера из первого слова
            speaker = segment['words'][0].get('speaker', f"SPEAKER_{len(converted_segments) % 10}")
        else:
            # Если нет слов, используем speaker из сегмента или создаем новый
            speaker = segment.get('speaker', f"SPEAKER_{len(converted_segments) % 10}")
        
        # Создаем сегмент в новом формате
        converted_segment = {
            "speaker": speaker,
            "text": segment['text'],
            "start": float(segment['start']),
            "end": float(segment['end'])
        }
        
        converted_segments.append(converted_segment)
    
    # Создаем выходной файл
    if output_file is None:
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_converted{input_path.suffix}"
    
    # Сохраняем результат
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(converted_segments, f, ensure_ascii=False, indent=2)
    
    return output_file

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python convert_replicate_transcript.py <input_file> [output_file]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        result_file = convert_replicate_transcript(input_file, output_file)
        print(f"Транскрипт успешно преобразован и сохранен в: {result_file}")
    except Exception as e:
        print(f"Ошибка при преобразовании транскрипта: {e}")
        sys.exit(1)
