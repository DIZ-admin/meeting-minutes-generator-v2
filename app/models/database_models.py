"""
SQLAlchemy модели для базы данных
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import Column, String, Boolean, DateTime, JSON, ForeignKey, Table, Text, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from ..services.database_service import Base

# Таблица для связи многие-ко-многим между пользователями и ролями
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id')),
    Column('role_id', UUID(as_uuid=True), ForeignKey('roles.id'))
)

class User(Base):
    """Модель пользователя"""
    __tablename__ = 'users'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Отношения
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    protocols = relationship("Protocol", back_populates="created_by")
    sessions = relationship("UserSession", back_populates="user")

class Role(Base):
    """Модель роли"""
    __tablename__ = 'roles'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    
    # Отношения
    users = relationship("User", secondary=user_roles, back_populates="roles")

class UserSession(Base):
    """Модель сессии пользователя"""
    __tablename__ = 'user_sessions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)  # Поддержка IPv6
    
    # Отношения
    user = relationship("User", back_populates="sessions")

class Protocol(Base):
    """Модель протокола встречи"""
    __tablename__ = 'protocols'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Метаданные протокола
    title = Column(String(255), nullable=False)
    date = Column(DateTime, nullable=False)
    location = Column(String(255), nullable=True)
    organizer = Column(String(255), nullable=True)
    
    # Файлы
    audio_file_path = Column(Text, nullable=True)
    transcript_file_path = Column(Text, nullable=True)
    markdown_file_path = Column(Text, nullable=True)
    json_file_path = Column(Text, nullable=True)
    
    # Данные протокола
    participants = Column(JSON, nullable=True)  # {"present": [...], "absent": [...]}
    agenda = Column(JSON, nullable=True)  # ["item1", "item2", ...]
    summary = Column(Text, nullable=True)
    decisions = Column(JSON, nullable=True)  # [{"decision": "...", "responsible": "..."}]
    action_items = Column(JSON, nullable=True)  # [{"task": "...", "responsible": "...", "deadline": "..."}]
    
    # Статус обработки
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Метаданные
    created_by_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    
    # Дополнительные поля
    language = Column(String(10), default="de")
    duration_seconds = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)
    
    # Отношения
    created_by = relationship("User", back_populates="protocols")
    processing_tasks = relationship("ProcessingTask", back_populates="protocol")

class ProcessingTask(Base):
    """Модель задачи обработки"""
    __tablename__ = 'processing_tasks'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(255), unique=True, nullable=False, index=True)
    protocol_id = Column(UUID(as_uuid=True), ForeignKey('protocols.id'), nullable=False)
    
    # Статус задачи
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    message = Column(Text, nullable=True)
    
    # Тайминги
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Результат
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    
    # Отношения
    protocol = relationship("Protocol", back_populates="processing_tasks")

class ApiKey(Base):
    """Модель API ключа для внешних интеграций"""
    __tablename__ = 'api_keys'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Права доступа
    scopes = Column(JSON, nullable=True)  # ["read:protocols", "write:protocols", ...]
    rate_limit = Column(Integer, default=1000)  # Запросов в час
    
    # Статус
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    
    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
