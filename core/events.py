"""Custom events for file system changes"""
from PyQt6.QtCore import QEvent


class FileUpdateEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, table, file_path):
        super().__init__(self.EVENT_TYPE)
        self.table = table
        self.file_path = file_path


class FileCreateEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, table, file_path):
        super().__init__(self.EVENT_TYPE)
        self.table = table
        self.file_path = file_path
        print(f"DEBUG: FileCreateEvent created for {file_path}")  # Debug log


class FileDeleteEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, table, file_path):
        super().__init__(self.EVENT_TYPE)
        self.table = table
        self.file_path = file_path

