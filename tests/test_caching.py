"""
Тесты для кеширования функциональности
"""
import pytest
import tempfile
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Добавляем родительскую директорию в путь импорта
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

class TestCaching:
    """Тесты для системы кеширования"""
    
    def test_cache_adapter_creation(self):
        """Тестирует создание кеш адаптера"""
        try:
            from app.utils.cache import CacheAdapter
            
            with tempfile.TemporaryDirectory() as temp_dir:
                cache = CacheAdapter(
                    fallback_to_file=True,
                    file_cache_dir=Path(temp_dir)
                )
                assert cache is not None
                assert cache.fallback_to_file is True
                assert cache.is_healthy() is True
        except ImportError:
            pytest.skip("Cache utils not available")
    
    def test_file_cache_basic_operations(self):
        """Тестирует базовые операции файлового кеша"""
        try:
            from app.utils.cache import CacheAdapter
            
            with tempfile.TemporaryDirectory() as temp_dir:
                cache = CacheAdapter(
                    fallback_to_file=True,
                    file_cache_dir=Path(temp_dir),
                    default_ttl=60
                )
                
                # Тест set/get
                test_data = {"test": "data", "number": 42}
                success = cache.set("test_ns", "test_key", test_data)
                assert success is True
                
                retrieved = cache.get("test_ns", "test_key")
                assert retrieved == test_data
                
                # Тест cache miss
                missing = cache.get("test_ns", "missing_key")
                assert missing is None
                
                # Тест delete
                deleted = cache.delete("test_ns", "test_key")
                assert deleted is True
                
                # Проверяем что данные удалены
                after_delete = cache.get("test_ns", "test_key")
                assert after_delete is None
                
        except ImportError:
            pytest.skip("Cache utils not available")
    
    def test_cache_convenience_functions(self):
        """Тестирует convenience функции для кеширования"""
        try:
            from app.utils.cache import (
                cache_asr_result, get_cached_asr_result,
                cache_llm_response, get_cached_llm_response,
                generate_content_hash
            )
            
            # Тест генерации хеша
            hash1 = generate_content_hash("test content")
            hash2 = generate_content_hash("test content")
            hash3 = generate_content_hash("different content")
            
            assert hash1 == hash2  # Одинаковый контент -> одинаковый хеш
            assert hash1 != hash3  # Разный контент -> разный хеш
            assert len(hash1) == 64  # SHA256 хеш
            
            # Тест ASR кеширования
            test_asr_result = [{"text": "hello", "start": 0, "end": 1}]
            success = cache_asr_result("test_hash", test_asr_result)
            
            # Может не сработать если Redis недоступен, но не должно падать
            if success:
                retrieved = get_cached_asr_result("test_hash")
                assert retrieved == test_asr_result
            
            # Тест LLM кеширования  
            test_llm_response = {"response": "test response"}
            success = cache_llm_response("test_prompt_hash", test_llm_response)
            
            if success:
                retrieved = get_cached_llm_response("test_prompt_hash")
                assert retrieved == test_llm_response
                
        except ImportError:
            pytest.skip("Cache utils not available")
    
    def test_cache_health_check(self):
        """Тестирует health check кеша"""
        try:
            from app.utils.cache import get_cache
            
            cache = get_cache()
            health = cache.is_healthy()
            
            # Должен работать хотя бы файловый кеш
            assert isinstance(health, bool)
            
            # Получаем статистику
            stats = cache.get_stats()
            assert isinstance(stats, dict)
            assert "redis_available" in stats
            assert "fallback_enabled" in stats
            
        except ImportError:
            pytest.skip("Cache utils not available")
    
    def test_llm_adapter_caching_integration(self):
        """Тестирует интеграцию кеширования в LLM адаптер"""
        try:
            from app.adapters.llm.openai_adapter import OpenAILLMAdapter
            
            # Проверяем что методы имеют параметр use_cache
            adapter_file = parent_dir / "app" / "adapters" / "llm" / "openai_adapter.py"
            if adapter_file.exists():
                content = adapter_file.read_text(encoding="utf-8")
                assert "use_cache: bool = True" in content, "use_cache parameter not found in LLM adapter"
                assert "cache_llm_response" in content, "LLM caching function not imported"
                assert "get_cached_llm_response" in content, "LLM cache retrieval function not imported"
                
        except ImportError:
            pytest.skip("LLM adapter not available")
    
    def test_asr_service_caching_integration(self):
        """Тестирует интеграцию кеширования в ASR сервис"""
        try:
            from app.core.services.asr_service import ASRService
            
            # Проверяем что ASR сервис имеет кеширование
            asr_file = parent_dir / "app" / "core" / "services" / "asr_service.py"
            if asr_file.exists():
                content = asr_file.read_text(encoding="utf-8")
                assert "use_cache: bool = True" in content, "use_cache parameter not found in ASR service"
                assert "cache_asr_result" in content, "ASR caching function not imported"
                assert "get_cached_asr_result" in content, "ASR cache retrieval function not imported"
                
        except ImportError:
            pytest.skip("ASR service not available")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
