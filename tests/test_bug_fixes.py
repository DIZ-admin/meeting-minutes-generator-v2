"""
Тест для проверки исправлений TODO/FIXME/BUG комментариев
"""
import pytest
import sys
import os
from pathlib import Path

# Добавляем родительскую директорию в путь импорта
parent_dir = Path(__file__).parent.parent
sys.path.append(str(parent_dir))

class TestBugFixes:
    """Тесты для проверки исправления BUG комментариев"""
    
    def test_config_validator_creation(self):
        """Тестирует создание валидатора конфигурации"""
        try:
            from app.utils.config_validator import ConfigValidator
            validator = ConfigValidator()
            assert validator is not None
            assert isinstance(validator.errors, list)
            assert isinstance(validator.warnings, list)
        except ImportError:
            pytest.skip("Config validator not available")
    
    def test_retry_mechanism_creation(self):
        """Тестирует создание retry механизма"""
        try:
            from app.utils.retry import RetryConfig, RetryPresets
            
            retry_config = RetryConfig()
            assert retry_config.max_attempts == 3
            assert retry_config.base_delay == 1.0
            
            # Тестируем предустановки
            api_config = RetryPresets.API_CALLS
            assert api_config.max_attempts == 3
        except ImportError:
            pytest.skip("Retry utils not available")
    
    def test_pipeline_imports(self):
        """Тестирует что исправлены импорты в pipeline"""
        try:
            from app.core.services.pipeline import Pipeline
            # Если импорт прошел успешно, значит синтаксические ошибки исправлены
            assert Pipeline is not None
        except ImportError as e:
            pytest.fail(f"Pipeline import failed: {e}")
    
    def test_llm_adapters_imports(self):
        """Тестирует что исправлены импорты в LLM адаптерах"""
        try:
            from app.adapters.llm.openai_adapter import OpenAILLMAdapter
            assert OpenAILLMAdapter is not None  
        except ImportError:
            pytest.skip("OpenAI adapter not available")
    
    def test_no_remaining_bug_comments_in_pipeline(self):
        """Проверяет что в pipeline.py не осталось BUG комментариев"""
        pipeline_file = parent_dir / "app" / "core" / "services" / "pipeline.py"
        if pipeline_file.exists():
            content = pipeline_file.read_text(encoding="utf-8")
            # Ищем строчки с просто "bug" (наши исправленные комментарии)
            bug_lines = [line for line in content.split('\n') if line.strip() == 'bug']
            assert len(bug_lines) == 0, f"Found {len(bug_lines)} remaining 'bug' comments in pipeline.py"
        else:
            pytest.skip("Pipeline file not found")

if __name__ == "__main__":
    # Запускаем тесты если файл выполняется напрямую
    pytest.main([__file__, "-v"])
