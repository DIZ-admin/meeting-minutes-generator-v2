#!/usr/bin/env python3
"""
Скрипт для автоматического удаления bug маркеров из кода
"""
import re
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def clean_bug_markers(file_path: Path) -> int:
    """Удаляет bug маркеры из файла и возвращает количество удаленных"""
    try:
        content = file_path.read_text(encoding='utf-8')
        original_content = content
        
        # Паттерны для поиска bug маркеров
        patterns = [
            r'\n\s*bug\s*\n',  # bug на отдельной строке
            r'\n\s*BUG\s*\n',  # BUG на отдельной строке
            r'\n\s*TODO\s*\n', # TODO без описания
            r'\n\s*FIXME\s*\n', # FIXME без описания
            r'\n\s*HACK\s*\n',  # HACK без описания
            r'\n\s*XXX\s*\n',   # XXX без описания
            r'#\s*bug\s*$',     # bug в конце строки с комментарием
            r'#\s*BUG\s*$',     # BUG в конце строки с комментарием
        ]
        
        count = 0
        for pattern in patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            count += len(matches)
            # Заменяем на пустую строку или убираем комментарий
            if pattern.startswith(r'\n'):
                content = re.sub(pattern, '\n', content)
            else:
                content = re.sub(pattern, '', content)
        
        # Убираем множественные пустые строки
        content = re.sub(r'\n\n\n+', '\n\n', content)
        
        if content != original_content:
            file_path.write_text(content, encoding='utf-8')
            logger.info(f"Cleaned {count} bug markers from {file_path}")
            return count
        
        return 0
        
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return 0

def find_and_clean_bug_markers(project_dir: Path):
    """Находит и очищает bug маркеры во всех Python файлах проекта"""
    total_files = 0
    total_markers = 0
    
    # Исключаем некоторые директории
    exclude_dirs = {'.venv', 'venv', '__pycache__', '.git', '.pytest_cache', 'node_modules'}
    
    for py_file in project_dir.rglob('*.py'):
        # Проверяем, что файл не в исключенных директориях
        if any(excluded in py_file.parts for excluded in exclude_dirs):
            continue
            
        markers_removed = clean_bug_markers(py_file)
        if markers_removed > 0:
            total_files += 1
            total_markers += markers_removed
    
    logger.info(f"Total: Cleaned {total_markers} bug markers from {total_files} files")

if __name__ == "__main__":
    project_dir = Path("/Users/kostas/Documents/Projects/meeting")
    find_and_clean_bug_markers(project_dir)
