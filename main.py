"""
Main Application Entry Point

NOTE: The FileWatcherApp class is very large (400+ lines).
For the complete clean architecture version:
1. Copy the FileWatcherApp class from compare_observer.py (lines 1435-1926)
2. Update imports to use the refactored modules below
3. OR continue using compare_observer.py as your main entry point

This file provides a template for the main application.
"""

import sys
from PyQt6.QtWidgets import QApplication

# Import from refactored modules
from config import API_URL, DEBUG
from core.models import FileChangeEntry
from services.file_watcher import WatcherThread
from services.telegram_service import TelegramService
from ui.dialogs.log_dialog import LogDialog
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.change_review_dialog import ChangeReviewDialog
from ui.dialogs.git_compare_dialog import GitSourceCompareDialog
from ui.widgets.file_watcher_table import FileWatcherTable
from ui.widgets.custom_text_edit import CustomTextEdit

# TODO: Copy FileWatcherApp class from compare_observer.py (lines 1435-1926)
# and update its imports to use the refactored modules above

# For now, import from the original file
try:
    from compare_observer import FileWatcherApp
except ImportError:
    print("Error: Please ensure compare_observer.py is in the same directory")
    print("Or copy the FileWatcherApp class to this file and update imports")
    sys.exit(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = FileWatcherApp()
    main_window.show()
    sys.exit(app.exec())

