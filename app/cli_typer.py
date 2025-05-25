#!/usr/bin/env python3
"""
CLI приложение для генерации протоколов совещаний с использованием Typer
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

import typer
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.text import Text

# Добавляем родительскую директорию в путь импорта
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

from app.core.services.pipeline import Pipeline
from app.core.exceptions import ASRError, LLMError, ConfigError
from app.utils.logging import get_default_logger
from app.config.config import config

# Инициализация Typer и Rich
app = typer.Typer(
    help="Генератор протоколов совещаний из аудиозаписей",
    add_completion=False
)
console = Console()

def process_single_file(
    pipeline: Pipeline,
    audio_path: Path,
    output_dir: Optional[Path],
    language: Optional[str],
    metadata: Dict[str, Any],
    skip_notifications: bool
) -> bool:
    """
    Обрабатывает один аудиофайл с отображением прогресса
    
    Args:
        pipeline: Экземпляр Pipeline
        audio_path: Путь к аудиофайлу
        output_dir: Директория для сохранения результатов
        language: Язык аудио
        metadata: Метаданные протокола
        skip_notifications: Пропустить отправку уведомлений
        
    Returns:
        True, если обработка выполнена успешно, иначе False
    """
    try:
        # Отображаем информацию о файле
        console.print(f"[bold blue]Обработка аудиофайла:[/] {audio_path}")
        
        # Создаем прогресс-бар
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            # Создаем задачу для прогресс-бара
            task = progress.add_task("[cyan]Обработка...", total=100)
            
            # Обновляем прогресс на начальное значение
            progress.update(task, completed=5, description="[cyan]Инициализация...")
            
            # Создаем функцию обратного вызова для обновления прогресса
            def progress_callback(stage: str, percent: float):
                progress.update(
                    task, 
                    completed=int(percent * 100), 
                    description=f"[cyan]{stage}"
                )
            
            # Обрабатываем аудиофайл с обратным вызовом для прогресса
            md_file, json_file = pipeline.process_audio(
                audio_path=audio_path,
                output_dir=output_dir,
                language=language,
                meeting_info=metadata,
                skip_notifications=skip_notifications,
                progress_callback=progress_callback  # Передаем функцию обратного вызова
            )
            
            # Завершаем прогресс
            progress.update(task, completed=100, description="[green]Завершено!")
        
        # Выводим информацию о результатах
        console.print("\n[bold green]Обработка завершена успешно![/]")
        console.print(f"[bold]Выходные файлы:[/]")
        console.print(f"  - Markdown: [cyan]{md_file}[/]")
        console.print(f"  - JSON: [cyan]{json_file}[/]")
        
        return True
        
    except FileNotFoundError as e:
        console.print(f"[bold red]Ошибка:[/] Файл не найден: {e}")
        return False
        
    except ASRError as e:
        console.print(f"[bold red]Ошибка ASR:[/] {e}")
        return False
        
    except LLMError as e:
        console.print(f"[bold red]Ошибка LLM:[/] {e}")
        return False
        
    except Exception as e:
        console.print(f"[bold red]Непредвиденная ошибка:[/] {e}")
        return False

def process_batch(
    pipeline: Pipeline,
    directory_path: Path,
    output_dir: Optional[Path],
    language: Optional[str],
    metadata: Optional[Dict[str, Any]],
    skip_notifications: bool
) -> bool:
    """
    Обрабатывает все аудиофайлы в директории
    
    Args:
        pipeline: Экземпляр Pipeline
        directory_path: Путь к директории с аудиофайлами
        output_dir: Директория для сохранения результатов
        language: Язык аудио
        metadata: Метаданные протокола
        skip_notifications: Пропустить отправку уведомлений
        
    Returns:
        True, если обработка всех файлов выполнена успешно, иначе False
    """
    # Проверяем существование директории
    if not directory_path.exists() or not directory_path.is_dir():
        console.print(f"[bold red]Ошибка:[/] Директория не найдена: {directory_path}")
        return False
    
    # Находим все аудиофайлы в директории
    audio_files = []
    for ext in ['.wav', '.mp3', '.m4a', '.ogg']:
        audio_files.extend(directory_path.glob(f"*{ext}"))
    
    # Проверяем, что есть файлы для обработки
    if not audio_files:
        console.print(f"[bold yellow]Предупреждение:[/] В директории {directory_path} не найдено аудиофайлов")
        return False
    
    # Выводим информацию о найденных файлах
    console.print(f"[bold blue]Найдено {len(audio_files)} аудиофайлов в директории {directory_path}[/]")
    
    # Обрабатываем каждый файл
    success_count = 0
    for i, audio_file in enumerate(audio_files):
        console.print(f"\n[bold]Файл {i+1}/{len(audio_files)}:[/] {audio_file.name}")
        
        # Создаем поддиректорию для результатов, если output_dir указан
        file_output_dir = None
        if output_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_output_dir = output_dir / f"{audio_file.stem}_{timestamp}"
        
        # Обрабатываем файл
        if process_single_file(
            pipeline=pipeline,
            audio_path=audio_file,
            output_dir=file_output_dir,
            language=language,
            metadata=metadata.copy() if metadata else {},
            skip_notifications=skip_notifications
        ):
            success_count += 1
    
    # Выводим итоговую информацию
    if success_count == len(audio_files):
        console.print(f"\n[bold green]Все файлы ({success_count}/{len(audio_files)}) успешно обработаны![/]")
        return True
    else:
        console.print(f"\n[bold yellow]Обработано {success_count}/{len(audio_files)} файлов.[/]")
        return False

@app.command()
def process(
    audio: str = typer.Argument(
        ..., 
        help="Путь к аудиофайлу (wav/m4a/mp3) или директории с аудиофайлами"
    ),
    batch: bool = typer.Option(
        False, 
        "--batch", 
        "-b", 
        help="Обработать все аудиофайлы в директории (если audio - директория)"
    ),
    lang: Optional[str] = typer.Option(
        None, 
        "--lang", 
        "-l", 
        help="Код языка (например, 'de' для немецкого, по умолчанию из переменной окружения или 'de')"
    ),
    output: Optional[str] = typer.Option(
        None, 
        "--output", 
        "-o", 
        help="Директория для сохранения результатов (по умолчанию: ./output/[имя_файла])"
    ),
    skip_telegram: bool = typer.Option(
        False, 
        "--skip-telegram", 
        help="Пропустить отправку уведомлений в Telegram"
    ),
    title: Optional[str] = typer.Option(
        None, 
        "--title", 
        "-t", 
        help="Название совещания (по умолчанию: извлекается из имени файла)"
    ),
    date: Optional[str] = typer.Option(
        None, 
        "--date", 
        "-d", 
        help="Дата совещания в формате YYYY-MM-DD (по умолчанию: извлекается из имени файла или текущая дата)"
    ),
    location: Optional[str] = typer.Option(
        None, 
        "--location", 
        help="Место проведения совещания (по умолчанию: 'Online Meeting')"
    ),
    organizer: Optional[str] = typer.Option(
        None, 
        "--organizer", 
        help="Организатор совещания (по умолчанию: пусто)"
    ),
    participants: Optional[str] = typer.Option(
        None, 
        "--participants", 
        help="Список участников через запятую"
    ),
    agenda: Optional[str] = typer.Option(
        None, 
        "--agenda", 
        help="Список пунктов повестки через запятую"
    ),
    debug: bool = typer.Option(
        False, 
        "--debug", 
        help="Включить отладочное логирование"
    )
):
    """
    Обработать аудиофайл(ы) и сгенерировать протокол совещания
    """
    # Отображаем заголовок
    title_text = Text("Генератор протоколов совещаний", style="bold cyan")
    version_text = Text(f"Версия {config.app_version}", style="cyan")
    panel = Panel.fit(
        title_text + "\n" + version_text,
        border_style="blue"
    )
    console.print(panel)
    
    try:
        # Преобразуем пути в объекты Path
        audio_path = Path(audio)
        output_dir = Path(output) if output else None
        
        # Подготавливаем метаданные
        metadata = {}
        if title:
            metadata["title"] = title
        if date:
            metadata["date"] = date
        if location:
            metadata["location"] = location
        if organizer:
            metadata["organizer"] = organizer
        if participants:
            metadata["participants"] = participants.split(",")
        if agenda:
            metadata["agenda"] = agenda.split(",")
        
        # Добавляем автора
        metadata["author"] = "AI Assistant"
        
        # Инициализируем Pipeline
        console.print("[bold blue]Инициализация конвейера...[/]")
        pipeline = Pipeline()
        
        # Обрабатываем аудиофайл(ы)
        if audio_path.is_dir() and batch:
            # Пакетная обработка директории
            result = process_batch(
                pipeline=pipeline,
                directory_path=audio_path,
                output_dir=output_dir,
                language=lang,
                metadata=metadata,
                skip_notifications=skip_telegram
            )
        elif audio_path.is_dir() and not batch:
            console.print(
                "[bold yellow]Указана директория, но не включен режим пакетной обработки.[/] "
                "Используйте флаг --batch для обработки всех файлов в директории."
            )
            result = False
        else:
            # Обработка одного файла
            result = process_single_file(
                pipeline=pipeline,
                audio_path=audio_path,
                output_dir=output_dir,
                language=lang,
                metadata=metadata,
                skip_notifications=skip_telegram
            )
        
        # Возвращаем код завершения
        if not result:
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[bold red]Критическая ошибка:[/] {e}")
        if debug:
            console.print_exception()
        sys.exit(1)

@app.command()
def web():
    """
    Запустить веб-интерфейс для генерации протоколов
    """
    try:
        from app.web import start
        console.print("[bold green]Запуск веб-интерфейса...[/]")
        start()
    except ImportError:
        console.print("[bold red]Ошибка:[/] Модуль веб-интерфейса не найден.")
        console.print("Убедитесь, что установлены все необходимые зависимости:")
        console.print("  - fastapi")
        console.print("  - uvicorn")
        console.print("  - python-multipart")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Ошибка при запуске веб-интерфейса:[/] {e}")
        sys.exit(1)

def main():
    """Основная функция CLI-приложения"""
    app()

@app.command()
def process_transcript(
    transcript: str = typer.Argument(
        ..., 
        help="Путь к JSON-файлу транскрипта"
    ),
    lang: Optional[str] = typer.Option(
        None, 
        "--lang", 
        "-l", 
        help="Код языка (например, 'de' для немецкого, по умолчанию из переменной окружения или 'de')"
    ),
    output: Optional[str] = typer.Option(
        None, 
        "--output", 
        "-o", 
        help="Директория для сохранения результатов (по умолчанию: ./output/[имя_файла])"
    ),
    skip_telegram: bool = typer.Option(
        False, 
        "--skip-telegram", 
        help="Пропустить отправку уведомлений в Telegram"
    ),
    title: Optional[str] = typer.Option(
        None, 
        "--title", 
        "-t", 
        help="Название совещания (по умолчанию: извлекается из имени файла)"
    ),
    date: Optional[str] = typer.Option(
        None, 
        "--date", 
        "-d", 
        help="Дата совещания в формате YYYY-MM-DD (по умолчанию: извлекается из имени файла или текущая дата)"
    ),
    location: Optional[str] = typer.Option(
        None, 
        "--location", 
        help="Место проведения совещания (по умолчанию: 'Online Meeting')"
    ),
    organizer: Optional[str] = typer.Option(
        None, 
        "--organizer", 
        help="Организатор совещания (по умолчанию: пусто)"
    ),
    participants: Optional[str] = typer.Option(
        None, 
        "--participants", 
        help="Список участников через запятую"
    ),
    agenda: Optional[str] = typer.Option(
        None, 
        "--agenda", 
        help="Список пунктов повестки через запятую"
    ),
    debug: bool = typer.Option(
        False, 
        "--debug", 
        help="Включить отладочное логирование"
    )
):
    """
    Обработать JSON-файл транскрипта и сгенерировать протокол совещания
    """
    try:
        # Настраиваем уровень логирования
        if debug:
            import logging
            logging.basicConfig(level=logging.DEBUG)
        
        # Преобразуем пути в объекты Path
        transcript_path = Path(transcript)
        
        # Проверяем существование файла
        if not transcript_path.exists():
            console.print(f"[bold red]Ошибка:[/] Файл {transcript_path} не найден")
            return 1
        
        # Проверяем расширение файла
        if transcript_path.suffix.lower() != ".json":
            console.print(f"[bold red]Ошибка:[/] Файл {transcript_path} должен иметь расширение .json")
            return 1
        
        # Определяем директорию для выходных файлов
        if output:
            output_dir = Path(output)
        else:
            output_dir = None
        
        # Подготавливаем метаданные
        metadata = {}
        if title:
            metadata["title"] = title
        if date:
            metadata["date"] = date
        if location:
            metadata["location"] = location
        if organizer:
            metadata["organizer"] = organizer
        if participants:
            metadata["participants"] = participants.split(",")
        if agenda:
            metadata["agenda"] = agenda.split(",")
        
        # Инициализируем Pipeline
        console.print("[bold blue]Инициализация конвейера...[/]")
        pipeline = Pipeline()
        
        # Обрабатываем файл транскрипта
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            # Создаем задачу для прогресс-бара
            task = progress.add_task("[cyan]Обработка...", total=100)
            
            # Обновляем прогресс на начальное значение
            progress.update(task, completed=5, description="[cyan]Инициализация...")
            
            # Создаем функцию обратного вызова для обновления прогресса
            def progress_callback(stage: str, percent: float):
                progress.update(
                    task, 
                    completed=int(percent * 100), 
                    description=f"[cyan]{stage}"
                )
            
            # Обрабатываем JSON-файл транскрипта с обратным вызовом для прогресса
            md_file, json_file = pipeline.process_transcript_json(
                transcript_path=transcript_path,
                output_dir=output_dir,
                language=lang,
                meeting_info=metadata,
                skip_notifications=skip_telegram,
                progress_callback=progress_callback
            )
            
            # Завершаем прогресс
            progress.update(task, completed=100, description="[green]Завершено!")
        
        # Выводим информацию о результатах
        console.print("\n[bold green]Обработка завершена успешно![/]")
        console.print(f"[bold]Выходные файлы:[/]")
        console.print(f"  - Markdown: [cyan]{md_file}[/]")
        console.print(f"  - JSON: [cyan]{json_file}[/]")
        
        return 0
    
    except json.JSONDecodeError as e:
        console.print(f"[bold red]Ошибка декодирования JSON:[/] {e}")
        return 1
    
    except LLMError as e:
        console.print(f"[bold red]Ошибка обработки текста:[/] {e}")
        return 1
    
    except ConfigError as e:
        console.print(f"[bold red]Ошибка конфигурации:[/] {e}")
        return 1
    
    except Exception as e:
        console.print(f"[bold red]Непредвиденная ошибка:[/] {e}")
        import traceback
        console.print(traceback.format_exc())
        return 1

if __name__ == "__main__":
    main()
