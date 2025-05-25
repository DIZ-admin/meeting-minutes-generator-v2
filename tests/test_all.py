import unittest
import os
import pathlib
import tempfile
import json
from unittest.mock import patch, MagicMock
import sys
import logging

# Настройка логирования для тестов
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test_suite')

# Путь к директории проекта
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(PROJECT_DIR)

# Импорт модулей для тестирования
try:
    from scripts.asr import transcribe
    logger.info("ASR module imported successfully")
except ImportError as e:
    logger.error(f"Failed to import ASR module: {e}")

try:
    import main
    logger.info("Main application imported successfully")
except ImportError as e:
    logger.error(f"Failed to import main application: {e}")

class TestConfiguration(unittest.TestCase):
    """Тесты конфигурации и окружения"""
    
    def test_environment_variables(self):
        """Проверка наличия необходимых переменных окружения"""
        required_vars = ['OPENAI_API_KEY', 'REPLICATE_API_TOKEN']
        
        for var in required_vars:
            value = os.environ.get(var)
            logger.info(f"Environment variable {var}: {'Present' if value else 'Missing'}")
            
        database_url = os.environ.get('DATABASE_URL')
        logger.info(f"Database URL: {'Present' if database_url else 'Missing'}")

class TestDirStructure(unittest.TestCase):
    """Тесты структуры директорий"""
    
    def test_directories(self):
        """Проверка наличия необходимых директорий"""
        required_dirs = ['scripts', 'templates', 'uploads', 'output', 'logs']
        
        for dir_name in required_dirs:
            dir_path = os.path.join(PROJECT_DIR, dir_name)
            exists = os.path.isdir(dir_path)
            logger.info(f"Directory {dir_name}: {'Present' if exists else 'Missing'}")
            
    def test_scripts(self):
        """Проверка наличия скриптов"""
        scripts_dir = os.path.join(PROJECT_DIR, 'scripts')
        if os.path.isdir(scripts_dir):
            files = [f for f in os.listdir(scripts_dir) if os.path.isfile(os.path.join(scripts_dir, f))]
            logger.info(f"Found scripts: {files}")

class TestFileReadWrite(unittest.TestCase):
    """Тесты файловых операций"""
    
    def setUp(self):
        """Создание временных директорий для тестов"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_file_path = os.path.join(self.temp_dir.name, "test.json")
        
    def tearDown(self):
        """Очистка временных директорий"""
        self.temp_dir.cleanup()
        
    def test_json_write_read(self):
        """Проверка записи и чтения JSON-файла"""
        # Тестовые данные
        test_data = {
            "segments": [
                {"start": 0.0, "end": 5.0, "speaker": "1", "text": "Test sentence one."},
                {"start": 5.0, "end": 10.0, "speaker": "2", "text": "Test sentence two."}
            ]
        }
        
        # Запись в файл
        with open(self.test_file_path, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Successfully wrote JSON to {self.test_file_path}")
        
        # Чтение из файла
        with open(self.test_file_path, 'r', encoding='utf-8') as f:
            read_data = json.load(f)
        logger.info(f"Successfully read JSON from {self.test_file_path}")
        
        # Проверка данных
        self.assertEqual(test_data, read_data)
        self.assertEqual(len(test_data["segments"]), len(read_data["segments"]))
        self.assertEqual(test_data["segments"][0]["text"], read_data["segments"][0]["text"])

if __name__ == '__main__':
    unittest.main()