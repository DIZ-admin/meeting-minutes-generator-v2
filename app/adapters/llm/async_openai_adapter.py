"""
Асинхронный адаптер для языковых моделей OpenAI
"""
import json
import asyncio
import time
from typing import Dict, List, Optional, Any, Union, Tuple

try:
    import jsonschema
except ImportError:
    import subprocess
    subprocess.check_call(["pip", "install", "jsonschema"])
    import jsonschema

try:
    import tiktoken
    from openai import AsyncOpenAI
    from openai.types.chat import ChatCompletion
    from openai import BadRequestError, RateLimitError, APIError
except ImportError:
    # Установка openai и tiktoken, если отсутствуют
    import subprocess
    subprocess.check_call(["pip", "install", "openai"])
    subprocess.check_call(["pip", "install", "tiktoken"])
    import tiktoken
    from openai import AsyncOpenAI
    from openai.types.chat import ChatCompletion
    from openai import BadRequestError, RateLimitError, APIError

from .async_base import AsyncLLMAdapter
from ...core.exceptions import LLMError, ConfigError, ValidationError
from ...utils.logging import get_default_logger
from ...config.config import config

logger = get_default_logger(__name__)

class AsyncOpenAILLMAdapter(AsyncLLMAdapter):
    """
    Асинхронный адаптер для языковых моделей OpenAI
    
    Поддерживает модели GPT-3.5-turbo, GPT-4, GPT-4o и другие.
    Использует асинхронный клиент OpenAI для параллельной обработки запросов.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: int = 5,
        encoding_name: str = "cl100k_base"
    ):
        """
        Инициализирует асинхронный адаптер для OpenAI LLM
        
        Args:
            api_key: API ключ OpenAI (если None, берется из конфигурации)
            model: Имя модели (если None, берется из конфигурации)
            max_retries: Максимальное количество попыток при ошибке API
            retry_delay: Начальная задержка между попытками в секундах
            encoding_name: Имя кодировки для tiktoken
            
        Raises:
            ConfigError: Если API ключ не найден ни в параметрах, ни в конфигурации
            ImportError: Если не установлены необходимые зависимости
        """
        self.api_key = api_key or config.openai_api_key
        self.model = model or config.openai_model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.encoding_name = encoding_name
        
        if not self.api_key:
            raise ConfigError(
                "OpenAI API key not found. Set OPENAI_API_KEY env variable or pass it directly."
            )
        
        # Инициализируем асинхронный клиент OpenAI
        try:
            self.client = AsyncOpenAI(api_key=self.api_key)
            logger.debug(f"Async OpenAI client initialized with model {self.model}")
        except Exception as e:
            error_msg = f"Error initializing Async OpenAI client: {e}"
            logger.error(error_msg)
            raise ConfigError(error_msg) from e
        
        # Инициализируем tokenizer
        try:
            self.encoding = tiktoken.get_encoding(self.encoding_name)
            logger.debug(f"Initialized tiktoken encoding: {self.encoding_name}")
        except Exception as e:
            error_msg = f"Error initializing tiktoken encoding: {e}"
            logger.error(error_msg)
            raise ConfigError(error_msg) from e
    
    async def generate_text(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: float = 120.0,
        **kwargs
    ) -> str:
        """
        Асинхронно генерирует текст на основе промпта с использованием OpenAI API
        
        Args:
            prompt: Основной промпт для генерации
            system_message: Системное сообщение для контекста
            temperature: Температура семплирования (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе
            timeout: Таймаут запроса в секундах
            **kwargs: Дополнительные параметры для OpenAI API
            
        Returns:
            Сгенерированный текст
            
        Raises:
            LLMError: Если произошла ошибка при генерации текста
        """
        # Формируем сообщения для чата
        messages = []
        
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        messages.append({"role": "user", "content": prompt})
        
        # Логируем запрос (без токена API)
        logger.debug(f"Generating text with model {self.model}, temperature {temperature}")
        
        return await self._execute_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            response_format=kwargs.get("response_format", None),
            **kwargs
        )
    
    async def generate_json(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.3,
        schema: Optional[Dict[str, Any]] = None,
        timeout: float = 120.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Асинхронно генерирует JSON на основе промпта с использованием OpenAI API
        
        Args:
            prompt: Основной промпт для генерации
            system_message: Системное сообщение для контекста
            temperature: Температура семплирования (0.0 - 1.0)
            schema: Опциональная JSON-схема для валидации ответа
            timeout: Таймаут запроса в секундах
            **kwargs: Дополнительные параметры для OpenAI API
            
        Returns:
            Сгенерированный JSON как словарь Python
            
        Raises:
            LLMError: Если произошла ошибка при генерации JSON
            ValidationError: Если сгенерированный JSON не соответствует схеме
        """
        # Формируем сообщения для чата
        messages = []
        
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        # Для GPT-4o и новее используем параметр response_format
        response_format = {"type": "json_object"}
        
        # Если передана схема, добавляем её в промпт
        if schema:
            prompt_with_schema = f"{prompt}\n\nJSON Schema:\n```json\n{json.dumps(schema, indent=2)}\n```"
            messages.append({"role": "user", "content": prompt_with_schema})
        else:
            messages.append({"role": "user", "content": prompt})
        
        # Логируем запрос (без токена API)
        logger.debug(f"Generating JSON with model {self.model}, temperature {temperature}")
        
        # Выполняем запрос к API
        raw_json_response = await self._execute_chat_completion(
            messages=messages,
            temperature=temperature,
            timeout=timeout,
            response_format=response_format,
            **kwargs
        )
        
        # Парсим JSON
        try:
            result = json.loads(raw_json_response)
            logger.debug("Successfully parsed JSON response")
            
            # Если передана схема, валидируем JSON
            if schema:
                try:
                    jsonschema.validate(result, schema)
                    logger.debug("JSON validation passed successfully")
                except jsonschema.ValidationError as e:
                    logger.error(f"JSON validation failed: {e.message}", exc_info=True)
                    logger.debug(f"Failed JSON content: {json.dumps(result, indent=2, ensure_ascii=False)}")
                    raise ValidationError(f"Generated JSON doesn't match provided schema: {e.message}") from e
                except jsonschema.SchemaError as e:
                    logger.error(f"Invalid JSON schema provided: {e.message}", exc_info=True)
                    raise ValidationError(f"Invalid JSON schema: {e.message}") from e
            
            return result
        except json.JSONDecodeError as e:
            error_msg = f"Error decoding JSON response: {e}"
            logger.error(f"{error_msg}. Raw response: {raw_json_response}")
            
            raise LLMError(
                message=error_msg,
                details={
                    "raw_response": raw_json_response,
                    "json_decode_error": str(e),
                },
                api_name="OpenAI"
            ) from e
    
    async def count_tokens(self, text: str) -> int:
        """
        Подсчитывает количество токенов в тексте с использованием tiktoken
        
        Args:
            text: Текст для подсчета токенов
            
        Returns:
            Количество токенов
        """
        return len(self.encoding.encode(text))
    
    def get_adapter_info(self) -> Dict[str, Any]:
        """
        Возвращает информацию об адаптере
        
        Returns:
            Словарь с информацией об адаптере
        """
        return {
            "name": "AsyncOpenAILLMAdapter",
            "provider": "OpenAI",
            "model": self.model,
            "encoding": self.encoding_name,
            "features": ["chat", "json_generation", "token_count", "async"]
        }
    
    async def _execute_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        timeout: float = 120.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> str:
        """
        Асинхронный вспомогательный метод для выполнения запроса к Chat Completion API
        
        Args:
            messages: Список сообщений для чата
            temperature: Температура семплирования
            timeout: Таймаут запроса в секундах
            max_tokens: Максимальное количество токенов в ответе
            response_format: Формат ответа (например, {"type": "json_object"})
            **kwargs: Дополнительные параметры для OpenAI API
            
        Returns:
            Текст ответа от модели
            
        Raises:
            LLMError: Если произошла ошибка при запросе к API
        """
        last_exception = None
        retry_delay = self.retry_delay
        
        for attempt in range(self.max_retries):
            try:
                # Формируем параметры запроса
                params = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "timeout": timeout,
                }
                
                # Добавляем опциональные параметры
                if max_tokens is not None:
                    params["max_tokens"] = max_tokens
                
                if response_format is not None:
                    params["response_format"] = response_format
                
                # Добавляем дополнительные параметры
                params.update(kwargs)
                
                # Выполняем запрос к API
                response: ChatCompletion = await self.client.chat.completions.create(**params)
                
                # Получаем содержимое ответа
                content = response.choices[0].message.content
                
                # Проверяем ответ
                if content is None:
                    logger.warning(f"OpenAI API returned empty content for model {self.model}")
                    return ""  # Возвращаем пустую строку, если содержимое пустое
                
                return content
            
            except (BadRequestError, RateLimitError, APIError) as e:
                last_exception = e
                logger.warning(
                    f"OpenAI API error (attempt {attempt+1}/{self.max_retries}): {e}. "
                    f"Retrying in {retry_delay}s..."
                )
                
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Экспоненциальное увеличение задержки
            
            except Exception as e:
                last_exception = e
                logger.error(
                    f"Unexpected error during OpenAI API call (attempt {attempt+1}/{self.max_retries}): {e}",
                    exc_info=True
                )
                
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
        
        # Если все попытки исчерпаны и ни одна не удалась
        error_msg = f"Failed OpenAI API call after {self.max_retries} attempts"
        logger.error(error_msg)
        
        # Создаем и выбрасываем исключение с деталями
        raise LLMError(
            message=error_msg,
            details={"last_exception": str(last_exception)},
            api_name="OpenAI",
            api_response=getattr(last_exception, "response", None),
        ) from last_exception
