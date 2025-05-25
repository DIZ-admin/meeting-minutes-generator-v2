#!/usr/bin/env python
"""
Скрипт для обработки транскрипта с учетом информации об участниках.
Преобразует транскрипт из формата Replicate в формат для системы протоколов
и заменяет идентификаторы спикеров на имена участников.
"""
import json
import sys
import os
import argparse
from pathlib import Path
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_participants(participants_file):
    """
    Загружает информацию об участниках из JSON-файла.
    
    Args:
        participants_file: Путь к файлу с информацией об участниках
        
    Returns:
        Словарь с маппингом идентификаторов спикеров на имена участников
    """
    try:
        with open(participants_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Проверяем формат данных
        if not isinstance(data, dict) or 'participants' not in data:
            raise ValueError("Неверный формат файла участников")
        
        # Создаем маппинг SPEAKER_XX -> имя участника
        speaker_mapping = {}
        for participant in data['participants']:
            if participant.get('status') == 'Anwesend' and participant.get('speaker'):
                speaker_mapping[participant['speaker']] = participant['name']
        
        return speaker_mapping
    
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла участников: {e}")
        return {}

def convert_replicate_transcript(input_file, participants_file=None, output_file=None):
    """
    Преобразует транскрипт из формата Replicate в формат для системы протоколов
    с учетом информации об участниках.
    
    Args:
        input_file: Путь к входному JSON-файлу транскрипта
        participants_file: Путь к файлу с информацией об участниках
        output_file: Путь к выходному JSON-файлу (если None, создается автоматически)
    
    Returns:
        Путь к выходному файлу
    """
    # Загружаем входной файл транскрипта
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Проверяем, что это файл от Replicate
    if not isinstance(data, dict) or 'output' not in data or 'segments' not in data['output']:
        raise ValueError("Входной файл не соответствует формату Replicate")
    
    # Загружаем информацию об участниках, если указан файл
    speaker_mapping = {}
    if participants_file:
        speaker_mapping = load_participants(participants_file)
        logger.info(f"Загружена информация о {len(speaker_mapping)} участниках")
    
    # Извлекаем сегменты
    segments = data['output']['segments']
    
    # Создаем новый формат
    converted_segments = []
    for segment in segments:
        if 'text' not in segment:
            continue
            
        # Определяем спикера из слов или используем ID сегмента
        speaker_id = None
        if 'words' in segment and segment['words']:
            # Берем спикера из первого слова
            speaker_id = segment['words'][0].get('speaker', f"SPEAKER_{len(converted_segments) % 10}")
        else:
            # Если нет слов, используем speaker из сегмента или создаем новый
            speaker_id = segment.get('speaker', f"SPEAKER_{len(converted_segments) % 10}")
        
        # Заменяем ID спикера на имя участника, если есть маппинг
        speaker_name = speaker_mapping.get(speaker_id, speaker_id)
        
        # Создаем сегмент в новом формате
        converted_segment = {
            "speaker": speaker_name,
            "speaker_id": speaker_id,  # Сохраняем оригинальный ID для отладки
            "text": segment['text'],
            "start": float(segment['start']),
            "end": float(segment['end'])
        }
        
        converted_segments.append(converted_segment)
    
    # Создаем выходной файл
    if output_file is None:
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_processed{input_path.suffix}"
    
    # Создаем метаданные для транскрипта
    output_data = {
        "transcript_info": {
            "source": "Replicate ASR",
            "processed_with_participants": bool(speaker_mapping),
            "language": data['output'].get('language', 'de'),
            "total_segments": len(converted_segments)
        },
        "segments": converted_segments
    }
    
    # Сохраняем результат
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    return output_file

def main():
    """Основная функция скрипта"""
    parser = argparse.ArgumentParser(description='Обработка транскрипта с учетом участников')
    parser.add_argument('input_file', help='Путь к входному JSON-файлу транскрипта')
    parser.add_argument('-p', '--participants', help='Путь к файлу с информацией об участниках')
    parser.add_argument('-o', '--output', help='Путь к выходному JSON-файлу')
    
    args = parser.parse_args()
    
    try:
        result_file = convert_replicate_transcript(
            args.input_file, 
            args.participants, 
            args.output
        )
        logger.info(f"Транскрипт успешно обработан и сохранен в: {result_file}")
    except Exception as e:
        logger.error(f"Ошибка при обработке транскрипта: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
