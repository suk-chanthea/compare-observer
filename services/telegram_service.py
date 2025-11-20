"""Telegram notification service"""
import requests
from utils.helpers import escape_markdown


class TelegramService:
    """Service for sending Telegram notifications"""
    
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.url = f'https://api.telegram.org/bot{token}/sendMessage'
    
    def send_message(self, username, description, file_list):
        """Send a message to Telegram with file changes"""
        DESCRIPTION = f"{username}: {description}"
        MESSAGE = escape_markdown(file_list)
        formatted_message = f"`{DESCRIPTION}` \n {MESSAGE}"
        
        params = {
            'chat_id': self.chat_id,
            'text': formatted_message,
            "parse_mode": "MarkdownV2",
        }
        
        response = requests.post(self.url, data=params)
        if response.status_code == 200:
            print("Message sent successfully!")
            return True
        else:
            print(f"Failed to send message. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False

