"""
Улучшенные утилиты для интеллектуального разбиения текста
"""
import re
from typing import List, Dict, Any, Optional, Union, Tuple

try:
    import tiktoken
except ImportError:
    # Установка tiktoken, если отсутствует
    import subprocess
    subprocess.check_call(["pip", "install", "tiktoken"])
    import tiktoken

from ..utils.logging import get_default_logger
from ..config.config import config

logger = get_default_logger(__name__)

def smart_split_text(
    text: str,
    chunk_tokens: int = None,
    overlap_tokens: int = None,
    encoding_name: str = "cl100k_base",
    respect_paragraphs: bool = True,
    respect_sentences: bool = True
) -> List[str]:
    """
    Интеллектуально разбивает текст на чанки с учетом смысловых границ
    
    Args:
        text: Текст для разбиения
        chunk_tokens: Максимальное количество токенов в чанке
                     (если None, берется из конфигурации)
        overlap_tokens: Количество токенов перекрытия между чанками
                       (если None, берется из конфигурации)
        encoding_name: Имя кодировки для tiktoken
        respect_paragraphs: Учитывать ли границы параграфов при разбиении
        respect_sentences: Учитывать ли границы предложений при разбиении
        
    Returns:
        Список чанков текста с учетом смысловых границ
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
        
        # Разбиваем текст на параграфы и предложения, если это требуется
        if respect_paragraphs:
            # Разбиваем на параграфы (несколько пустых строк или \n\n)
            paragraphs = re.split(r'\n\s*\n', text)
            
            # Если абзацы большие, можно разбить их на предложения
            if respect_sentences:
                segments = []
                for paragraph in paragraphs:
                    # Разбиваем абзац на предложения
                    # Учитываем различные окончания предложений (., !, ?, ...)
                    sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                    segments.extend(sentences)
            else:
                segments = paragraphs
        elif respect_sentences:
            # Разбиваем только на предложения
            segments = re.split(r'(?<=[.!?])\s+', text)
        else:
            # Если не учитываем ни параграфы, ни предложения, используем весь текст
            segments = [text]
        
        # Токенизируем каждый сегмент
        segment_tokens = [(segment, encoding.encode(segment)) for segment in segments]
        
        # Разбиваем на чанки с учетом токенов
        chunks = []
        current_chunk_text = []
        current_chunk_tokens = []
        current_token_count = 0
        
        for segment_text, segment_token_ids in segment_tokens:
            segment_token_count = len(segment_token_ids)
            
            # Если текущий сегмент один больше, чем размер чанка, разбиваем его на более мелкие части
            if segment_token_count > chunk_tokens:
                # Если есть уже накопленные сегменты, сохраняем их как чанк
                if current_chunk_text:
                    chunks.append(" ".join(current_chunk_text))
                    current_chunk_text = []
                    current_chunk_tokens = []
                    current_token_count = 0
                
                # Разбиваем большой сегмент на части по маркерам пунктуации или просто по количеству токенов
                if respect_sentences:
                    # Пытаемся разбить по запятым, точкам с запятой и т.д.
                    subsegments = re.split(r'(?<=[,;:])\s+', segment_text)
                    
                    # Если все еще слишком большие, просто разбиваем по токенам
                    if any(len(encoding.encode(ss)) > chunk_tokens for ss in subsegments):
                        # Просто разбиваем по токенам
                        for i in range(0, segment_token_count, chunk_tokens - overlap_tokens):
                            end_idx = min(i + chunk_tokens, segment_token_count)
                            subsegment_tokens = segment_token_ids[i:end_idx]
                            subsegment_text = encoding.decode(subsegment_tokens)
                            chunks.append(subsegment_text)
                    else:
                        # Используем разбиение по пунктуации
                        subsegment_chunk_text = []
                        subsegment_token_count = 0
                        
                        for subsegment in subsegments:
                            subsegment_tokens = encoding.encode(subsegment)
                            subsegment_token_len = len(subsegment_tokens)
                            
                            if subsegment_token_count + subsegment_token_len <= chunk_tokens:
                                subsegment_chunk_text.append(subsegment)
                                subsegment_token_count += subsegment_token_len
                            else:
                                # Сохраняем текущий под-чанк
                                if subsegment_chunk_text:
                                    chunks.append(" ".join(subsegment_chunk_text))
                                
                                # Начинаем новый под-чанк
                                subsegment_chunk_text = [subsegment]
                                subsegment_token_count = subsegment_token_len
                        
                        # Добавляем последний под-чанк, если он есть
                        if subsegment_chunk_text:
                            chunks.append(" ".join(subsegment_chunk_text))
                else:
                    # Просто разбиваем по токенам
                    for i in range(0, segment_token_count, chunk_tokens - overlap_tokens):
                        end_idx = min(i + chunk_tokens, segment_token_count)
                        subsegment_tokens = segment_token_ids[i:end_idx]
                        subsegment_text = encoding.decode(subsegment_tokens)
                        chunks.append(subsegment_text)
            
            # Если добавление текущего сегмента превысит размер чанка, сохраняем текущий чанк и начинаем новый
            elif current_token_count + segment_token_count > chunk_tokens:
                chunks.append(" ".join(current_chunk_text))
                
                # Начинаем новый чанк с учетом перекрытия
                if overlap_tokens > 0 and current_chunk_tokens:
                    # Определяем, сколько последних токенов нужно включить в перекрытие
                    overlap_start = max(0, len(current_chunk_tokens) - overlap_tokens)
                    overlap_tokens_ids = []
                    
                    # Собираем токены для перекрытия
                    for i in range(overlap_start, len(current_chunk_tokens)):
                        overlap_tokens_ids.extend(current_chunk_tokens[i])
                    
                    # Декодируем токены перекрытия в текст
                    overlap_text = encoding.decode(overlap_tokens_ids)
                    
                    # Разбиваем текст перекрытия на предложения или параграфы
                    if respect_sentences:
                        overlap_segments = re.split(r'(?<=[.!?])\s+', overlap_text)
                    elif respect_paragraphs:
                        overlap_segments = re.split(r'\n\s*\n', overlap_text)
                    else:
                        overlap_segments = [overlap_text]
                    
                    # Инициализируем новый чанк с текстом перекрытия
                    current_chunk_text = overlap_segments
                    current_chunk_tokens = [encoding.encode(seg) for seg in overlap_segments]
                    current_token_count = sum(len(tokens) for tokens in current_chunk_tokens)
                else:
                    current_chunk_text = []
                    current_chunk_tokens = []
                    current_token_count = 0
                
                # Добавляем текущий сегмент в новый чанк
                current_chunk_text.append(segment_text)
                current_chunk_tokens.append(segment_token_ids)
                current_token_count += segment_token_count
            else:
                # Добавляем текущий сегмент к текущему чанку
                current_chunk_text.append(segment_text)
                current_chunk_tokens.append(segment_token_ids)
                current_token_count += segment_token_count
        
        # Добавляем последний чанк, если он не пустой
        if current_chunk_text:
            chunks.append(" ".join(current_chunk_text))
        
        logger.debug(f"Split text into {len(chunks)} chunks using smart split")
        return chunks
        
    except Exception as e:
        logger.error(f"Error in smart_split_text: {e}", exc_info=True)
        # Если произошла ошибка, возвращаемся к базовому разбиению
        logger.warning("Falling back to basic text chunking")
        
        from ..utils.text import split_text_into_chunks
        return split_text_into_chunks(text, chunk_tokens, overlap_tokens, encoding_name)

def classify_transcript_segments(
    segments: List[Dict[str, Any]],
    classification_types: Optional[List[str]] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Классифицирует сегменты транскрипции по типам содержимого
    
    Args:
        segments: Список сегментов транскрипции
        classification_types: Список типов для классификации
                             (по умолчанию: ["introduction", "discussion", "decision", "action", "conclusion"])
        
    Returns:
        Словарь с классифицированными сегментами по типам
    """
    if classification_types is None:
        classification_types = ["introduction", "discussion", "decision", "action", "conclusion"]
    
    # Инициализируем словарь для классифицированных сегментов
    classified_segments = {classification_type: [] for classification_type in classification_types}
    classified_segments["other"] = []  # Для сегментов, которые не попали ни в одну категорию
    
    # Регулярные выражения для классификации
    patterns = {
        "introduction": [
            r'\b(?:welcome|good\s+(?:morning|afternoon|evening)|(?:let[''']s\s+)?start|begin|introduction|introduce|opening|hello|hi everyone)\b',
            r'\btoday\s+(?:we|I|(?:we[''']re|I[''']m)\s+going\s+to)\b',
            r'\bagenda\s+(?:for\s+today|is|includes)\b',
            r'\bmeeting\s+(?:objective|purpose|goal)\b'
        ],
        "discussion": [
            r'\b(?:discuss|discussed|discussing|discussion|talk|talked|talking|review|reviewed|reviewing|analyze|analyzed|analyzing|consider|considered|considering|examine|examined|examining)\b',
            r'\b(?:point|topic|subject|issue|concern|matter|question)\b',
            r'\b(?:what\s+about|how\s+about|regarding)\b'
        ],
        "decision": [
            r'\b(?:decide|decided|decision|agree|agreed|agreement|consensus|vote|voted|approve|approved|approval|resolve|resolved|resolution)\b',
            r'\b(?:we\s+(?:have|will|should|must|need\s+to)|it\s+was\s+(?:decided|agreed|determined))\b',
            r'\b(?:(?:will|shall|should|must|going\s+to)\s+(?:be|proceed|continue|start|stop|implement|adopt))\b'
        ],
        "action": [
            r'\b(?:action|task|todo|to\s+do|assign|assigned|responsibility|responsible|accountable|owner|take\s+care|follow\s+up)\b',
            r'\b(?:(?:will|shall|must|need\s+to)\s+(?:do|prepare|create|send|write|contact|call|email|report|update))\b',
            r'\b(?:by\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|next\s+week|next\s+month|end\s+of|deadline))\b',
            r'\b(?:due\s+(?:date|by|on))\b'
        ],
        "conclusion": [
            r'\b(?:conclude|concluded|conclusion|summary|summarize|summarized|wrap|wrap\s+up|end|finish|thank|thanks|closing)\b',
            r'\b(?:next\s+(?:meeting|session|time))\b',
            r'\b(?:any\s+(?:other|final|last)\s+(?:business|questions|comments|thoughts|remarks))\b',
            r'\b(?:see\s+you\s+(?:next|all|then|soon|later|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b'
        ]
    }
    
    # Компилируем регулярные выражения
    compiled_patterns = {
        category: [re.compile(pattern, re.IGNORECASE) for pattern in pattern_list]
        for category, pattern_list in patterns.items()
    }
    
    # Проходим по всем сегментам
    for segment in segments:
        segment_text = segment.get("text", "")
        segment_matched = False
        
        # Проверяем каждую категорию
        for category in classification_types:
            if category in compiled_patterns:
                for pattern in compiled_patterns[category]:
                    if pattern.search(segment_text):
                        classified_segments[category].append(segment)
                        segment_matched = True
                        break
            
            if segment_matched:
                break
        
        # Если сегмент не попал ни в одну категорию, добавляем его в "other"
        if not segment_matched:
            classified_segments["other"].append(segment)
    
    logger.debug(f"Classified {len(segments)} segments into categories: "
                f"{', '.join(f'{cat}: {len(segs)}' for cat, segs in classified_segments.items())}")
    
    return classified_segments

def optimize_deduplication(items: List[Dict[str, Any]], similarity_threshold: float = 0.8) -> List[Dict[str, Any]]:
    """
    Оптимизированный алгоритм дедупликации с использованием расстояния Левенштейна
    и смысловой близости текстов
    
    Args:
        items: Список элементов для дедупликации (словари с текстовыми полями)
        similarity_threshold: Порог сходства для объединения элементов (0.0 - 1.0)
        
    Returns:
        Список уникальных элементов
    """
    if not items:
        return []
    
    # Импортируем необходимые библиотеки
    try:
        from difflib import SequenceMatcher
    except ImportError:
        # Если difflib не установлен, используем простую дедупликацию
        unique_items = []
        unique_texts = set()
        
        for item in items:
            item_text = str(item)
            if item_text not in unique_texts:
                unique_texts.add(item_text)
                unique_items.append(item)
        
        return unique_items
    
    # Функция для вычисления сходства между двумя текстами
    def text_similarity(text1: str, text2: str) -> float:
        return SequenceMatcher(None, text1, text2).ratio()
    
    # Функция для объединения двух элементов
    def merge_items(item1: Dict[str, Any], item2: Dict[str, Any]) -> Dict[str, Any]:
        result = item1.copy()
        
        # Специальная логика объединения для разных типов полей
        for key, value in item2.items():
            if key not in result:
                result[key] = value
            else:
                # Объединение строк
                if isinstance(result[key], str) and isinstance(value, str):
                    # Выбираем более длинную строку
                    if len(value) > len(result[key]):
                        result[key] = value
                
                # Объединение списков
                elif isinstance(result[key], list) and isinstance(value, list):
                    for item in value:
                        if item not in result[key]:
                            result[key].append(item)
                
                # Объединение словарей
                elif isinstance(result[key], dict) and isinstance(value, dict):
                    result[key].update(value)
        
        return result
    
    # Группируем элементы по ключевым полям для оптимизации
    grouped_items = {}
    for item in items:
        # Определяем ключевое поле (например, первые несколько символов текста)
        key_field = ""
        for field_name in ["text", "description", "what", "content"]:
            if field_name in item and isinstance(item[field_name], str):
                key = item[field_name][:10].lower() if len(item[field_name]) > 10 else item[field_name].lower()
                if key:
                    key_field = key
                    break
        
        if key_field:
            if key_field not in grouped_items:
                grouped_items[key_field] = []
            grouped_items[key_field].append(item)
        else:
            # Если не удалось найти ключевое поле, просто добавляем элемент в отдельную группу
            key_field = str(hash(str(item)))
            grouped_items[key_field] = [item]
    
    # Дедупликация внутри каждой группы и между близкими группами
    unique_items = []
    processed_groups = set()
    
    for key_field, group in grouped_items.items():
        if key_field in processed_groups:
            continue
        
        processed_groups.add(key_field)
        
        # Объединяем группы с похожими ключевыми полями
        merged_group = group.copy()
        for other_key, other_group in grouped_items.items():
            if other_key != key_field and other_key not in processed_groups:
                if text_similarity(key_field, other_key) >= similarity_threshold:
                    merged_group.extend(other_group)
                    processed_groups.add(other_key)
        
        # Дедупликация внутри объединенной группы
        for i, item1 in enumerate(merged_group):
            if item1 is None:
                continue
            
            for j in range(i + 1, len(merged_group)):
                item2 = merged_group[j]
                if item2 is None:
                    continue
                
                # Вычисляем сходство между элементами
                similarity = 0.0
                common_fields = 0
                
                for field_name in ["text", "description", "what", "content"]:
                    if field_name in item1 and field_name in item2:
                        if isinstance(item1[field_name], str) and isinstance(item2[field_name], str):
                            field_similarity = text_similarity(item1[field_name], item2[field_name])
                            similarity += field_similarity
                            common_fields += 1
                
                # Вычисляем среднее сходство
                avg_similarity = similarity / common_fields if common_fields > 0 else 0.0
                
                # Если элементы достаточно похожи, объединяем их
                if avg_similarity >= similarity_threshold:
                    merged_group[i] = merge_items(item1, item2)
                    merged_group[j] = None
        
        # Добавляем уникальные элементы в результат
        for item in merged_group:
            if item is not None:
                unique_items.append(item)
    
    logger.debug(f"Deduplicated {len(items)} items to {len(unique_items)} unique items")
    return unique_items
