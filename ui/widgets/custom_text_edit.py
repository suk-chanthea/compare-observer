"""Custom text edit widget"""
from PyQt6.QtWidgets import QTextEdit


class CustomTextEdit(QTextEdit):
    """Text edit that strips formatting on paste"""
    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())  # Insert as plain text, removing formatting
        else:
            super().insertFromMimeData(source)

