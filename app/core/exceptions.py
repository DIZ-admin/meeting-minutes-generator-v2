"""
Иерархия исключений приложения
"""
from typing import Optional, Any, Dict, List

class AppBaseError(Exception):
    """Базовое исключение для всех ошибок приложения"""
    def __init__(self, message: str = "Произошла ошибка в приложении", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message

class ConfigError(AppBaseError):
    """Ошибка в конфигурации приложения"""
    def __init__(self, message: str = "Ошибка в конфигурации", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)

class AuthenticationError(AppBaseError):
    """Ошибка аутентификации"""
    def __init__(self, message: str = "Ошибка аутентификации", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)

class DatabaseError(AppBaseError):
    """Ошибка при работе с базой данных"""
    def __init__(self, message: str = "Ошибка базы данных", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)

class APIError(AppBaseError):
    """Ошибка при взаимодействии с внешним API"""
    def __init__(
        self, 
        message: str = "Ошибка во время вызова внешнего API", 
        details: Optional[Dict[str, Any]] = None,
        api_name: Optional[str] = None,
        status_code: Optional[int] = None,
        api_response: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if api_name:
            details["api_name"] = api_name
        if status_code:
            details["status_code"] = status_code
        if api_response:
            details["api_response"] = api_response
        
        super().__init__(message, details)

class ASRError(APIError):
    """Ошибка при распознавании речи"""
    def __init__(
        self, 
        message: str = "Ошибка при распознавании речи", 
        details: Optional[Dict[str, Any]] = None,
        api_name: Optional[str] = None,
        status_code: Optional[int] = None,
        api_response: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details, api_name, status_code, api_response)

class LLMError(APIError):
    """Ошибка при взаимодействии с языковой моделью"""
    def __init__(
        self, 
        message: str = "Ошибка при взаимодействии с языковой моделью", 
        details: Optional[Dict[str, Any]] = None,
        api_name: Optional[str] = None,
        status_code: Optional[int] = None,
        api_response: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details, api_name, status_code, api_response)

class NotificationError(APIError):
    """Ошибка при отправке уведомлений"""
    def __init__(
        self, 
        message: str = "Ошибка при отправке уведомления", 
        details: Optional[Dict[str, Any]] = None,
        api_name: Optional[str] = None,
        status_code: Optional[int] = None,
        api_response: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details, api_name, status_code, api_response)

class ValidationError(AppBaseError):
    """Ошибка валидации данных"""
    def __init__(
        self, 
        message: str = "Ошибка валидации данных", 
        details: Optional[Dict[str, Any]] = None,
        validation_errors: Optional[List[str]] = None
    ):
        details = details or {}
        if validation_errors:
            details["validation_errors"] = validation_errors
        
        super().__init__(message, details)

class FileProcessingError(AppBaseError):
    """Ошибка при обработке файлов"""
    def __init__(
        self, 
        message: str = "Ошибка при обработке файла", 
        details: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None
    ):
        details = details or {}
        if file_path:
            details["file_path"] = file_path
        
        super().__init__(message, details)

class AudioProcessingError(FileProcessingError):
    """Ошибка при обработке аудиофайла"""
    def __init__(
        self, 
        message: str = "Ошибка при обработке аудиофайла", 
        details: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None
    ):
        super().__init__(message, details, file_path)
