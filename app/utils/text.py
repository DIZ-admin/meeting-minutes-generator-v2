"""
Утилиты для работы с текстом
"""
import json
from typing import List, Dict, Any, Optional, Union

try:
    import tiktoken
except ImportError:
    import subprocess
    subprocess.check_call(["pip", "install", "tiktoken"])
    import tiktoken

from ..utils.logging import get_default_logger
from ..config.config import config

logger = get_default_logger(__name__)

def split_text_into_chunks(
    text: str,
    chunk_tokens: int = None,
    overlap_tokens: int = None,
    encoding_name: str = "cl100k_base"
) -> List[str]:
    """
    Разбивает текст на чанки с заданным количеством токенов и перекрытием
    
    Args:
        text: Текст для разбиения
        chunk_tokens: Максимальное количество токенов в чанке
                     (если None, берется из конфигурации)
        overlap_tokens: Количество токенов перекрытия между чанками
                       (если None, берется из конфигурации)
        encoding_name: Имя кодировки для tiktoken
        
    Returns:
        Список чанков текста
    """
    if chunk_tokens is None:
        chunk_tokens = config.chunk_tokens
    
    if overlap_tokens is None:
        overlap_tokens = config.overlap_tokens
    
    # Убеждаемся, что перекрытие не больше размера чанка
    if overlap_tokens >= chunk_tokens:
        logger.warning(
            f"Overlap tokens ({overlap_tokens}) is greater than or equal to chunk tokens ({chunk_tokens}). "
            f"Setting overlap to 0."
        )
        overlap_tokens = 0
    
    # Если текст пустой, возвращаем пустой список
    if not text:
        return []
    
    try:
        # Получаем кодировку
        encoding = tiktoken.get_encoding(encoding_name)
        
        # Кодируем текст в токены
        all_tokens = encoding.encode(text)
        
        # Если текст меньше размера чанка, возвращаем его целиком
        if len(all_tokens) <= chunk_tokens:
            return [text]
        
        # Разбиваем токены на чанки
        chunks = []
        start_token_idx = 0
        
        while start_token_idx < len(all_tokens):
            # Находим конец текущего чанка
            end_token_idx = min(start_token_idx + chunk_tokens, len(all_tokens))
            
            # Получаем токены для текущего чанка
            current_chunk_tokens = all_tokens[start_token_idx:end_token_idx]
            
            # Декодируем токены обратно в текст
            chunk_text = encoding.decode(current_chunk_tokens)
            chunks.append(chunk_text)
            
            # Если достигли конца текста, выходим из цикла
            if end_token_idx >= len(all_tokens):
                break
            
            # Определяем начало следующего чанка с учетом перекрытия
            start_token_idx += chunk_tokens - overlap_tokens
            
            # Убеждаемся, что мы не застряли в бесконечном цикле
            if start_token_idx >= end_token_idx:
                start_token_idx = end_token_idx
        
        logger.debug(f"Split text into {len(chunks)} chunks")
        return chunks
        
    except Exception as e:
        logger.error(f"Error splitting text into chunks: {e}", exc_info=True)
        # Если произошла ошибка с tiktoken, используем простое разбиение на символы
        # Это запасной вариант, который работает не так точно
        logger.warning("Falling back to simple character split")
        
        chunk_size_chars = chunk_tokens * 4  # Грубое приближение: 1 токен ~ 4 символа
        overlap_chars = overlap_tokens * 4
        
        # Разбиваем текст на чанки по символам
        result = []
        start_idx = 0
        
        while start_idx < len(text):
            end_idx = min(start_idx + chunk_size_chars, len(text))
            result.append(text[start_idx:end_idx])
            
            if end_idx >= len(text):
                break
                
            start_idx += chunk_size_chars - overlap_chars
            
            # Защита от бесконечного цикла
            if start_idx >= end_idx:
                start_idx = end_idx
        
        logger.debug(f"Split text into {len(result)} chunks using fallback method")
        return result

