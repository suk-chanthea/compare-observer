"""File watcher table widget"""
import os
from PyQt6.QtWidgets import (QTableWidget, QTableWidgetItem, QPushButton, 
                            QHBoxLayout, QWidget)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QCursor, QIcon

from core.events import FileUpdateEvent, FileDeleteEvent
from utils.helpers import get_pixmap_from_base64
from config import DEBUG


class FileWatcherTable(QTableWidget):
    def __init__(self, folder_to_watch):
        super().__init__()
        self.folder_to_watch = folder_to_watch
        self.file_contents = {}  # Track old file content for diff {file_path: content}
        
        self.setColumnCount(2)  # Ensure only 2 columns
        self.setHorizontalHeaderLabels(["File Name", "Action"])
        self.verticalHeader().setDefaultSectionSize(30)  # Set row height to 30
        from PyQt6.QtWidgets import QHeaderView
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 100)  # Set the width of the second column
        self.setMinimumWidth(400)  # Ensure table doesn't shrink below a minimum width
        
        # Connect cell click to show diff
        self.cellClicked.connect(self.on_file_clicked)

    def on_file_clicked(self, row, column):
        """Handle file click to show diff dialog"""
        # Only trigger on file name column (column 0)
        if column != 0:
            return
        
        file_name = self.item(row, 0).text()
        # Normalize path to forward slashes to match stored baseline keys
        file_path = os.path.join(self.folder_to_watch, file_name).replace("\\", "/")
        
        # Get old content from cache (baseline from when Start was clicked)
        old_content = self.file_contents.get(file_path)
        
        if DEBUG:
            print(f"on_file_clicked: {file_path}")
            print(f"old_content found: {old_content is not None}")
        
        # Read current content
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                new_content = f.read()
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            new_content = None
        
        # Show chunk-by-chunk review dialog
        from ui.dialogs.chunk_review_dialog import ChunkReviewDialog
        dialog = ChunkReviewDialog(file_path, old_content, new_content, self)
        dialog.exec()
    
    def remove_button_row(self, button):
        # removeRow build-in, but overrite to see log
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, 1)
            if widget:
                button_inside = widget.findChild(QPushButton)
                if button_inside == button:
                    super().removeRow(row)
                    break

    def event(self, event):
        if isinstance(event, FileUpdateEvent):
            self.update_file(event.file_path)
            return True
        elif isinstance(event, FileDeleteEvent):  # File deleted
            self.remove_file(event.file_path)
            return True
    
        return super().event(event)

    def update_file(self, file_path):
        """Handle file update event - do not change stored old content"""
        if DEBUG:
            print(f"update_file FileWatcherTable={file_path}")

        file_name = os.path.relpath(file_path, self.folder_to_watch)
        
        # Check if file is already in table
        file_exists = False
        for row in range(self.rowCount()):
            if self.item(row, 0) and self.item(row, 0).text() == file_name:
                file_exists = True
                break
        
        # If file doesn't exist in table yet, add it (captures current content as baseline)
        if not file_exists:
            self.add_file(file_path)
        # If file already exists, do nothing - keep the original baseline content
        # The baseline was captured when scanning started in preload_file_hashes

    def add_file(self, file_path):
        """Add new file to table"""
        if DEBUG:
            print(f"add_file FileWatcherTable={file_path}")

        file_name = os.path.relpath(file_path, self.folder_to_watch)
        
        # Check if file is already added
        for row in range(self.rowCount()):
            if self.item(row, 0) and self.item(row, 0).text() == file_name:
                return
        
        # Store the current file content for diff comparison
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                self.file_contents[file_path] = f.read()
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            self.file_contents[file_path] = None
        
        row_position = self.rowCount()
        self.insertRow(row_position)
        self.setItem(row_position, 0, QTableWidgetItem(file_name))
        
        # Ensure column width remains fixed after adding a new row
        if self.rowCount() >= 10:
            self.setColumnWidth(0, 278)
        else:
            self.setColumnWidth(0, 286)  # Maintain column width for the first column
        
        self.setColumnWidth(1, 100)  # Maintain column width for the second column
        
        btn_remove = QPushButton()
        btn_remove.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        ICON_BASE64 = "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"
        btn_remove.setIcon(QIcon(get_pixmap_from_base64(ICON_BASE64)))
        btn_remove.setIconSize(QSize(20, 30))
        btn_remove.clicked.connect(lambda _, btn=btn_remove: self.remove_button_row(btn))  # Capture row index
        
        # Center button in cell
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)  # Remove padding
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Align center
        btn_layout.addWidget(btn_remove)
        cell_widget = QWidget()
        cell_widget.setLayout(btn_layout)
        
        self.setCellWidget(row_position, 1, cell_widget)

    def remove_file(self, file_path):
        # work when remove file from system
        file_name = os.path.relpath(file_path, self.folder_to_watch).strip()
        print(f"remove_file {file_name} from {self.rowCount()}")
        for row in range(self.rowCount()):
            if self.item(row, 0) and self.item(row, 0).text().strip() == file_name:
                self.removeRow(row)
                return  # Stop after removing the first match

