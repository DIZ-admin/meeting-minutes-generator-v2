#!/usr/bin/env python
"""
Скрипт для подготовки транскрипта к обработке в системе Map-Reduce.
Преобразует транскрипт в формат, оптимальный для обработки в Map-Reduce-Refine.
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

def prepare_transcript_for_mapreduce(input_file, output_file=None, max_segment_length=200):
    """
    Подготавливает транскрипт для обработки в системе Map-Reduce.
    
    Args:
        input_file: Путь к входному JSON-файлу с сегментами
        output_file: Путь к выходному JSON-файлу (если None, создается автоматически)
        max_segment_length: Максимальная длина текста сегмента в символах
        
    Returns:
        Путь к выходному файлу
    """
    # Загружаем входной файл
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Проверяем формат данных
    if not isinstance(data, list):
        raise ValueError("Входной файл должен содержать список сегментов")
    
    # Оптимизируем сегменты для Map-Reduce
    optimized_segments = []
    
    for segment in data:
        # Проверяем наличие обязательных полей
        if 'text' not in segment or 'speaker' not in segment:
            logger.warning(f"Пропускаем сегмент без обязательных полей: {segment}")
            continue
        
        # Разбиваем слишком длинные сегменты
        text = segment['text']
        if len(text) > max_segment_length:
            # Разбиваем текст на предложения
            sentences = [s.strip() + '.' for s in text.replace('.', '.<SPLIT>').split('<SPLIT>') if s.strip()]
            
            # Группируем предложения в сегменты подходящей длины
            current_text = ""
            for sentence in sentences:
                if len(current_text) + len(sentence) <= max_segment_length:
                    current_text += " " + sentence if current_text else sentence
                else:
                    # Создаем новый сегмент с текущим текстом
                    new_segment = segment.copy()
                    new_segment['text'] = current_text
                    optimized_segments.append(new_segment)
                    current_text = sentence
            
            # Добавляем последний сегмент, если есть текст
            if current_text:
                new_segment = segment.copy()
                new_segment['text'] = current_text
                optimized_segments.append(new_segment)
        else:
            # Добавляем сегмент без изменений
            optimized_segments.append(segment)
    
    # Форматируем сегменты для лучшей обработки в Map-Reduce
    formatted_segments = []
    for segment in optimized_segments:
        # Создаем форматированный сегмент
        formatted_segment = {
            "speaker": segment['speaker'],
            "text": segment['text'],
            "start": segment.get('start', 0.0),
            "end": segment.get('end', 0.0)
        }
        
        # Добавляем дополнительные поля, если они есть
        if 'speaker_id' in segment:
            formatted_segment['speaker_id'] = segment['speaker_id']
        
        formatted_segments.append(formatted_segment)
    
    # Создаем выходной файл
    if output_file is None:
        input_path = Path(input_file)
        output_file = input_path.parent / f"{input_path.stem}_mapreduce{input_path.suffix}"
    
    # Сохраняем результат
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(formatted_segments, f, ensure_ascii=False, indent=2)
    
    return output_file

def main():
    """Основная функция скрипта"""
    parser = argparse.ArgumentParser(description='Подготовка транскрипта для Map-Reduce')
    parser.add_argument('input_file', help='Путь к входному JSON-файлу с сегментами')
    parser.add_argument('-o', '--output', help='Путь к выходному JSON-файлу')
    parser.add_argument('-m', '--max-length', type=int, default=200, 
                        help='Максимальная длина текста сегмента в символах')
    
    args = parser.parse_args()
    
    try:
        result_file = prepare_transcript_for_mapreduce(
            args.input_file,
            args.output,
            args.max_length
        )
        logger.info(f"Транскрипт успешно подготовлен и сохранен в: {result_file}")
    except Exception as e:
        logger.error(f"Ошибка при подготовке транскрипта: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
