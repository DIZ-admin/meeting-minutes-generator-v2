import pytest
import os
import pathlib
import requests
from unittest.mock import MagicMock # Used for mocker.patch object side_effect

# Adjust the import path based on your project structure if needed
from scripts.telegram_notify import TelegramNotifierClient

# Define test constants for token and chat_id
TEST_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
TEST_CHAT_ID = "-1001234567890"

@pytest.fixture
def mock_env_vars(mocker):
    """Fixture to mock environment variables for Telegram credentials."""
    mocker.patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": TEST_TOKEN,
        "TELEGRAM_CHAT_ID": TEST_CHAT_ID
    })

@pytest.fixture
def mock_env_vars_missing(mocker):
    """Fixture to mock missing environment variables."""
    mocker.patch.dict(os.environ, {}, clear=True)
    # Ensure specific keys are not present if they were set by other tests/fixtures
    if "TELEGRAM_BOT_TOKEN" in os.environ:
        del os.environ["TELEGRAM_BOT_TOKEN"]
    if "TELEGRAM_CHAT_ID" in os.environ:
        del os.environ["TELEGRAM_CHAT_ID"]

# --- Test Initialization ---

def test_telegram_client_initialization_with_env_vars(mock_env_vars):
    client = TelegramNotifierClient()
    assert client.token == TEST_TOKEN
    assert client.chat_id == TEST_CHAT_ID
    assert client.api_url == f"https://api.telegram.org/bot{TEST_TOKEN}"
    assert client.is_configured is True

def test_telegram_client_initialization_with_direct_params(mock_env_vars_missing): # ensure env vars don't interfere
    direct_token = "direct_token"
    direct_chat_id = "direct_chat_id"
    client = TelegramNotifierClient(token=direct_token, chat_id=direct_chat_id)
    assert client.token == direct_token
    assert client.chat_id == direct_chat_id
    assert client.api_url == f"https://api.telegram.org/bot{direct_token}"
    assert client.is_configured is True

def test_telegram_client_initialization_token_missing(mock_env_vars_missing, mocker, capsys):
    mocker.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": TEST_CHAT_ID}, clear=True)
    if "TELEGRAM_BOT_TOKEN" in os.environ: del os.environ["TELEGRAM_BOT_TOKEN"]
    client = TelegramNotifierClient()
    assert client.token is None
    assert client.chat_id == TEST_CHAT_ID
    assert client.api_url is None
    assert client.is_configured is False
    captured = capsys.readouterr()
    assert "Token or Chat ID is not configured" in captured.out

def test_telegram_client_initialization_chat_id_missing(mock_env_vars_missing, mocker, capsys):
    mocker.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": TEST_TOKEN}, clear=True)
    if "TELEGRAM_CHAT_ID" in os.environ: del os.environ["TELEGRAM_CHAT_ID"]
    client = TelegramNotifierClient()
    assert client.token == TEST_TOKEN
    assert client.chat_id is None
    assert client.api_url == f"https://api.telegram.org/bot{TEST_TOKEN}" # api_url is set if token exists
    assert client.is_configured is False
    captured = capsys.readouterr()
    assert "Token or Chat ID is not configured" in captured.out

def test_telegram_client_initialization_all_missing(mock_env_vars_missing, capsys):
    client = TelegramNotifierClient()
    assert client.token is None
    assert client.chat_id is None
    assert client.api_url is None
    assert client.is_configured is False
    captured = capsys.readouterr()
    assert "Token or Chat ID is not configured" in captured.out

# --- Test send_message --- 

@pytest.fixture
def configured_client(mock_env_vars):
    """Provides a configured TelegramNotifierClient instance."""
    return TelegramNotifierClient()

@pytest.fixture
def unconfigured_client(mock_env_vars_missing):
    """Provides an unconfigured TelegramNotifierClient instance."""
    return TelegramNotifierClient()

def test_send_message_success(configured_client, mocker):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 123}}
    mocker.patch('requests.post', return_value=mock_response)
    
    success = configured_client.send_message("Hello, world!")
    
    assert success is True
    requests.post.assert_called_once()
    args, kwargs = requests.post.call_args
    assert args[0] == f"{configured_client.api_url}/sendMessage"
    assert kwargs['data'] == {
        "chat_id": configured_client.chat_id,
        "text": "Hello, world!",
        "parse_mode": "Markdown"
    }

