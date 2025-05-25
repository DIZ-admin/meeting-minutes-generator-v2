#!/usr/bin/env python
"""
Улучшенный скрипт для обработки транскрипта совещания.
Преобразует транскрипт из формата Replicate в формат для системы протоколов,
заменяет идентификаторы спикеров на имена участников и оптимизирует структуру
для лучшей обработки в MAP-фазе.
"""
import json
import sys
import os
import argparse
import re
from pathlib import Path
import logging
from collections import defaultdict
from datetime import datetime

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
        participants_info = []
        
        for participant in data['participants']:
            if participant.get('status') == 'Anwesend' and participant.get('speaker'):
                speaker_mapping[participant['speaker']] = participant['name']
            
            # Собираем информацию об участниках для метаданных
            participants_info.append({
                "name": participant.get('name', ''),
                "role": participant.get('role', ''),
                "status": participant.get('status', '')
            })
        
        return speaker_mapping, participants_info
    
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла участников: {e}")
        return {}, []

def merge_consecutive_segments(segments, max_gap=1.0):
    """
    Объединяет последовательные сегменты от одного спикера.
    
    Args:
        segments: Список сегментов
        max_gap: Максимальный промежуток между сегментами в секундах
        
    Returns:
        Список объединенных сегментов
    """
    if not segments:
        return []
    
    merged_segments = []
    current_segment = segments[0].copy()
    
    for segment in segments[1:]:
        # Если спикер тот же и промежуток небольшой, объединяем сегменты
        if (segment['speaker'] == current_segment['speaker'] and 
            segment['start'] - current_segment['end'] <= max_gap):
            current_segment['text'] += " " + segment['text']
            current_segment['end'] = segment['end']
        else:
            # Иначе сохраняем текущий сегмент и начинаем новый
            merged_segments.append(current_segment)
            current_segment = segment.copy()
    
    # Добавляем последний сегмент
    merged_segments.append(current_segment)
    
    return merged_segments

def filter_segments(segments, min_length=3):
    """
    Фильтрует сегменты по длине и содержанию.
    
    Args:
        segments: Список сегментов
        min_length: Минимальная длина текста в словах
        
    Returns:
        Отфильтрованный список сегментов
    """
    filtered_segments = []
    
    for segment in segments:
        # Пропускаем слишком короткие сегменты
        words = segment['text'].split()
        if len(words) < min_length:
            continue
        
        # Пропускаем сегменты, содержащие только междометия или незначимые фразы
        skip_patterns = [
            r'^(Mhm|Hmm|Aha|Okay|OK|Ja|Nein|Gut)\.?$',
            r'^(Ja|Nein|Gut|Okay|OK),?\s+(okay|gut|ja|nein)\.?$',
            r'^(Danke|Bitte|Alles klar)\.?$'
        ]
        
        skip = False
        for pattern in skip_patterns:
            if re.match(pattern, segment['text'], re.IGNORECASE):
                skip = True
                break
        
        if not skip:
            filtered_segments.append(segment)
    
    return filtered_segments

def group_segments_by_topic(segments, max_segment_count=15, max_time_gap=30.0):
    """
    Группирует сегменты по предполагаемым темам на основе временных промежутков.
    
    Args:
        segments: Список сегментов
        max_segment_count: Максимальное количество сегментов в группе
        max_time_gap: Максимальный промежуток между сегментами в секундах для определения новой темы
        
    Returns:
        Список групп сегментов
    """
    if not segments:
        return []
    
    groups = []
    current_group = [segments[0]]
    
    for segment in segments[1:]:
        # Если группа слишком большая или есть большой временной промежуток, начинаем новую группу
        if (len(current_group) >= max_segment_count or 
            segment['start'] - current_group[-1]['end'] > max_time_gap):
            groups.append(current_group)
            current_group = [segment]
        else:
            current_group.append(segment)
    
    # Добавляем последнюю группу
    if current_group:
        groups.append(current_group)
    
    return groups

