#!/usr/bin/env python3
"""
CLI приложение с Typer (refactored) - использует AudioFileProcessor
"""
import sys
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.text import Text

# Добавляем родительскую директорию в путь импорта
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

from app.core.services.pipeline import Pipeline
from app.core.exceptions import ConfigError
from app.utils.logging import get_default_logger
from app.config.config import config
from app.cli_services.file_processor import AudioFileProcessor, MetadataBuilder

# Инициализация Typer и Rich
app = typer.Typer(
    help="Генератор протоколов совещаний (Service Layer Version)",
    add_completion=False
)
console = Console()
logger = get_default_logger(__name__)

def display_header():
    """Отображает заголовок приложения"""
    title_text = Text("Генератор протоколов совещаний", style="bold cyan")
    version_text = Text(f"Версия {config.app_version} (Service Layer)", style="cyan")  
    panel = Panel.fit(
        title_text + "\n" + version_text,
        border_style="blue"
    )
    console.print(panel)

def create_progress_callback(progress: Progress, task_id):
    """Создает callback функцию для обновления прогресса"""
    def progress_callback(stage: str, percent: float):
        progress.update(task_id, completed=int(percent * 100), description=f"[cyan]{stage}")
    return progress_callback

def create_batch_progress_callback(progress: Progress, task_id):
    """Создает callback функцию для batch обработки"""
    def batch_progress_callback(description: str, current: int, total: int):
        progress.update(task_id, completed=current, total=total, description=f"[cyan]{description}")
    return batch_progress_callback

def display_results(success: bool, md_file: Optional[Path], json_file: Optional[Path], error_msg: Optional[str]):
    """Отображает результаты обработки"""
    if success and md_file and json_file:
        console.print("\n[bold green]Обработка завершена успешно![/]")
        console.print(f"[bold]Выходные файлы:[/]")
        console.print(f"  - Markdown: [cyan]{md_file}[/]")
        console.print(f"  - JSON: [cyan]{json_file}[/]")
    else:
        console.print(f"\n[bold red]Ошибка обработки:[/] {error_msg}")

def display_batch_results(success: bool, results: list, summary_msg: str):
    """Отображает результаты batch обработки"""
    if success:
        console.print(f"\n[bold green]{summary_msg}[/]")
    else:
        console.print(f"\n[bold yellow]{summary_msg}[/]")
    
    # Показываем детали по каждому файлу
    if results:
        console.print("\n[bold]Детали обработки:[/]")
        for file_path, file_success, file_error in results:
            status = "[green]✓[/]" if file_success else "[red]✗[/]"
            console.print(f"  {status} {file_path.name}")
            if not file_success and file_error:
                console.print(f"    [red]Ошибка:[/] {file_error}")