def test_send_message_failure_api_error(configured_client, mocker, capsys):
    mock_response = MagicMock()
    mock_response.status_code = 400 # Simulate a client error
    mock_response.json.return_value = {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
    # Simulate the actual error object that would be raised
    http_error = requests.exceptions.HTTPError("400 Client Error: Bad Request for url", response=mock_response)
    mock_response.raise_for_status = MagicMock(side_effect=http_error)
    mocker.patch('requests.post', return_value=mock_response)
    
    success = configured_client.send_message("Test message")
    
    assert success is False
    requests.post.assert_called_once()
    captured = capsys.readouterr()
    # The actual error string from HTTPError will be in the log from _api_call
    assert "Error calling Telegram API method sendMessage: 400 Client Error: Bad Request for url" in captured.out
    # The message from the client logic will use the description from the JSON if available from the response attr of HTTPError
    assert "Failed to send message: 400 Client Error: Bad Request for url" in captured.out

def test_send_message_failure_network_error(configured_client, mocker, capsys):
    mocker.patch('requests.post', side_effect=requests.exceptions.ConnectionError("Network down"))
    
    success = configured_client.send_message("Test message")
    
    assert success is False
    requests.post.assert_called_once()
    captured = capsys.readouterr()
    assert "Failed to send message: Network down" in captured.out
    assert "Error calling Telegram API method sendMessage: Network down" in captured.out

def test_send_message_not_configured(unconfigured_client, mocker):
    mock_post = mocker.patch('requests.post') # To check it's not called
    success = unconfigured_client.send_message("Hello")
    assert success is False
    mock_post.assert_not_called()

# --- Test _api_call (indirectly, but good to have some direct if complex) ---

def test_api_call_skipped_if_not_configured(unconfigured_client, capsys):
    result = unconfigured_client._api_call("sendMessage", data={})
    assert result['ok'] is False
    assert "client not configured" in result['description']
    captured = capsys.readouterr()
    assert "Telegram API call skipped: client not configured" in captured.out

# --- Test send_document ---

@pytest.fixture
def temp_file(tmp_path):
    """Create a temporary file for testing file uploads."""
    file_path = tmp_path / "test_document.txt"
    file_path.write_text("This is a test document.")
    return file_path

def test_send_document_success(configured_client, mocker, temp_file):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 124}}
    mock_post = mocker.patch('requests.post', return_value=mock_response)
    
    success = configured_client.send_document(str(temp_file))
    
    assert success is True
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == f"{configured_client.api_url}/sendDocument"
    assert kwargs['data'] == {"chat_id": configured_client.chat_id, "parse_mode": "Markdown"}
    # Check that files payload is present and correctly structured
    assert 'files' in kwargs
    assert 'document' in kwargs['files']
    # kwargs['files']['document'] will be a tuple (filename, file_object, content_type)
    # We can check the filename part
    assert kwargs['files']['document'][0] == temp_file.name

def test_send_document_file_not_found(configured_client, mocker, capsys):
    mock_post = mocker.patch('requests.post') # To check it's not called if file not found early
    non_existent_file = "/tmp/this_file_does_not_exist_ever.txt"
    
    success = configured_client.send_document(non_existent_file)
    
    assert success is False
    mock_post.assert_not_called()
    captured = capsys.readouterr()
    assert f"Failed to send document: File not found at path: {non_existent_file}" in captured.out

def test_send_document_api_error(configured_client, mocker, temp_file, capsys):
    mock_response = MagicMock()
    mock_response.status_code = 403 # Simulate an auth error for example
    mock_response.json.return_value = {"ok": False, "error_code": 403, "description": "Forbidden: bot is not a member of the chat"}
    http_error = requests.exceptions.HTTPError("403 Client Error: Forbidden for url", response=mock_response)
    mock_response.raise_for_status = MagicMock(side_effect=http_error)
    mock_post = mocker.patch('requests.post', return_value=mock_response)

    success = configured_client.send_document(str(temp_file))

    assert success is False
    mock_post.assert_called_once() # API call should be attempted
    captured = capsys.readouterr()
    assert "Error calling Telegram API method sendDocument: 403 Client Error: Forbidden for url" in captured.out
    assert "Failed to send document: 403 Client Error: Forbidden for url" in captured.out

def test_send_document_network_error(configured_client, mocker, temp_file, capsys):
    mocker.patch('requests.post', side_effect=requests.exceptions.ConnectionError("Network fritz"))
    
    success = configured_client.send_document(str(temp_file))
    
    assert success is False
    requests.post.assert_called_once()
    captured = capsys.readouterr()
    assert "Error calling Telegram API method sendDocument: Network fritz" in captured.out
    assert "Failed to send document: Network fritz" in captured.out

def test_send_document_not_configured(unconfigured_client, mocker, temp_file):
    mock_post = mocker.patch('requests.post')
    success = unconfigured_client.send_document(str(temp_file))
    assert success is False
    mock_post.assert_not_called()