def process_transcript(input_file, participants_file=None, output_file=None, meeting_info=None):
    """
    Обрабатывает транскрипт для оптимальной работы с системой генерации протоколов.
    
    Args:
        input_file: Путь к входному JSON-файлу транскрипта
        participants_file: Путь к файлу с информацией об участниках
        output_file: Путь к выходному JSON-файлу (если None, создается автоматически)
        meeting_info: Дополнительная информация о совещании
        
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
    participants_info = []
    if participants_file:
        speaker_mapping, participants_info = load_participants(participants_file)
        logger.info(f"Загружена информация о {len(speaker_mapping)} участниках")
    
    # Извлекаем сегменты
    segments = data['output']['segments']
    
    # Создаем новый формат сегментов с именами участников
    processed_segments = []
    for segment in segments:
        if 'text' not in segment:
            continue
            
        # Определяем спикера из слов или используем ID сегмента
        speaker_id = None
        if 'words' in segment and segment['words']:
            # Берем спикера из первого слова
            speaker_id = segment['words'][0].get('speaker', f"SPEAKER_{len(processed_segments) % 10}")
        else:
            # Если нет слов, используем speaker из сегмента или создаем новый
            speaker_id = segment.get('speaker', f"SPEAKER_{len(processed_segments) % 10}")
        
        # Заменяем ID спикера на имя участника, если есть маппинг
        speaker_name = speaker_mapping.get(speaker_id, speaker_id)
        
        # Создаем сегмент в новом формате
        processed_segment = {
            "speaker": speaker_name,
            "speaker_id": speaker_id,  # Сохраняем оригинальный ID для отладки
            "text": segment['text'],
            "start": float(segment['start']),
            "end": float(segment['end'])
        }
        
        processed_segments.append(processed_segment)
    
    # Объединяем последовательные сегменты от одного спикера
    merged_segments = merge_consecutive_segments(processed_segments)
    logger.info(f"Объединено {len(processed_segments)} сегментов в {len(merged_segments)} сегментов")
    
    # Фильтруем сегменты
    filtered_segments = filter_segments(merged_segments)
    logger.info(f"Отфильтровано {len(merged_segments) - len(filtered_segments)} малоинформативных сегментов")
    
    # Группируем сегменты по темам
    grouped_segments = group_segments_by_topic(filtered_segments)
    logger.info(f"Сегменты сгруппированы в {len(grouped_segments)} тематических групп")
    
    # Создаем метаданные для транскрипта
    if meeting_info is None:
        meeting_info = {}
    
    # Добавляем информацию о дате, если не указана
    if 'date' not in meeting_info:
        meeting_info['date'] = datetime.now().strftime("%Y-%m-%d")
    
    # Добавляем информацию о участниках
    if participants_info and 'participants' not in meeting_info:
        meeting_info['participants'] = participants_info
    
    # Создаем выходные данные
    output_data = {
        "transcript_info": {
            "source": "Replicate ASR",
            "processed_with_participants": bool(speaker_mapping),
            "language": data['output'].get('language', 'de'),
            "total_segments": len(filtered_segments),
            "total_groups": len(grouped_segments)
        },
        "meeting_info": meeting_info,
        "segment_groups": grouped_segments
    }
    
    # Создаем выходной файл
    if output_file is None:
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_enhanced{input_path.suffix}"
    
    # Сохраняем результат
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    # Создаем также файл с сегментами в формате, который ожидает система
    segments_file = str(output_file).replace('.json', '_segments.json')
    with open(segments_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_segments, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Сохранен файл с сегментами: {segments_file}")
    
    return output_file

def main():
    """Основная функция скрипта"""
    parser = argparse.ArgumentParser(description='Улучшенная обработка транскрипта совещания')
    parser.add_argument('input_file', help='Путь к входному JSON-файлу транскрипта')
    parser.add_argument('-p', '--participants', help='Путь к файлу с информацией об участниках')
    parser.add_argument('-o', '--output', help='Путь к выходному JSON-файлу')
    parser.add_argument('-t', '--title', help='Название совещания')
    parser.add_argument('-d', '--date', help='Дата совещания (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    # Создаем информацию о совещании
    meeting_info = {}
    if args.title:
        meeting_info['title'] = args.title
    if args.date:
        meeting_info['date'] = args.date
    
    try:
        result_file = process_transcript(
            args.input_file, 
            args.participants, 
            args.output,
            meeting_info
        )
        logger.info(f"Транскрипт успешно обработан и сохранен в: {result_file}")
    except Exception as e:
        logger.error(f"Ошибка при обработке транскрипта: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
