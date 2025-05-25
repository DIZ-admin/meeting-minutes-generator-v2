import os
import pathlib
import requests
from typing import Optional, Dict, Tuple, Union

# Constants for environment variables
TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"
TELEGRAM_PARSE_MODE_ENV = "TELEGRAM_PARSE_MODE"

# Default values
DEFAULT_PARSE_MODE = "Markdown"

class TelegramNotifierClient:
    """
    A client for sending notifications and files to a Telegram chat.
    """
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None, parse_mode: Optional[str] = None):
        """
        Initializes the TelegramNotifierClient.

        Args:
            token: The Telegram Bot Token. If None, tries to load from TELEGRAM_BOT_TOKEN env var.
            chat_id: The Telegram Chat ID. If None, tries to load from TELEGRAM_CHAT_ID env var.
            parse_mode: Default parse mode for messages (e.g., "Markdown", "HTML"). 
                        If None, tries to read from TELEGRAM_PARSE_MODE_ENV, then defaults to DEFAULT_PARSE_MODE.
        """
        self.token = token or os.getenv(TELEGRAM_BOT_TOKEN_ENV)
        self.chat_id = chat_id or os.getenv(TELEGRAM_CHAT_ID_ENV)
        self.parse_mode = parse_mode or os.getenv(TELEGRAM_PARSE_MODE_ENV) or DEFAULT_PARSE_MODE

        if self.token:
            self.api_url = f"https://api.telegram.org/bot{self.token}"
        else:
            self.api_url = None
            
        self.is_configured = bool(self.token and self.chat_id)
        
        if not self.is_configured:
            print("⚠️  TelegramNotifierClient: Token or Chat ID is not configured. Notifications will be skipped.")

    def _api_call(self, method: str, data: Optional[Dict] = None, files: Optional[Dict] = None) -> Dict:
        """
        Makes a POST request to the Telegram Bot API.

        Args:
            method: The API method name (e.g., 'sendMessage', 'sendDocument').
            data: Optional dictionary of data to send in the request body.
            files: Optional dictionary of files to send.

        Returns:
            A dictionary representing the JSON response from the API, or an error dict.
        """
        if not self.is_configured or not self.api_url:
            error_msg = "Telegram API call skipped: client not configured."
            print(f"Error: {error_msg}")
            return {"ok": False, "error_code": 400, "description": error_msg}
            
        url = f"{self.api_url}/{method}"
        try:
            response = requests.post(url, data=data, files=files, timeout=30)
            response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error calling Telegram API method {method}: {e}")
            return {"ok": False, "error_code": getattr(e.response, 'status_code', 500), "description": str(e)}

    def send_message(self, text: str, parse_mode: Optional[str] = None) -> bool:
        """
        Sends a text message to the configured chat.

        Args:
            text: The text of the message to send.
            parse_mode: Optional. Mode for parsing entities in the message text (e.g., 'Markdown', 'HTML').

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        if not self.is_configured:
            return False
        
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode if parse_mode is not None else self.parse_mode
        }
        response = self._api_call("sendMessage", data=payload)
        if response.get("ok"):
            print(f"✓ Message sent to Telegram chat {self.chat_id}")
            return True
        else:
            print(f"✗ Failed to send message: {response.get('description')}")
            return False

    def send_document(self, file_path: Union[str, pathlib.Path], caption: Optional[str] = None) -> bool:
        """
        Sends a document to the configured chat.

        Args:
            file_path: Path (string or pathlib.Path) to the document file to send.
            caption: Optional. Caption for the document.

        Returns:
            True if the document was sent successfully, False otherwise.
        """
        if not self.is_configured:
            print("Telegram client not configured. Skipping send document.")
            return False

        # Ensure file_path is a Path object
        file_path_obj = pathlib.Path(file_path)

        if not file_path_obj.exists() or not file_path_obj.is_file():
            print(f"❌ Failed to send document: File not found at path: {file_path_obj}")
            return False
        
        files = {'document': (file_path_obj.name, open(file_path_obj, 'rb'))}
        data = {
            "chat_id": self.chat_id,
            "parse_mode": self.parse_mode
        }
        if caption: # Add caption to data if provided
            data['caption'] = caption

        try:
            response_json = self._api_call("sendDocument", data=data, files=files)
            if response_json.get("ok"):
                print(f"📄 Document '{file_path_obj.name}' sent successfully.")
                return True
            else:
                error_desc = response_json.get('description', 'Unknown error')
                print(f"❌ Failed to send document: {error_desc}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to send document: {e}")
            return False
        finally:
            # Ensure the file is closed if it was opened
            if 'document' in files and hasattr(files['document'][1], 'close'):
                files['document'][1].close()

    def send_protocol_files(
        self, 
        md_path: pathlib.Path, 
        json_path: pathlib.Path, 
        notification_text_template: str = "✅ Protokoll ready: *{meeting_folder_name}*"
    ) -> bool:
        """
        Sends a notification message and then the protocol files (Markdown and JSON) to Telegram.

        Args:
            md_path: Path to the Markdown protocol file.
            json_path: Path to the JSON protocol file.
            notification_text_template: A template string for the notification message.
                                      Can use {meeting_folder_name} placeholder.

        Returns:
            True if all operations (message and both files) were successful, False otherwise.
        """
        if not self.is_configured:
            return False

        meeting_folder_name = md_path.parent.name
        message_text = notification_text_template.format(meeting_folder_name=meeting_folder_name)
        
        message_sent = self.send_message(message_text)
        if not message_sent:
            print("Skipping file sending due to message failure.")
            return False
        
        md_sent = self.send_document(md_path)
        json_sent = self.send_document(json_path)
        
        if md_sent and json_sent:
            print("✅ All protocol files sent to Telegram successfully")
            return True
        else:
            print("✗ Failed to send one or more protocol files to Telegram.")
            return False

def send_files(md_path: pathlib.Path, json_path: pathlib.Path) -> None:
    """
    Send meeting minutes files to Telegram chat using TelegramNotifierClient.
    This function is kept for backward compatibility.
    
    Args:
        md_path: Path to the markdown file
        json_path: Path to the JSON file
    """
    client = TelegramNotifierClient()
    if client.is_configured:
        client.send_protocol_files(md_path, json_path)
    else:
        # The client's __init__ already prints a warning, 
        # but we can add another one or rely on that.
        print("Telegram notifications skipped as client is not configured (from send_files function).")
