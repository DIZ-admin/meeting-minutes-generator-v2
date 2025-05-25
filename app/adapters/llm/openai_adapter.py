"""
Адаптер для языковых моделей OpenAI
"""
import json
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
    from openai import OpenAI
    from openai.types.chat import ChatCompletion
    from openai import BadRequestError, RateLimitError, APIError, APIConnectionError, InternalServerError, AuthenticationError
except ImportError:
    # Установка openai и tiktoken, если отсутствуют
    import subprocess
    subprocess.check_call(["pip", "install", "openai"])
    subprocess.check_call(["pip", "install", "tiktoken"])
    import tiktoken
    from openai import OpenAI
    from openai.types.chat import ChatCompletion
    from openai import BadRequestError, RateLimitError, APIError

from .base import LLMAdapter
from ...core.exceptions import LLMError, ConfigError, ValidationError
from ...utils.logging import get_default_logger
from ...utils.retry import retry_sync, RetryPresets, RetryConfig
from ...utils.cache import get_cache, generate_content_hash, cache_llm_response, get_cached_llm_response
from ...utils.metrics import monitor_api_calls, track_api_request
from ...config.config import config

logger = get_default_logger(__name__)

class OpenAILLMAdapter(LLMAdapter):
    """
    Адаптер для языковых моделей OpenAI
    
    Поддерживает модели GPT-3.5-turbo, GPT-4, GPT-4o и другие.
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
        Инициализирует адаптер для OpenAI LLM
        
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
        
        # Инициализируем клиент OpenAI
        try:
            self.client = OpenAI(api_key=self.api_key)
            logger.debug(f"OpenAI client initialized with model {self.model}")
        except Exception as e:
            error_msg = f"Error initializing OpenAI client: {e}"
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
    
    def generate_text(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: float = 120.0,
        use_cache: bool = True,
        **kwargs
    ) -> str:
        """
        Генерирует текст на основе промпта с использованием OpenAI API и кеширования
        
        Args:
            prompt: Основной промпт для генерации
            system_message: Системное сообщение для контекста
            temperature: Температура семплирования (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе
            timeout: Таймаут запроса в секундах
            use_cache: Использовать кеширование результатов
            **kwargs: Дополнительные параметры для OpenAI API
            
        Returns:
            Сгенерированный текст
            
        Raises:
            LLMError: Если произошла ошибка при генерации текста
        """
        # Проверяем кеш если разрешено и temperature достаточно низкая для кеширования
        cache_key = None
        if use_cache and temperature <= 0.3:  # Кешируем только детерминистичные запросы
            try:
                # Создаем ключ кеша
                cache_components = [
                    prompt,
                    system_message or "",
                    str(temperature),
                    str(max_tokens),
                    self.model,
                    str(sorted(kwargs.items()))
                ]
                cache_key = generate_content_hash(":".join(cache_components))
                
                # Пытаемся получить из кеша
                cached_result = get_cached_llm_response(cache_key)
                if cached_result is not None:
                    logger.debug("LLM cache hit for text generation")
                    return cached_result
                else:
                    logger.debug("LLM cache miss for text generation")
                    
            except Exception as e:
                logger.warning(f"Cache lookup failed: {e}")
                cache_key = None
        # Формируем сообщения для чата
        messages = []
        
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        messages.append({"role": "user", "content": prompt})
        
        # Логируем запрос (без токена API)
        logger.debug(f"Generating text with model {self.model}, temperature {temperature}")
        
        # Выполняем запрос
        result = self._execute_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            response_format=kwargs.get("response_format", None),
            **kwargs
        )
        
        # Сохраняем в кеш если разрешено
        if use_cache and cache_key and result and temperature <= 0.3:
            try:
                cache_success = cache_llm_response(cache_key, result, ttl=3600)  # 1 час
                if cache_success:
                    logger.debug("LLM result cached for text generation")
                else:
                    logger.warning("Failed to cache LLM result")
            except Exception as e:
                logger.warning(f"Cache save failed: {e}")
        
        return result
    
    def generate_json(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.3,
        schema: Optional[Dict[str, Any]] = None,
        timeout: float = 120.0,
        use_cache: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Генерирует JSON на основе промпта с использованием OpenAI API и кеширования
        
        Args:
            prompt: Основной промпт для генерации
            system_message: Системное сообщение для контекста
            temperature: Температура семплирования (0.0 - 1.0)
            schema: Опциональная JSON-схема для валидации ответа
            timeout: Таймаут запроса в секундах
            use_cache: Использовать кеширование результатов
            **kwargs: Дополнительные параметры для OpenAI API
            
        Returns:
            Сгенерированный JSON как словарь Python
            
        Raises:
            LLMError: Если произошла ошибка при генерации JSON
            ValidationError: Если сгенерированный JSON не соответствует схеме
        """
        # Проверяем кеш если разрешено
        cache_key = None
        if use_cache:
            try:
                # Создаем ключ кеша
                cache_components = [
                    prompt,
                    system_message or "",
                    str(temperature),
                    str(schema) if schema else "",
                    self.model,
                    str(sorted(kwargs.items()))
                ]
                cache_key = generate_content_hash(":".join(cache_components))
                
                # Пытаемся получить из кеша
                cached_result = get_cached_llm_response(cache_key)
                if cached_result is not None:
                    logger.debug("LLM cache hit for JSON generation")
                    return cached_result
                else:
                    logger.debug("LLM cache miss for JSON generation")
                    
            except Exception as e:
                logger.warning(f"Cache lookup failed: {e}")
                cache_key = None
        
        # Формируем сообщения для чата
        messages = []
        
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        # Для GPT-4o и новее можно использовать параметр response_format
        response_format = {"type": "json_object"}
        
        # Если передана схема, можно добавить её в промпт
        if schema:
            prompt_with_schema = f"{prompt}\n\nJSON Schema:\n```json\n{json.dumps(schema, indent=2)}\n```"
            messages.append({"role": "user", "content": prompt_with_schema})
        else:
            messages.append({"role": "user", "content": prompt})
        
        # Логируем запрос (без токена API)
        logger.debug(f"Generating JSON with model {self.model}, temperature {temperature}")
        
        # Выполняем запрос к API
        raw_json_response = self._execute_chat_completion(
            messages=messages,
            temperature=temperature,
            timeout=timeout,
            response_format=response_format,
            **kwargs
        )
        
        # Парсим JSON
        try:
            # Подробное логирование ответа для отладки
            logger.debug(f"Raw JSON response (first 200 chars): {raw_json_response[:200]}...")
            
            # Проверяем, есть ли в ответе фигурные скобки JSON
            if not (raw_json_response.strip().startswith('{') and raw_json_response.strip().endswith('}')):
                # Если нет, пытаемся найти JSON в тексте
                logger.warning("Response does not appear to be a valid JSON object, trying to extract JSON")
                import re
                json_match = re.search(r'\{[\s\S]*\}', raw_json_response)
                if json_match:
                    raw_json_response = json_match.group(0)
                    logger.debug(f"Extracted JSON: {raw_json_response[:200]}...")
                else:
                    logger.error("Could not extract JSON from response")
                    # Создаем пустой JSON с информацией об ошибке
                    return {
                        "error": "Failed to extract valid JSON from response",
                        "raw_response": raw_json_response[:500]  # Первые 500 символов для отладки
                    }
            
            # Пытаемся парсить JSON
            result = json.loads(raw_json_response)
            logger.debug(f"Successfully parsed JSON response with keys: {list(result.keys()) if isinstance(result, dict) else 'not a dict'}")
            
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
            
            # Сохраняем в кеш если разрешено
            if use_cache and cache_key and result:
                try:
                    cache_success = cache_llm_response(cache_key, result, ttl=3600)  # 1 час
                    if cache_success:
                        logger.debug("LLM result cached for JSON generation")
                    else:
                        logger.warning("Failed to cache LLM JSON result")
                except Exception as e:
                    logger.warning(f"Cache save failed: {e}")
            
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
    
    def count_tokens(self, text: str) -> int:
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
        # Проверяем, является ли модель новейшей версией
        is_latest_model = any(model_name in self.model for model_name in ["gpt-4o", "gpt-4-turbo", "gpt-4-0125"])
        
        features = ["chat", "json_generation", "token_count"]
        if is_latest_model:
            features.extend(["vision", "high_token_limit", "improved_reasoning"])
            
        return {
            "name": "OpenAILLMAdapter",
            "provider": "OpenAI",
            "model": self.model,
            "encoding": self.encoding_name,
            "features": features,
            "is_latest_model": is_latest_model
        }
    
    @retry_sync(RetryPresets.API_CALLS)
    @monitor_api_calls("openai", "chat_completion")
    def _execute_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        timeout: float = 120.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> str:
        """
        Вспомогательный метод для выполнения запроса к Chat Completion API с retry логикой
        
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
                    
                # Добавляем seed для воспроизводимости, если температура низкая
                if temperature <= 0.2 and "seed" not in kwargs:
                    # Используем фиксированный seed для воспроизводимости
                    params["seed"] = 42
                
                # Добавляем дополнительные параметры
                params.update(kwargs)
                
                # Выполняем запрос к API
                response: ChatCompletion = self.client.chat.completions.create(**params)
                
                # Получаем содержимое ответа
                content = response.choices[0].message.content
                
                # Проверяем ответ
                if content is None:
                    logger.warning(f"OpenAI API returned empty content for model {self.model}")
                    return ""  # Возвращаем пустую строку, если содержимое пустое
                
                return content
                
            except (BadRequestError, RateLimitError, APIError, APIConnectionError, InternalServerError) as e:
                last_exception = e
                error_type = type(e).__name__
                logger.warning(f"OpenAI API error (attempt {attempt+1}/{self.max_retries}): {error_type}: {e}")
                
                # Для ошибок сервера или соединения увеличиваем задержку сильнее
                if isinstance(e, (APIConnectionError, InternalServerError)):
                    retry_delay *= 3
                else:
                    # Увеличиваем задержку экспоненциально
                    retry_delay *= 2
                
                time.sleep(retry_delay)
                
            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error during OpenAI API call (attempt {attempt+1}/{self.max_retries}): {e}", exc_info=True)
                time.sleep(retry_delay)
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