@app.command()
def process(
    audio: str = typer.Argument(..., help="Путь к аудиофайлу или директории"),
    batch: bool = typer.Option(False, "--batch", "-b", help="Обработать все файлы в директории"),
    lang: Optional[str] = typer.Option(None, "--lang", "-l", help="Код языка"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Директория для результатов"),
    skip_telegram: bool = typer.Option(False, "--skip-telegram", help="Пропустить Telegram"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Название совещания"),
    date: Optional[str] = typer.Option(None, "--date", "-d", help="Дата совещания"),
    location: Optional[str] = typer.Option(None, "--location", help="Место проведения"),
    organizer: Optional[str] = typer.Option(None, "--organizer", help="Организатор"),
    participants: Optional[str] = typer.Option(None, "--participants", help="Участники через запятую"),
    agenda: Optional[str] = typer.Option(None, "--agenda", help="Повестка через запятую"),
    debug: bool = typer.Option(False, "--debug", help="Отладочное логирование")
):
    """Обработать аудиофайл(ы) и сгенерировать протокол совещания"""    # Отображаем заголовок
    display_header()
    
    try:
        # Настраиваем логирование
        if debug:
            import logging
            logging.basicConfig(level=logging.DEBUG)
        
        # Преобразуем пути в объекты Path
        audio_path = Path(audio)
        output_dir = Path(output) if output else None
        
        # Подготавливаем метаданные используя MetadataBuilder
        metadata = MetadataBuilder.from_cli_args(
            title=title, date=date, location=location, organizer=organizer,
            participants=participants, agenda=agenda
        )
        
        # Инициализируем Pipeline и AudioFileProcessor
        console.print("[bold blue]Инициализация конвейера...[/]")
        pipeline = Pipeline()
        processor = AudioFileProcessor(pipeline)
        
        # Обрабатываем аудиофайл(ы)
        if audio_path.is_dir() and batch:
            # Пакетная обработка директории
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Обработка файлов...", total=100)
                batch_callback = create_batch_progress_callback(progress, task)
                
                success, results, summary_msg = processor.process_batch(
                    directory_path=audio_path,
                    output_dir=output_dir,
                    language=lang,
                    metadata=metadata,
                    skip_notifications=skip_telegram,
                    progress_callback=batch_callback
                )
                
                display_batch_results(success, results, summary_msg)
        
        elif audio_path.is_dir() and not batch:
            console.print(
                "[bold yellow]Указана директория, но не включен режим пакетной обработки.[/] "
                "Используйте флаг --batch для обработки всех файлов в директории."
            )
            sys.exit(1)
        
        else:
            # Обработка одного файла
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Обработка...", total=100)
                callback = create_progress_callback(progress, task)
                
                success, md_file, json_file, error_msg = processor.process_single_file(
                    audio_path=audio_path,
                    output_dir=output_dir,
                    language=lang,
                    metadata=metadata,
                    skip_notifications=skip_telegram,
                    progress_callback=callback
                )
                
                display_results(success, md_file, json_file, error_msg)
        
        # Возвращаем код завершения
        sys.exit(0 if success else 1)
            
    except Exception as e:
        console.print(f"[bold red]Критическая ошибка:[/] {e}")
        if debug:
            console.print_exception()
        sys.exit(1)

@app.command()
def process_transcript(
    transcript: str = typer.Argument(..., help="Путь к JSON-файлу транскрипта"),
    lang: Optional[str] = typer.Option(None, "--lang", "-l", help="Код языка"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Директория для результатов"),
    skip_telegram: bool = typer.Option(False, "--skip-telegram", help="Пропустить Telegram"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Название совещания"),
    date: Optional[str] = typer.Option(None, "--date", "-d", help="Дата совещания"),
    location: Optional[str] = typer.Option(None, "--location", help="Место проведения"),
    organizer: Optional[str] = typer.Option(None, "--organizer", help="Организатор"),
    participants: Optional[str] = typer.Option(None, "--participants", help="Участники через запятую"),
    agenda: Optional[str] = typer.Option(None, "--agenda", help="Повестка через запятую"),
    debug: bool = typer.Option(False, "--debug", help="Отладочное логирование")
):
    """Обработать JSON-файл транскрипта и сгенерировать протокол совещания"""
    display_header()
    
    try:
        # Настраиваем логирование
        if debug:
            import logging
            logging.basicConfig(level=logging.DEBUG)
        
        # Преобразуем пути в объекты Path
        transcript_path = Path(transcript)
        output_dir = Path(output) if output else None
        
        # Подготавливаем метаданные
        metadata = MetadataBuilder.from_cli_args(
            title=title, date=date, location=location, organizer=organizer,
            participants=participants, agenda=agenda
        )
        
        # Инициализируем Pipeline и AudioFileProcessor
        console.print("[bold blue]Инициализация конвейера...[/]")
        pipeline = Pipeline()
        processor = AudioFileProcessor(pipeline)
        
        # Обрабатываем файл транскрипта
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Обработка...", total=100)
            callback = create_progress_callback(progress, task)
            
            success, md_file, json_file, error_msg = processor.process_transcript_file(
                transcript_path=transcript_path,
                output_dir=output_dir,
                language=lang,
                metadata=metadata,
                skip_notifications=skip_telegram,
                progress_callback=callback
            )
            
            display_results(success, md_file, json_file, error_msg)
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        console.print(f"[bold red]Критическая ошибка:[/] {e}")
        if debug:
            console.print_exception()
        sys.exit(1)

@app.command()
def web():
    """Запустить веб-интерфейс для генерации протоколов"""
    try:
        from app.web import start
        console.print("[bold green]Запуск веб-интерфейса...[/]")
        start()
    except ImportError:
        console.print("[bold red]Ошибка:[/] Модуль веб-интерфейса не найден.")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Ошибка при запуске веб-интерфейса:[/] {e}")
        sys.exit(1)

def main():
    """Основная функция CLI-приложения"""
    app()

if __name__ == "__main__":
    main()
