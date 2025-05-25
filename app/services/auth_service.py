"""
Authentication Service для управления пользователями и безопасностью
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Any, Union
from pathlib import Path
import json

import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field, SecretStr

from ..utils.logging import get_default_logger
from ..core.exceptions import AuthenticationError, ConfigError

logger = get_default_logger(__name__)

# Модели данных для аутентификации
class UserCreate(BaseModel):
    """Модель для создания пользователя"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: SecretStr = Field(..., min_length=8)
    full_name: Optional[str] = None
    roles: List[str] = Field(default_factory=lambda: ["user"])

class UserInDB(BaseModel):
    """Модель пользователя в базе данных"""
    id: str
    username: str
    email: str
    hashed_password: str
    full_name: Optional[str] = None
    roles: List[str] = Field(default_factory=lambda: ["user"])
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Token(BaseModel):
    """Модель токена доступа"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class TokenData(BaseModel):
    """Данные, содержащиеся в токене"""
    username: Optional[str] = None
    user_id: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    exp: Optional[datetime] = None

class Session(BaseModel):
    """Модель сессии пользователя"""
    session_id: str
    user_id: str
    username: str
    roles: List[str]
    created_at: datetime
    expires_at: datetime
    is_active: bool = True
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

class AuthenticationService:
    """
    Сервис аутентификации с поддержкой JWT, RBAC и управления сессиями
    
    Предоставляет функциональность для:
    - Регистрации и аутентификации пользователей
    - Генерации и валидации JWT токенов
    - Управления ролями и разрешениями (RBAC)
    - Управления сессиями пользователей
    """
    
    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        session_expire_hours: int = 24,
        db_path: Optional[Path] = None
    ):
        """
        Инициализация сервиса аутентификации
        
        Args:
            secret_key: Секретный ключ для JWT (если None, генерируется случайный)
            algorithm: Алгоритм для JWT
            access_token_expire_minutes: Время жизни токена в минутах
            session_expire_hours: Время жизни сессии в часах
            db_path: Путь к файлу БД (временное решение до PostgreSQL)
        """
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.session_expire_hours = session_expire_hours
        
        # Контекст для хеширования паролей
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        # Временное хранилище (будет заменено на PostgreSQL)
        self.db_path = db_path or Path("./data/auth.json")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Загружаем данные из файла
        self._load_data()
        
        logger.info("AuthenticationService initialized")

    
    def _load_data(self) -> None:
        """Загружает данные из файла (временное решение)"""
        self.users: Dict[str, UserInDB] = {}
        self.sessions: Dict[str, Session] = {}
        
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r') as f:
                    data = json.load(f)
                    
                # Загружаем пользователей
                for user_data in data.get("users", []):
                    user = UserInDB(**user_data)
                    self.users[user.username] = user
                    
                # Загружаем сессии
                for session_data in data.get("sessions", []):
                    session = Session(**session_data)
                    self.sessions[session.session_id] = session
                    
            except Exception as e:
                logger.warning(f"Failed to load auth data: {e}")
    
    def _save_data(self) -> None:
        """Сохраняет данные в файл (временное решение)"""
        try:
            data = {
                "users": [user.model_dump(mode='json') for user in self.users.values()],
                "sessions": [session.model_dump(mode='json') for session in self.sessions.values()]
            }
            
            with open(self.db_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to save auth data: {e}")
    
    # Методы для работы с паролями
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Проверяет пароль"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Хеширует пароль"""
        return self.pwd_context.hash(password)

    
    # Методы для работы с пользователями
    def create_user(self, user_create: UserCreate) -> UserInDB:
        """
        Создает нового пользователя
        
        Args:
            user_create: Данные для создания пользователя
            
        Returns:
            Созданный пользователь
            
        Raises:
            AuthenticationError: Если пользователь уже существует
        """
        if user_create.username in self.users:
            raise AuthenticationError(
                message="User already exists",
                details={"username": user_create.username}
            )
        
        # Создаем пользователя
        user_id = secrets.token_urlsafe(16)
        hashed_password = self.get_password_hash(user_create.password.get_secret_value())
        
        user = UserInDB(
            id=user_id,
            username=user_create.username,
            email=user_create.email,
            hashed_password=hashed_password,
            full_name=user_create.full_name,
            roles=user_create.roles
        )
        
        self.users[user.username] = user
        self._save_data()
        
        logger.info(f"Created user: {user.username}")
        return user
    
    def get_user(self, username: str) -> Optional[UserInDB]:
        """Получает пользователя по имени"""
        return self.users.get(username)
    
    def get_user_by_id(self, user_id: str) -> Optional[UserInDB]:
        """Получает пользователя по ID"""
        for user in self.users.values():
            if user.id == user_id:
                return user
        return None

    
    def authenticate_user(self, username: str, password: str) -> Optional[UserInDB]:
        """
        Аутентифицирует пользователя
        
        Args:
            username: Имя пользователя
            password: Пароль
            
        Returns:
            Пользователь, если аутентификация успешна, иначе None
        """
        user = self.get_user(username)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user
    
    # Методы для работы с JWT токенами
    def create_access_token(
        self, 
        user: UserInDB,
        expires_delta: Optional[timedelta] = None
    ) -> Token:
        """
        Создает JWT токен доступа
        
        Args:
            user: Пользователь
            expires_delta: Время жизни токена
            
        Returns:
            Токен доступа
        """
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=self.access_token_expire_minutes
            )
        
        to_encode = {
            "sub": user.username,
            "user_id": user.id,
            "roles": user.roles,
            "exp": expire
        }
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        return Token(
            access_token=encoded_jwt,
            expires_in=int(expire.timestamp())
        )

    
    def decode_token(self, token: str) -> TokenData:
        """
        Декодирует и валидирует JWT токен
        
        Args:
            token: JWT токен
            
        Returns:
            Данные из токена
            
        Raises:
            AuthenticationError: Если токен невалидный или истек
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            username: str = payload.get("sub")
            user_id: str = payload.get("user_id")
            roles: List[str] = payload.get("roles", [])
            
            if username is None or user_id is None:
                raise AuthenticationError(
                    message="Invalid token payload",
                    details={"error": "Missing required fields"}
                )
            
            token_data = TokenData(
                username=username,
                user_id=user_id,
                roles=roles
            )
            
            return token_data
            
        except jwt.ExpiredSignatureError:
            raise AuthenticationError(
                message="Token has expired",
                details={"error": "Token expired"}
            )
        except jwt.PyJWTError as e:
            raise AuthenticationError(
                message="Invalid token",
                details={"error": str(e)}
            )

    
    # Методы для управления сессиями
    def create_session(
        self,
        user: UserInDB,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Session:
        """
        Создает новую сессию пользователя
        
        Args:
            user: Пользователь
            user_agent: User-Agent браузера
            ip_address: IP адрес клиента
            
        Returns:
            Созданная сессия
        """
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=self.session_expire_hours)
        
        session = Session(
            session_id=session_id,
            user_id=user.id,
            username=user.username,
            roles=user.roles,
            created_at=now,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address
        )
        
        self.sessions[session_id] = session
        self._save_data()
        
        logger.info(f"Created session for user: {user.username}")
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Получает сессию по ID"""
        session = self.sessions.get(session_id)
        
        if session:
            # Проверяем, не истекла ли сессия
            if session.expires_at < datetime.now(timezone.utc):
                self.invalidate_session(session_id)
                return None
            
            if not session.is_active:
                return None
                
        return session

    
    def invalidate_session(self, session_id: str) -> bool:
        """
        Инвалидирует сессию
        
        Args:
            session_id: ID сессии
            
        Returns:
            True, если сессия была инвалидирована
        """
        if session_id in self.sessions:
            self.sessions[session_id].is_active = False
            self._save_data()
            logger.info(f"Invalidated session: {session_id}")
            return True
        return False
    
    def invalidate_user_sessions(self, user_id: str) -> int:
        """
        Инвалидирует все сессии пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Количество инвалидированных сессий
        """
        count = 0
        for session in self.sessions.values():
            if session.user_id == user_id and session.is_active:
                session.is_active = False
                count += 1
        
        if count > 0:
            self._save_data()
            logger.info(f"Invalidated {count} sessions for user: {user_id}")
            
        return count

    
    # Методы для RBAC (Role-Based Access Control)
    def check_permission(
        self,
        user_roles: List[str],
        required_roles: List[str],
        require_all: bool = False
    ) -> bool:
        """
        Проверяет, есть ли у пользователя необходимые роли
        
        Args:
            user_roles: Роли пользователя
            required_roles: Требуемые роли
            require_all: Если True, требуются все роли, иначе хотя бы одна
            
        Returns:
            True, если пользователь имеет необходимые роли
        """
        if not required_roles:
            return True
            
        if "admin" in user_roles:
            return True  # Админ имеет все права
            
        if require_all:
            return all(role in user_roles for role in required_roles)
        else:
            return any(role in user_roles for role in required_roles)
    
    def add_role_to_user(self, username: str, role: str) -> bool:
        """
        Добавляет роль пользователю
        
        Args:
            username: Имя пользователя
            role: Роль для добавления
            
        Returns:
            True, если роль добавлена успешно
        """
        user = self.get_user(username)
        if not user:
            return False
            
        if role not in user.roles:
            user.roles.append(role)
            user.updated_at = datetime.now(timezone.utc)
            self._save_data()
            logger.info(f"Added role '{role}' to user: {username}")
            return True
            
        return False

    
    def remove_role_from_user(self, username: str, role: str) -> bool:
        """
        Удаляет роль у пользователя
        
        Args:
            username: Имя пользователя
            role: Роль для удаления
            
        Returns:
            True, если роль удалена успешно
        """
        user = self.get_user(username)
        if not user:
            return False
            
        if role in user.roles and role != "user":  # Базовую роль user нельзя удалить
            user.roles.remove(role)
            user.updated_at = datetime.now(timezone.utc)
            self._save_data()
            logger.info(f"Removed role '{role}' from user: {username}")
            return True
            
        return False
    
    def update_user(self, username: str, **kwargs) -> Optional[UserInDB]:
        """
        Обновляет данные пользователя
        
        Args:
            username: Имя пользователя
            **kwargs: Поля для обновления
            
        Returns:
            Обновленный пользователь или None
        """
        user = self.get_user(username)
        if not user:
            return None
            
        # Обновляем разрешенные поля
        allowed_fields = {"email", "full_name", "is_active"}
        for field, value in kwargs.items():
            if field in allowed_fields and hasattr(user, field):
                setattr(user, field, value)
        
        user.updated_at = datetime.now(timezone.utc)
        self._save_data()
        
        logger.info(f"Updated user: {username}")
        return user

    
    def get_active_sessions(self, user_id: Optional[str] = None) -> List[Session]:
        """
        Получает активные сессии
        
        Args:
            user_id: ID пользователя (если None, возвращает все сессии)
            
        Returns:
            Список активных сессий
        """
        now = datetime.now(timezone.utc)
        active_sessions = []
        
        for session in self.sessions.values():
            if session.is_active and session.expires_at > now:
                if user_id is None or session.user_id == user_id:
                    active_sessions.append(session)
                    
        return active_sessions
    
    def cleanup_expired_sessions(self) -> int:
        """
        Удаляет истекшие сессии
        
        Returns:
            Количество удаленных сессий
        """
        now = datetime.now(timezone.utc)
        expired_sessions = []
        
        for session_id, session in self.sessions.items():
            if session.expires_at < now:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del self.sessions[session_id]
        
        if expired_sessions:
            self._save_data()
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
            
        return len(expired_sessions)
