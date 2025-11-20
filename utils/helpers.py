"""Helper utility functions"""
import re
from PyQt6.QtCore import QByteArray
from PyQt6.QtGui import QPixmap


def get_pixmap_from_base64(base64_string):
    """Convert Base64 string to QPixmap."""
    image_data = QByteArray.fromBase64(base64_string.encode("utf-8"))
    pixmap = QPixmap()
    pixmap.loadFromData(image_data)
    return pixmap


def escape_markdown(text):
    """Escape special characters for Telegram MarkdownV2"""
    special_chars = r'_\*\[\]\(\)~`>#+-=|{}.!'
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", text)

