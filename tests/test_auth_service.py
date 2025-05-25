"""
Тесты для Authentication Service
"""
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import json

from app.services.auth_service import (
    AuthenticationService,
    UserCreate,
    UserInDB,
    Token,
    TokenData,
    Session
)
from app.core.exceptions import AuthenticationError

class TestAuthenticationService:
    """Тесты для сервиса аутентификации"""
    
    @pytest.fixture
    def temp_db_path(self):
        """Создает временный файл для БД"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = Path(f.name)
        yield temp_path
        # Очистка
        if temp_path.exists():
            temp_path.unlink()
    
    @pytest.fixture
    def auth_service(self, temp_db_path):
        """Создает экземпляр AuthenticationService с временной БД"""
        return AuthenticationService(
            secret_key="test-secret-key",
            db_path=temp_db_path
        )
    
    @pytest.fixture
    def test_user_data(self):
        """Тестовые данные пользователя"""
        return UserCreate(
            username="testuser",
            email="test@example.com",
            password="SecurePassword123!",
            full_name="Test User",
            roles=["user"]
        )

    
    def test_create_user_success(self, auth_service, test_user_data):
        """Тест успешного создания пользователя"""
        # Создаем пользователя
        user = auth_service.create_user(test_user_data)
        
        # Проверяем результат
        assert user.username == test_user_data.username
        assert user.email == test_user_data.email
        assert user.full_name == test_user_data.full_name
        assert user.roles == test_user_data.roles
        assert user.is_active is True
        assert user.id is not None
        assert user.hashed_password != test_user_data.password.get_secret_value()
    
    def test_create_duplicate_user(self, auth_service, test_user_data):
        """Тест создания дубликата пользователя"""
        # Создаем первого пользователя
        auth_service.create_user(test_user_data)
        
        # Пытаемся создать дубликат
        with pytest.raises(AuthenticationError) as exc_info:
            auth_service.create_user(test_user_data)
        
        assert "User already exists" in str(exc_info.value)
    
    def test_authenticate_user_success(self, auth_service, test_user_data):
        """Тест успешной аутентификации"""
        # Создаем пользователя
        auth_service.create_user(test_user_data)
        
        # Аутентифицируем
        authenticated_user = auth_service.authenticate_user(
            test_user_data.username,
            test_user_data.password.get_secret_value()
        )
        
        assert authenticated_user is not None
        assert authenticated_user.username == test_user_data.username
    
    def test_authenticate_user_wrong_password(self, auth_service, test_user_data):
        """Тест аутентификации с неверным паролем"""
        # Создаем пользователя
        auth_service.create_user(test_user_data)
        
        # Пытаемся аутентифицироваться с неверным паролем
        authenticated_user = auth_service.authenticate_user(
            test_user_data.username,
            "WrongPassword123"
        )
        
        assert authenticated_user is None

    
    def test_authenticate_nonexistent_user(self, auth_service):
        """Тест аутентификации несуществующего пользователя"""
        authenticated_user = auth_service.authenticate_user(
            "nonexistent",
            "password"
        )
        
        assert authenticated_user is None
    
    def test_create_access_token(self, auth_service, test_user_data):
        """Тест создания JWT токена"""
        # Создаем пользователя
        user = auth_service.create_user(test_user_data)
        
        # Создаем токен
        token = auth_service.create_access_token(user)
        
        assert isinstance(token, Token)
        assert token.token_type == "bearer"
        assert len(token.access_token) > 0
        assert token.expires_in > 0
    
    def test_decode_token_success(self, auth_service, test_user_data):
        """Тест успешного декодирования токена"""
        # Создаем пользователя и токен
        user = auth_service.create_user(test_user_data)
        token = auth_service.create_access_token(user)
        
        # Декодируем токен
        token_data = auth_service.decode_token(token.access_token)
        
        assert token_data.username == user.username
        assert token_data.user_id == user.id
        assert token_data.roles == user.roles
    
    def test_decode_invalid_token(self, auth_service):
        """Тест декодирования невалидного токена"""
        with pytest.raises(AuthenticationError) as exc_info:
            auth_service.decode_token("invalid.token.here")
        
        assert "Invalid token" in str(exc_info.value)
    
    def test_decode_expired_token(self, auth_service, test_user_data):
        """Тест декодирования истекшего токена"""
        # Создаем пользователя
        user = auth_service.create_user(test_user_data)
        
        # Создаем токен с очень коротким сроком жизни
        token = auth_service.create_access_token(
            user,
            expires_delta=timedelta(seconds=-1)  # Уже истек
        )
        
        with pytest.raises(AuthenticationError) as exc_info:
            auth_service.decode_token(token.access_token)
        
        assert "Token has expired" in str(exc_info.value)

    
    def test_create_session(self, auth_service, test_user_data):
        """Тест создания сессии"""
        # Создаем пользователя
        user = auth_service.create_user(test_user_data)
        
        # Создаем сессию
        session = auth_service.create_session(
            user,
            user_agent="Mozilla/5.0",
            ip_address="192.168.1.1"
        )
        
        assert isinstance(session, Session)
        assert session.user_id == user.id
        assert session.username == user.username
        assert session.roles == user.roles
        assert session.is_active is True
        assert session.user_agent == "Mozilla/5.0"
        assert session.ip_address == "192.168.1.1"
    
    def test_get_session_valid(self, auth_service, test_user_data):
        """Тест получения валидной сессии"""
        # Создаем пользователя и сессию
        user = auth_service.create_user(test_user_data)
        session = auth_service.create_session(user)
        
        # Получаем сессию
        retrieved_session = auth_service.get_session(session.session_id)
        
        assert retrieved_session is not None
        assert retrieved_session.session_id == session.session_id
        assert retrieved_session.user_id == user.id
    
    def test_get_expired_session(self, auth_service, test_user_data):
        """Тест получения истекшей сессии"""
        # Создаем пользователя
        user = auth_service.create_user(test_user_data)
        
        # Создаем сессию с прошедшей датой истечения
        session = auth_service.create_session(user)
        session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        auth_service._save_data()
        
        # Пытаемся получить истекшую сессию
        retrieved_session = auth_service.get_session(session.session_id)
        
        assert retrieved_session is None

    
    def test_invalidate_session(self, auth_service, test_user_data):
        """Тест инвалидации сессии"""
        # Создаем пользователя и сессию
        user = auth_service.create_user(test_user_data)
        session = auth_service.create_session(user)
        
        # Инвалидируем сессию
        success = auth_service.invalidate_session(session.session_id)
        
        assert success is True
        
        # Проверяем, что сессия неактивна
        invalidated_session = auth_service.sessions[session.session_id]
        assert invalidated_session.is_active is False
    
    def test_check_permission_single_role(self, auth_service):
        """Тест проверки одной роли"""
        user_roles = ["user", "moderator"]
        
        # Проверяем существующую роль
        assert auth_service.check_permission(user_roles, ["moderator"]) is True
        
        # Проверяем несуществующую роль
        assert auth_service.check_permission(user_roles, ["admin"]) is False
    
    def test_check_permission_multiple_roles_any(self, auth_service):
        """Тест проверки нескольких ролей (любая)"""
        user_roles = ["user"]
        
        # Хотя бы одна роль совпадает
        assert auth_service.check_permission(
            user_roles, 
            ["admin", "user", "moderator"], 
            require_all=False
        ) is True
        
        # Ни одна роль не совпадает
        assert auth_service.check_permission(
            user_roles,
            ["admin", "moderator"],
            require_all=False
        ) is False
    
    def test_check_permission_admin_bypass(self, auth_service):
        """Тест обхода проверки для админа"""
        admin_roles = ["admin"]
        
        # Админ имеет все права
        assert auth_service.check_permission(
            admin_roles,
            ["any", "role", "here"]
        ) is True

    
    def test_add_role_to_user(self, auth_service, test_user_data):
        """Тест добавления роли пользователю"""
        # Создаем пользователя
        user = auth_service.create_user(test_user_data)
        
        # Добавляем роль
        success = auth_service.add_role_to_user(user.username, "moderator")
        
        assert success is True
        
        # Проверяем, что роль добавлена
        updated_user = auth_service.get_user(user.username)
        assert "moderator" in updated_user.roles
    
    def test_remove_role_from_user(self, auth_service, test_user_data):
        """Тест удаления роли у пользователя"""
        # Создаем пользователя с дополнительной ролью
        test_user_data.roles = ["user", "moderator"]
        user = auth_service.create_user(test_user_data)
        
        # Удаляем роль
        success = auth_service.remove_role_from_user(user.username, "moderator")
        
        assert success is True
        
        # Проверяем, что роль удалена
        updated_user = auth_service.get_user(user.username)
        assert "moderator" not in updated_user.roles
        assert "user" in updated_user.roles  # Базовая роль остается
    
    def test_cannot_remove_base_user_role(self, auth_service, test_user_data):
        """Тест невозможности удаления базовой роли user"""
        # Создаем пользователя
        user = auth_service.create_user(test_user_data)
        
        # Пытаемся удалить базовую роль
        success = auth_service.remove_role_from_user(user.username, "user")
        
        assert success is False
        
        # Проверяем, что роль не удалена
        updated_user = auth_service.get_user(user.username)
        assert "user" in updated_user.roles

    
    def test_update_user(self, auth_service, test_user_data):
        """Тест обновления данных пользователя"""
        # Создаем пользователя
        user = auth_service.create_user(test_user_data)
        
        # Обновляем данные
        updated_user = auth_service.update_user(
            user.username,
            email="newemail@example.com",
            full_name="Updated Name",
            is_active=False
        )
        
        assert updated_user is not None
        assert updated_user.email == "newemail@example.com"
        assert updated_user.full_name == "Updated Name"
        assert updated_user.is_active is False
    
    def test_cleanup_expired_sessions(self, auth_service, test_user_data):
        """Тест очистки истекших сессий"""
        # Создаем пользователя
        user = auth_service.create_user(test_user_data)
        
        # Создаем несколько сессий
        active_session = auth_service.create_session(user)
        expired_session1 = auth_service.create_session(user)
        expired_session2 = auth_service.create_session(user)
        
        # Делаем две сессии истекшими
        expired_session1.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        expired_session2.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        auth_service._save_data()
        
        # Очищаем истекшие сессии
        cleaned_count = auth_service.cleanup_expired_sessions()
        
        assert cleaned_count == 2
        assert active_session.session_id in auth_service.sessions
        assert expired_session1.session_id not in auth_service.sessions
        assert expired_session2.session_id not in auth_service.sessions
    
    def test_data_persistence(self, temp_db_path):
        """Тест сохранения данных между сессиями"""
        # Создаем первый экземпляр сервиса
        service1 = AuthenticationService(db_path=temp_db_path)
        
        # Создаем пользователя
        user_data = UserCreate(
            username="persistent_user",
            email="persist@example.com",
            password="Password123!"
        )
        created_user = service1.create_user(user_data)
        
        # Создаем второй экземпляр сервиса
        service2 = AuthenticationService(db_path=temp_db_path)
        
        # Проверяем, что данные загружены
        loaded_user = service2.get_user("persistent_user")
        assert loaded_user is not None
        assert loaded_user.email == "persist@example.com"
        assert loaded_user.id == created_user.id
