"""
Адаптер для уведомлений через Telegram
"""
import os
import requests
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

from .base import NotificationAdapter
from ...core.exceptions import NotificationError, ConfigError
from ...utils.logging import get_default_logger
from ...config.config import config

logger = get_default_logger(__name__)

class TelegramNotificationAdapter(NotificationAdapter):
    """
    Адаптер для отправки уведомлений через Telegram Bot API
    """
    
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: int = 5
    ):
        """
        Инициализирует адаптер для Telegram
        
        Args:
            bot_token: Токен Telegram бота (если None, берется из конфигурации)
            chat_id: ID чата для отправки сообщений (если None, берется из конфигурации)
            parse_mode: Режим парсинга сообщений (Markdown, HTML)
                       (если None, берется из конфигурации)
            max_retries: Максимальное количество попыток при ошибке API
            retry_delay: Начальная задержка между попытками в секундах
            
        Raises:
            ConfigError: Если не найдены обязательные параметры
        """
        # Store the original parameters to properly handle None values
        self._bot_token = bot_token
        self._chat_id = chat_id
        
        # Get values from config if not provided
        self.bot_token = self._bot_token if self._bot_token is not None else getattr(config, 'telegram_bot_token', None)
        
        # Получаем chat_id и преобразуем его в строку, если он есть
        chat_id_value = self._chat_id if self._chat_id is not None else getattr(config, 'telegram_chat_id', None)
        self.chat_id = str(chat_id_value) if chat_id_value is not None else None
        
        self.parse_mode = parse_mode or getattr(config, 'telegram_parse_mode', 'Markdown')
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Формируем URL API
        if self.bot_token:
            self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        else:
            self.api_url = None
        
        # Проверяем настройки адаптера
        if not self.is_configured():
            logger.warning(
                "TelegramNotificationAdapter is not fully configured. "
                "Missing bot_token or chat_id."
            )
    
    def is_configured(self) -> bool:
        """
        Проверяет, настроен ли адаптер
        
        Returns:
            True, если адаптер настроен (есть токен и ID чата), иначе False
        """
        # Добавляем отладочную информацию
        logger.debug(f"Checking Telegram configuration: bot_token={bool(self.bot_token)}, chat_id={bool(self.chat_id)}")
        logger.debug(f"Telegram token type: {type(self.bot_token)}, chat_id type: {type(self.chat_id)}")
        
        # Проверяем, что и токен, и chat_id не пустые
        has_token = bool(self.bot_token)
        has_chat_id = bool(self.chat_id)
        
        return has_token and has_chat_id
    
    def _api_call(
        self,
        method: str,
        data: Optional[Dict] = None,
        files: Optional[Dict] = None,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Выполняет вызов Telegram Bot API
        
        Args:
            method: Метод API (например, 'sendMessage', 'sendDocument')
            data: Данные для отправки
            files: Файлы для отправки
            timeout: Таймаут запроса в секундах
            
        Returns:
            Ответ от API в виде словаря
            
        Raises:
            NotificationError: Если произошла ошибка при вызове API
        """
        # Проверяем настройки адаптера
        if not self.is_configured():
            error_msg = "Telegram API call skipped: adapter not configured"
            logger.error(error_msg)
            raise NotificationError("Telegram adapter is not configured. Missing bot_token or chat_id.")
        
        # Формируем URL API
        url = f"{self.api_url}/{method}"
        
        # Выполняем запрос к API с повторными попытками
        last_exception = None
        retry_delay = self.retry_delay
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    url,
                    data=data,
                    files=files,
                    timeout=timeout
                )
                
                # Проверяем статус ответа
                response.raise_for_status()
                
                # Парсим JSON
                json_response = response.json()
                
                # Проверяем успешность запроса
                if not json_response.get("ok", False):
                    error_msg = (
                        f"Telegram API error: {json_response.get('description', 'Unknown error')}"
                    )
                    logger.warning(
                        f"Telegram API call failed (attempt {attempt+1}/{self.max_retries}): "
                        f"{error_msg}"
                    )
                    
                    # Если это последняя попытка, возвращаем ошибку
                    if attempt == self.max_retries - 1:
                        return json_response
                    
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                
                return json_response
                
            except requests.RequestException as e:
                last_exception = e
                logger.warning(
                    f"Telegram API request error (attempt {attempt+1}/{self.max_retries}): {e}. "
                    f"Retrying in {retry_delay}s..."
                )
                
                time.sleep(retry_delay)
                retry_delay *= 2
        
        # Если все попытки исчерпаны и ни одна не удалась
        error_msg = f"Failed to call Telegram API after {self.max_retries} attempts"
        logger.error(error_msg)
        
        return {
            "ok": False,
            "error_code": getattr(last_exception, "status_code", 500),
            "description": str(last_exception) if last_exception else "Unknown error"
        }
    
    def send_message(
        self,
        text: str,
        parse_mode: str = "Markdown",
        **kwargs
    ) -> bool:
        """
        Отправляет текстовое сообщение в Telegram
        
        Args:
            text: Текст сообщения
            parse_mode: Режим парсинга сообщения (если None, используется значение из конфигурации)
            **kwargs: Дополнительные параметры для метода sendMessage
            
        Returns:
            True, если сообщение отправлено успешно, иначе False
            
        Raises:
            NotificationError: Если произошла ошибка при отправке сообщения
        """
        if not self.is_configured():
            logger.warning("Cannot send message: TelegramNotificationAdapter is not configured")
            return False
        
        try:
            # Подготавливаем данные для отправки
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode or self.parse_mode
            }
            
            # Добавляем дополнительные параметры
            data.update(kwargs)
            
            # Выполняем запрос к API
            response = self._api_call("sendMessage", data=data)
            
            # Проверяем успешность запроса
            if response.get("ok", False):
                logger.info(f"Message sent to Telegram chat {self.chat_id}")
                return True
            
            # Если запрос не удался, логируем ошибку
            error_msg = f"Failed to send message: {response.get('description', 'Unknown error')}"
            logger.error(error_msg)
            
            return False
            
        except Exception as e:
            error_msg = f"Error sending message to Telegram: {e}"
            logger.error(error_msg, exc_info=True)
            
            raise NotificationError(
                message=error_msg,
                api_name="Telegram",
                details={"chat_id": self.chat_id}
            ) from e
    
    def send_file(
        self,
        file_path: Union[str, Path],
        caption: Optional[str] = None,
        parse_mode: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Отправляет файл в Telegram
        
        Args:
            file_path: Путь к файлу
            caption: Подпись к файлу
            parse_mode: Режим парсинга подписи (если None, используется значение из конфигурации)
            **kwargs: Дополнительные параметры для метода sendDocument
            
        Returns:
            True, если файл отправлен успешно, иначе False
            
        Raises:
            NotificationError: Если произошла ошибка при отправке файла
            FileNotFoundError: Если файл не найден
        """
        if not self.is_configured():
            logger.warning("Cannot send file: TelegramNotificationAdapter is not configured")
            return False
        
        try:
            # Преобразуем путь к файлу в объект Path
            file_path_obj = Path(file_path)
            
            # Проверяем существование файла
            if not file_path_obj.exists():
                error_msg = f"File not found: {file_path_obj}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            # Подготавливаем данные для отправки
            data = {
                "chat_id": self.chat_id,
                "parse_mode": parse_mode or self.parse_mode
            }
            
            # Добавляем подпись, если она есть
            if caption:
                data["caption"] = caption
            
            # Добавляем дополнительные параметры
            data.update(kwargs)
            
            # Подготавливаем файл
            files = {
                "document": (file_path_obj.name, open(file_path_obj, "rb"))
            }
            
            try:
                # Выполняем запрос к API
                response = self._api_call("sendDocument", data=data, files=files)
                
                # Проверяем успешность запроса
                if response.get("ok", False):
                    logger.info(f"File '{file_path_obj.name}' sent to Telegram chat {self.chat_id}")
                    return True
                
                # Если запрос не удался, логируем ошибку
                error_msg = f"Failed to send file: {response.get('description', 'Unknown error')}"
                logger.error(error_msg)
                
                return False
                
            finally:
                # Закрываем файл
                if "document" in files and hasattr(files["document"][1], "close"):
                    files["document"][1].close()
            
        except FileNotFoundError:
            # Пробрасываем исключение дальше
            raise
            
        except Exception as e:
            error_msg = f"Error sending file to Telegram: {e}"
            logger.error(error_msg, exc_info=True)
            
            raise NotificationError(
                message=error_msg,
                api_name="Telegram",
                details={"chat_id": self.chat_id, "file_path": str(file_path)}
            ) from e
    
    def send_protocol_files(
        self,
        md_path: Union[str, Path],
        json_path: Union[str, Path],
        notification_text_template: str = "✅ Protocol ready: *{meeting_name}*"
    ) -> bool:
        """
        Отправляет файлы протокола в Telegram
        
        Args:
            md_path: Путь к файлу протокола в формате Markdown
            json_path: Путь к файлу протокола в формате JSON
            notification_text_template: Шаблон текста уведомления
            
        Returns:
            True, если все файлы отправлены успешно, иначе False
        """
        if not self.is_configured():
            logger.warning("Cannot send protocol files: TelegramNotificationAdapter is not configured")
            return False
        
        try:
            # Преобразуем пути к файлам в объекты Path
            md_path_obj = Path(md_path)
            json_path_obj = Path(json_path)
            
            # Получаем имя встречи из имени директории протокола
            meeting_name = md_path_obj.parent.name
            
            # Формируем текст уведомления
            message_text = notification_text_template.format(meeting_name=meeting_name)
            
            # Отправляем уведомление
            message_sent = self.send_message(message_text)
            
            if not message_sent:
                logger.warning("Failed to send notification message, skipping file sending")
                return False
            
            # Отправляем файлы протокола
            md_sent = self.send_file(md_path_obj)
            json_sent = self.send_file(json_path_obj)
            
            if md_sent and json_sent:
                logger.info("All protocol files sent to Telegram successfully")
                return True
            else:
                logger.warning("Failed to send one or more protocol files to Telegram")
                return False
                
        except Exception as e:
            error_msg = f"Error sending protocol files to Telegram: {e}"
            logger.error(error_msg, exc_info=True)
            
            return False
    
    def get_adapter_info(self) -> Dict[str, Any]:
        """
        Возвращает информацию об адаптере
        
        Returns:
            Словарь с информацией об адаптере
        """
        return {
            "name": "TelegramNotificationAdapter",
            "provider": "Telegram",
            "chat_id": self.chat_id,
            "parse_mode": self.parse_mode,
            "is_configured": self.is_configured(),
            "features": ["text_messages", "file_sending"]
        }