def split_transcript_segments(
    segments: List[Dict[str, Any]],
    chunk_tokens: int = None,
    overlap_segments: int = 3,
    encoding_name: str = "cl100k_base"
) -> List[List[Dict[str, Any]]]:
    """
    Разбивает сегменты транскрипции на чанки с заданным количеством токенов и
    перекрытием сегментов
    
    Args:
        segments: Список сегментов транскрипции
        chunk_tokens: Максимальное количество токенов в чанке
                    (если None, берется из конфигурации)
        overlap_segments: Количество сегментов перекрытия между чанками
        encoding_name: Имя кодировки для tiktoken
        
    Returns:
        Список чанков сегментов
    """
    if chunk_tokens is None:
        chunk_tokens = config.chunk_tokens
    
    # Если сегментов нет, возвращаем пустой список
    if not segments:
        return []
    
    try:
        # Получаем кодировку
        encoding = tiktoken.get_encoding(encoding_name)
        
        # Разбиваем сегменты на чанки
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for segment in segments:
            # Получаем текст сегмента
            segment_text = segment.get("text", "")
            
            # Подсчитываем токены в сегменте
            segment_tokens = len(encoding.encode(segment_text))
            
            # Если текущий чанк пуст или добавление сегмента не превысит лимит,
            # добавляем сегмент в текущий чанк
            if not current_chunk or current_tokens + segment_tokens <= chunk_tokens:
                current_chunk.append(segment)
                current_tokens += segment_tokens
            else:
                # Иначе сохраняем текущий чанк и начинаем новый
                chunks.append(current_chunk)
                
                # Если у нас есть перекрытие, копируем последние N сегментов
                # из предыдущего чанка в новый
                if overlap_segments > 0 and len(current_chunk) > overlap_segments:
                    current_chunk = current_chunk[-overlap_segments:]
                    # Пересчитываем токены для нового чанка с перекрытием
                    current_tokens = sum(
                        len(encoding.encode(seg.get("text", "")))
                        for seg in current_chunk
                    )
                else:
                    current_chunk = []
                    current_tokens = 0
                
                # Добавляем текущий сегмент в новый чанк
                current_chunk.append(segment)
                current_tokens += segment_tokens
        
        # Добавляем последний чанк, если он не пустой
        if current_chunk:
            chunks.append(current_chunk)
        
        logger.debug(f"Split {len(segments)} segments into {len(chunks)} chunks")
        return chunks
        
    except Exception as e:
        logger.error(f"Error splitting segments into chunks: {e}", exc_info=True)
        # Если произошла ошибка, используем простое разбиение по количеству сегментов
        logger.warning("Falling back to simple segment count split")
        
        # Определяем примерное количество сегментов в чанке
        # Предполагаем, что один сегмент в среднем содержит 50 токенов
        segments_per_chunk = max(1, chunk_tokens // 50)
        
        # Разбиваем сегменты на чанки
        result = []
        for i in range(0, len(segments), segments_per_chunk - overlap_segments):
            end_idx = min(i + segments_per_chunk, len(segments))
            result.append(segments[i:end_idx])
            
            if end_idx >= len(segments):
                break
        
        logger.debug(f"Split {len(segments)} segments into {len(result)} chunks using fallback method")
        return result

def merge_text_with_headers(texts: List[str], header_template: str = "Часть {index}:") -> str:
    """
    Объединяет список текстов, добавляя к каждому заголовок
    
    Args:
        texts: Список текстов для объединения
        header_template: Шаблон для заголовка, может содержать {index} для номера части
        
    Returns:
        Объединенный текст с заголовками
    """
    result = []
    
    for i, text in enumerate(texts):
        # Формируем заголовок
        header = header_template.format(index=i+1)
        
        # Добавляем заголовок и текст
        result.append(f"{header}\n\n{text.strip()}")
    
    # Объединяем все части с двойным переносом строки
    return "\n\n".join(result)
