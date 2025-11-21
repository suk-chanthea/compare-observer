import sys
import os
import hashlib
import shutil
import json
import time
import requests
import re
import threading
import subprocess

from PyQt6.QtWidgets import (QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QPushButton, QVBoxLayout, QWidget, QHBoxLayout, QHeaderView, 
    QDialog, QSizePolicy, QLabel, QTextEdit, QLineEdit, QGroupBox, QScrollArea, QTableView, QMessageBox, QCheckBox
)
from PyQt6.QtCore import QSettings, QThreadPool, QEvent, QObject, QCoreApplication, QAbstractTableModel, Qt, QSize,  QThread, pyqtSignal, QByteArray, QTimer, QModelIndex
from PyQt6.QtGui import QCursor, QPixmap, QIcon, QAction, QFont, QColor
import difflib

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
#from functools import partial

API_URL = "http://khmergaming.436bet.com/app/"
DEBUG = False

class WatcherThread(QThread):
    started_watching = pyqtSignal()
    stopped_watching = pyqtSignal()
    preload_complete = pyqtSignal()  # Signal to notify when preload is complete
    # all_preload_complete = pyqtSignal()

    def __init__(self, table_index, table, path, excluded_folders, excluded_files, dialog):
        super().__init__()
        self.table = table
        self.path = path
        self.excluded_folders = excluded_folders
        self.excluded_files = excluded_files
        self.dialog = dialog
        self.table_index = table_index

        self.observer = Observer()
        self._running = False

    def run(self):
        self._running = True
        self.event_handler = FileEventHandler(self.table, self.path, self.excluded_folders, self.excluded_files, self.dialog)

        # IMPORTANT: Preload file hashes and capture baseline BEFORE starting observer
        # This ensures we save the current file state as "old code" before watching for changes
        self.event_handler.preload_file_hashes(self.table_index)
        
        # Mark preload as complete
        self.event_handler.preload_complete = True

        # Emit signal after preloading is complete
        self.preload_complete.emit()  # Notify that file preloading is finished
        # self.all_preload_complete.emit()
        
        # NOW start the observer to watch for new changes
        self.observer.schedule(self.event_handler, self.path, recursive=True)
        self.observer.start()
        
        # Emit started_watching signal after everything is ready
        self.started_watching.emit()

        try:
            while self._running:
                self.msleep(300)  # Prevent blocking GUI
        except Exception as e:
            print(f"Exception in WatcherThread: {e}")
        finally:
            self.stop_observer()  # Ensure observer is properly stopped
            self.stopped_watching.emit()

    def stop(self):
        self._running = False
        self.event_handler.stopp_reload_file_hashes()
        self.stop_observer()
        self.quit()  # Ensures thread exits properly
        self.wait()  # Waits for thread to finish

    def stop_observer(self):
        if self.observer.is_alive():  # Check if observer is still running
            self.observer.stop()
            self.observer.join()
            print("Observer stopped.")


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
class CustomTextEdit(QTextEdit):
    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())  # Insert as plain text, removing formatting
        else:
            super().insertFromMimeData(source)

class LogTableModel(QAbstractTableModel):
    """ Efficient model for handling large log files in QTableView """
    def __init__(self, log_file=None):
        super().__init__()
        self.log_file = log_file
        self.lines = []  # Initialize with an empty list
        if log_file:
            self.load_lines()

    def load_lines(self):
        """ Loads only line references (not full file) for efficiency """
        with open(self.log_file, "r", encoding="utf-8") as f:
            self.lines = f.readlines()  # Load lines from the file
        self.layoutChanged.emit()  # Notify the view that the data has changed

    def rowCount(self, parent=None):
        return len(self.lines)

    def columnCount(self, parent=None):
        return 1  # One column for log text

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            return self.lines[index.row()].strip()  # Return log text without extra spaces
        return None

    def append_row(self, new_line):
        """ Append a new row to the model """
        QIndex = QModelIndex()  
        self.beginInsertRows(QIndex, len(self.lines), len(self.lines))  # Notify about row insertion
        self.lines.append(new_line + "\n")  # Add the new line to the data
        self.endInsertRows()  # End the row insertion process

class LogDialog(QDialog):
    """Popup window for file scanning logs."""
    
    add_log_signal = pyqtSignal(str)  # Signal to update the table safely from another thread
    upt_log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scanning files...")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.layout = QVBoxLayout(self)

        self.row_layout_user = QHBoxLayout()

        self.user_label_name = QLabel("Scanning files:", self)
        self.user_label_name.setStyleSheet("color: #E0E0E0; font-size: 12px;")
        self.user_input_name = QLineEdit(self)
        self.user_input_name.setFixedHeight(30)
        self.user_input_name.setReadOnly(True)
        self.user_input_name.setStyleSheet("""
            QLineEdit {
                background-color: #3C3C3C;
                color: #E0E0E0;
                border: 2px solid #5A5A5A;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #1976D2;
                border-radius: 6px;
            }
        """)

        self.row_layout_user.addWidget(self.user_label_name)
        self.row_layout_user.addWidget(self.user_input_name)
        self.layout.addLayout(self.row_layout_user)

        # Table for logs
        self.table = QTableView()
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        self.table.resizeRowsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

        # Initialize the model
        self.model = LogTableModel()
        self.table.setModel(self.model)
        self.layout.addWidget(self.table)

        # Connect the signal to update the UI safely
        self.add_log_signal.connect(self.model.append_row)
        self.upt_log_signal.connect(self.setText)

    def setLog(self, text):
        """Safely update the table model from another thread."""
        self.add_log_signal.emit(text)  # Emit signal to safely update table

    def setText(self, text):
        self.user_input_name.setText(text)

class FileChangeEntry:
    """Represents a single file change with its content and metadata"""
    def __init__(self, file_path, old_content, new_content, source_root):
        self.file_path = file_path
        self.old_content = old_content
        self.new_content = new_content
        self.source_root = source_root
        self.relative_path = os.path.relpath(file_path, source_root)
        self.is_selected = True
        
    def get_diff_lines(self):
        """Generate diff lines for display"""
        if self.old_content is None:
            return [f"+ {line}" for line in self.new_content.splitlines()]
        elif self.new_content is None:
            return [f"- {line}" for line in self.old_content.splitlines()]
        else:
            old_lines = self.old_content.splitlines()
            new_lines = self.new_content.splitlines()
            diff = difflib.unified_diff(old_lines, new_lines, lineterm='')
            return list(diff)[2:]  # Skip the file header lines

class GitSourceCompareDialog(QDialog):
    """Dialog to compare files between Git path and Source path"""
    def __init__(self, git_path, source_path, backup_path="", without_paths=None, except_paths=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Git to Source Comparison")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(700)
        # Enable window resizing with minimize and maximize buttons
        self.setWindowFlags(Qt.WindowType.Window | 
                          Qt.WindowType.WindowMinimizeButtonHint | 
                          Qt.WindowType.WindowMaximizeButtonHint | 
                          Qt.WindowType.WindowCloseButtonHint)
        self.setSizeGripEnabled(True)
        self.git_path = git_path
        self.source_path = source_path
        self.backup_path = backup_path
        self.without_paths = [self._normalize_path(p) for p in (without_paths or []) if p]
        self.except_paths = [self._normalize_path(p) for p in (except_paths or []) if p]
        
        layout = QVBoxLayout(self)
        
        # Info label
        info_layout = QHBoxLayout()
        info_label = QLabel(f"Comparing Git: {git_path} <-> Source: {source_path}")
        info_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        info_layout.addWidget(info_label)
        
        # Scan button
        scan_btn = QPushButton("Scan for Changes")
        scan_btn.clicked.connect(self.scan_changes)
        info_layout.addWidget(scan_btn)
        
        layout.addLayout(info_layout)
        
        # Filter info label
        filter_info = []
        if self.without_paths:
            filter_info.append(f"Without: {', '.join(self.without_paths[:3])}" + ("..." if len(self.without_paths) > 3 else ""))
        if self.except_paths:
            filter_info.append(f"Except: {len(self.except_paths)} path(s)")
        if filter_info:
            filter_label = QLabel("🔍 Filters: " + " | ".join(filter_info))
            filter_label.setStyleSheet("font-size: 11px; color: #888888; padding: 5px;")
            filter_label.setToolTip(f"Without paths: {', '.join(self.without_paths)}\nExcept paths: {', '.join(self.except_paths)}")
            layout.addWidget(filter_label)
        
        # File list table
        self.file_list = QTableWidget()
        self.file_list.setColumnCount(3)
        self.file_list.setHorizontalHeaderLabels(["File Path", "Status", "Action"])
        self.file_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_list.setColumnWidth(1, 150)  # Status column width
        self.file_list.setColumnWidth(2, 140)  # Action column width - ensure button is visible
        self.file_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_list.verticalHeader().setDefaultSectionSize(36)  # Larger row height
        self.file_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Remove dotted focus border
        self.file_list.setStyleSheet("""
            QTableWidget::item:focus {
                outline: none;
                border: none;
            }
        """)
        layout.addWidget(self.file_list)
        
        # Status label
        self.status_label = QLabel("Click 'Scan for Changes' to start")
        layout.addWidget(self.status_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.copy_to_source_btn = QPushButton("Copy Selected to Source")
        self.copy_to_source_btn.clicked.connect(self.copy_to_source)
        self.copy_to_source_btn.setEnabled(False)
        btn_layout.addWidget(self.copy_to_source_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        self.changes = []

    def _normalize_path(self, path):
        return path.replace("\\", "/").strip("/")
    
    def _safe_relpath(self, path, start):
        """Safely compute relative path, handling cross-mount scenarios"""
        try:
            return os.path.relpath(path, start)
        except ValueError:
            # Paths are on different mounts - compute relative path manually
            # Normalize both paths
            path_norm = os.path.normpath(path)
            start_norm = os.path.normpath(start)
            
            # If they're absolute paths, try to find common prefix
            if os.path.isabs(path_norm) and os.path.isabs(start_norm):
                # Get drive/root info
                path_drive = os.path.splitdrive(path_norm)[0]
                start_drive = os.path.splitdrive(start_norm)[0]
                
                # If different drives/mounts, can't compute relative path
                if path_drive != start_drive and path_drive and start_drive:
                    # Return just the filename as fallback
                    return os.path.basename(path_norm)
            
            # Fallback: just return the basename
            return os.path.basename(path_norm)

    def _join_rel_paths(self, base, child):
        base_normalized = self._normalize_path(base)
        child_normalized = self._normalize_path(child)
        if not base_normalized:
            return child_normalized
        if not child_normalized:
            return base_normalized
        return f"{base_normalized}/{child_normalized}"

    def _is_excluded(self, rel_path):
        """Check if path should be excluded based on common system files and user-defined exceptions"""
        normalized = self._normalize_path(rel_path)
        
        # Always exclude common system files
        if normalized.startswith('.git/') or normalized == '.git':
            return True
        if normalized.startswith('__pycache__/') or normalized == '__pycache__':
            return True
        if '.DS_Store' in normalized or 'Thumbs.db' in normalized:
            return True
        
        # Check user-defined exceptions (respect app settings)
        for pattern in self.except_paths:
            if normalized == pattern or normalized.startswith(f"{pattern}/"):
                return True
        
        return False

    def _matches_without_dir(self, rel_path):
        normalized = self._normalize_path(rel_path)
        for directory in self.without_paths:
            if normalized.startswith(directory):
                return directory
        return None

    def _resolve_source_path_from_git(self, git_rel_path):
        """Map a file from Git (which may be flattened) to the expected source path."""
        normalized = self._normalize_path(git_rel_path)
        display_rel = normalized
        source_file = os.path.join(self.source_path, normalized.replace("/", os.sep))

        # If file exists directly, use it
        if os.path.exists(source_file):
            return display_rel, source_file

        basename = os.path.basename(normalized)
        # Try to map flattened files using 'without' directories
        for directory in self.without_paths:
            candidate_rel = self._normalize_path(os.path.join(directory, basename))
            candidate_file = os.path.join(self.source_path, candidate_rel.replace("/", os.sep))
            if os.path.exists(candidate_file):
                return candidate_rel, candidate_file

        # If still not found but without paths exist, default to first directory for new files
        if self.without_paths:
            candidate_rel = self._normalize_path(os.path.join(self.without_paths[0], basename))
            candidate_file = os.path.join(self.source_path, candidate_rel.replace("/", os.sep))
            return candidate_rel, candidate_file

        return display_rel, source_file

    def _resolve_git_path_from_source(self, source_rel_path):
        """Determine where a source file should live inside the Git directory."""
        normalized = self._normalize_path(source_rel_path)
        matched_dir = self._matches_without_dir(normalized)
        if matched_dir:
            basename = os.path.basename(normalized)
            git_rel = basename  # Flattened path
        else:
            git_rel = normalized
        git_file = os.path.join(self.git_path, git_rel.replace("/", os.sep))
        return git_rel, git_file
    
    def _check_path_access(self, path, path_name="Path"):
        """Check if a path is accessible, with retry logic for network shares"""
        import time
        
        # Check if it's a network share
        is_network = path.startswith('\\\\') or path.startswith('//')
        
        if is_network:
            self.status_label.setText(f"Checking network access: {path_name}...")
            QApplication.processEvents()  # Update UI
        
        # Try multiple times for network shares (they can be slow to respond)
        max_retries = 3 if is_network else 1
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                if os.path.exists(path):
                    return True, None
                else:
                    if attempt < max_retries - 1:
                        if is_network:
                            self.status_label.setText(f"Retrying network access ({attempt + 1}/{max_retries})...")
                            QApplication.processEvents()
                            time.sleep(retry_delay)
                            continue
            except (OSError, PermissionError, TimeoutError) as e:
                error_msg = str(e)
                if attempt < max_retries - 1:
                    if is_network:
                        self.status_label.setText(f"Network error, retrying ({attempt + 1}/{max_retries})...")
                        QApplication.processEvents()
                        time.sleep(retry_delay)
                        continue
                    else:
                        return False, error_msg
                else:
                    return False, error_msg
            except Exception as e:
                return False, f"Unexpected error: {str(e)}"
        
        # Path doesn't exist after retries
        if is_network:
            return False, f"Network path not accessible or timed out after {max_retries} attempts"
        else:
            return False, "Path does not exist"
    
    def _normalize_file_content(self, file_path):
        """Normalize file content for comparison - handles line endings, encoding, etc."""
        try:
            # Try reading as text first
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # Normalize line endings to LF
            content = content.replace('\r\n', '\n').replace('\r', '\n')
            # Strip trailing whitespace from each line
            content = '\n'.join(line.rstrip() for line in content.split('\n'))
            # Remove trailing newlines at end of file
            content = content.rstrip('\n')
            return content.encode('utf-8')
        except Exception:
            # If text reading fails, read as binary
            with open(file_path, 'rb') as f:
                return f.read()

    # Add this method to GitSourceCompareDialog class
    def scan_changes(self):
        """Scan for differences between Git and Source paths"""
        # Check Git path access with retry logic
        git_accessible, git_error = self._check_path_access(self.git_path, "Git path")
        if not git_accessible:
            error_msg = f"Git path is not accessible:\n{self.git_path}\n\n"
            if git_error:
                error_msg += f"Error: {git_error}\n\n"
            error_msg += "Possible issues:\n"
            error_msg += "- Network share is offline or unreachable\n"
            error_msg += "- Invalid credentials or permissions\n"
            error_msg += "- Network timeout\n"
            error_msg += "- Path format incorrect"
            QMessageBox.warning(self, "Git Path Error", error_msg)
            self.status_label.setText(f"❌ Git path not accessible: {git_error or 'Path not found'}")
            return
        
        # Check Source path access with retry logic
        source_accessible, source_error = self._check_path_access(self.source_path, "Source path")
        if not source_accessible:
            error_msg = f"Source path is not accessible:\n{self.source_path}\n\n"
            if source_error:
                error_msg += f"Error: {source_error}\n\n"
            error_msg += "Possible issues:\n"
            error_msg += "- Network share is offline or unreachable\n"
            error_msg += "- Invalid credentials or permissions\n"
            error_msg += "- Network timeout\n"
            error_msg += "- Path format incorrect"
            QMessageBox.warning(self, "Source Path Error", error_msg)
            self.status_label.setText(f"❌ Source path not accessible: {source_error or 'Path not found'}")
            return
        
        self.status_label.setText("Scanning...")
        self.file_list.setRowCount(0)
        self.changes.clear()
        
        # Compare files (Git -> Source) - Respect user-defined filters from app settings
        processed_files = set()  # Track processed files to avoid duplicates
        try:
            for root, dirs, files in os.walk(self.git_path):
                try:
                    rel_dir = self._normalize_path(self._safe_relpath(root, self.git_path))
                    if rel_dir == ".":
                        rel_dir = ""
                    
                    # Filter directories based on user settings (respect except_paths)
                    dirs[:] = [
                        d for d in dirs
                        if d != '.git' and not self._is_excluded(self._join_rel_paths(rel_dir, d))
                    ]
                    
                    for file in files:
                        try:
                            git_file = os.path.join(root, file)
                            git_rel_path = self._normalize_path(self._safe_relpath(git_file, self.git_path))

                            # Skip files that match user-defined exceptions or system files
                            if self._is_excluded(git_rel_path):
                                continue
                            
                            # Check if already processed
                            if git_rel_path in processed_files:
                                continue
                            processed_files.add(git_rel_path)

                            # Resolve source path (respect without_paths for flattening)
                            display_rel_path, source_file = self._resolve_source_path_from_git(git_rel_path)
                            
                            status = ""
                            try:
                                if not os.path.exists(source_file) or not os.path.isfile(source_file):
                                    status = "New in Git"
                                else:
                                    # Compare file contents - only show if files are DIFFERENT
                                    try:
                                        # Read as binary for accurate comparison
                                        with open(git_file, 'rb') as f1:
                                            git_content = f1.read()
                                        with open(source_file, 'rb') as f2:
                                            source_content = f2.read()
                                        
                                        # Compare content directly - if identical, skip (don't add to changes)
                                        if git_content != source_content:
                                            status = "Modified"
                                    except (OSError, PermissionError, TimeoutError) as e:
                                        status = f"Error reading: {str(e)[:50]}"
                                    except Exception as e:
                                        status = f"Error: {str(e)[:50]}"
                            except Exception as e:
                                status = f"Path error: {str(e)[:50]}"
                            
                            # Only add to changes if there's a status (file is different or missing)
                            # Identical files (same content) are skipped - they won't appear in the list
                            if status:
                                self.add_change_to_list(display_rel_path, status, git_file, source_file, git_rel_path)
                        except (OSError, PermissionError, TimeoutError) as e:
                            # Network error accessing file, skip and continue
                            self.status_label.setText(f"⚠️ Network issue accessing file: {file[:30]}...")
                            QApplication.processEvents()
                            continue
                except (OSError, PermissionError, TimeoutError) as e:
                    # Network error accessing directory, skip and continue
                    self.status_label.setText(f"⚠️ Network issue accessing directory...")
                    QApplication.processEvents()
                    continue
        except (OSError, PermissionError, TimeoutError) as e:
            error_msg = f"Network error while scanning Git path:\n{self.git_path}\n\nError: {str(e)}\n\n"
            error_msg += "The network share may have become unresponsive during scanning."
            QMessageBox.warning(self, "Network Error - Git Path", error_msg)
            self.status_label.setText(f"❌ Network error: {str(e)[:50]}")
            return
        
        # Check for files in source but not in git - Respect user-defined filters from app settings
        try:
            for root, dirs, files in os.walk(self.source_path):
                try:
                    rel_dir = self._normalize_path(self._safe_relpath(root, self.source_path))
                    if rel_dir == ".":
                        rel_dir = ""
                    
                    # Filter directories based on user settings (respect except_paths and without_paths)
                    dirs[:] = [
                        d for d in dirs
                        if d != '.git'
                        and not self._is_excluded(self._join_rel_paths(rel_dir, d))
                        and not self._matches_without_dir(self._join_rel_paths(rel_dir, d))
                    ]
                    
                    for file in files:
                        try:
                            source_file = os.path.join(root, file)
                            rel_path = self._normalize_path(self._safe_relpath(source_file, self.source_path))

                            # Skip files that match user-defined exceptions or system files
                            if self._is_excluded(rel_path):
                                continue
                            
                            # Skip files in without_paths directories (they're flattened)
                            if self._matches_without_dir(rel_path):
                                continue
                            
                            # Check if already processed
                            if rel_path in processed_files:
                                continue
                            processed_files.add(rel_path)
                            
                            # Resolve git path (respect without_paths for flattening)
                            git_rel_path, git_file = self._resolve_git_path_from_source(rel_path)
                            
                            try:
                                if not os.path.exists(git_file) or not os.path.isfile(git_file):
                                    self.add_change_to_list(rel_path, "Only in Source", git_file, source_file, git_rel_path)
                            except (OSError, PermissionError, TimeoutError) as e:
                                # Network error checking file, skip and continue
                                continue
                        except (OSError, PermissionError, TimeoutError) as e:
                            # Network error accessing file, skip and continue
                            continue
                except (OSError, PermissionError, TimeoutError) as e:
                    # Network error accessing directory, skip and continue
                    continue
        except (OSError, PermissionError, TimeoutError) as e:
            error_msg = f"Network error while scanning Source path:\n{self.source_path}\n\nError: {str(e)}\n\n"
            error_msg += "The network share may have become unresponsive during scanning."
            QMessageBox.warning(self, "Network Error - Source Path", error_msg)
            self.status_label.setText(f"❌ Network error: {str(e)[:50]}")
            return
        
        # Show final status - show filters if active
        filter_info = []
        if self.except_paths:
            filter_info.append(f"{len(self.except_paths)} except path(s)")
        if self.without_paths:
            filter_info.append(f"{len(self.without_paths)} without path(s)")
        
        status_text = f"✅ Found {len(self.changes)} difference(s)"
        if filter_info:
            status_text += f" (Filters active: {', '.join(filter_info)})"
        self.status_label.setText(status_text)
        self.copy_to_source_btn.setEnabled(len(self.changes) > 0)
    
    def add_change_to_list(self, display_path, status, git_file, source_file, git_rel_path):
        """Add a detected change to the list widget"""
        self.changes.append({
            'display_path': display_path,
            'status': status,
            'git_file': git_file,
            'source_file': source_file,
            'git_rel_path': git_rel_path
        })
        
        row = self.file_list.rowCount()
        self.file_list.insertRow(row)
        
        # File path
        path_item = QTableWidgetItem(display_path)
        path_item.setFlags(path_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        path_item.setCheckState(Qt.CheckState.Checked)
        self.file_list.setItem(row, 0, path_item)
        
        # Status
        status_item = QTableWidgetItem(status)
        if status == "Modified":
            status_item.setForeground(QColor(255, 165, 0))  # Orange
        elif status == "New in Git":
            status_item.setForeground(QColor(0, 200, 0))  # Green
        elif status == "Only in Source":
            status_item.setForeground(QColor(255, 0, 0))  # Red
        elif "Error" in status:
            status_item.setForeground(QColor(200, 0, 0))  # Dark red
        self.file_list.setItem(row, 1, status_item)
        
        # Action button (View & Apply) - compact size, smaller than row height
        if status == "Only in Source":
            btn_text = "👁️ View"
            btn_tooltip = "View source file (file doesn't exist in git)"
        else:
            btn_text = "👁️ View & Apply"
            btn_tooltip = "View differences and apply changes from git"
        
        view_btn = QPushButton(btn_text)
        view_btn.setToolTip(btn_tooltip)
        view_btn.setFixedHeight(24)  # Fixed small height, smaller than row
        view_btn.setStyleSheet("""
            QPushButton {
                padding: 0px 6px;
                font-size: 11px;
                border-radius: 3px;
            }
        """)
        view_btn.clicked.connect(lambda checked, g=git_file, s=source_file: self.view_diff(g, s))
        self.file_list.setCellWidget(row, 2, view_btn)
        
    def view_diff(self, git_file, source_file):
        """View line-by-line diff between git and source with individual chunk control"""
        try:
            # Read source content (old/current)
            if os.path.exists(source_file):
                with open(source_file, 'r', encoding='utf-8', errors='ignore') as f:
                    source_content = f.read()
            else:
                source_content = ""
            
            # Read git content (new/from git)
            if os.path.exists(git_file):
                with open(git_file, 'r', encoding='utf-8', errors='ignore') as f:
                    git_content = f.read()
            else:
                git_content = ""
            
            # Check if there are differences
            if source_content == git_content:
                QMessageBox.information(
                    self,
                    "No Differences",
                    "Files are identical. No changes to apply."
                )
                return
            
            # Import ChunkReviewDialog
            from ui.dialogs.chunk_review_dialog import ChunkReviewDialog
            
            # Use ChunkReviewDialog for line-by-line control
            # old_content = source (current), new_content = git (to apply)
            dialog = ChunkReviewDialog(source_file, source_content, git_content, self)
            dialog.setWindowTitle(f"Git → Source - {os.path.basename(source_file)}")
            
            # Update info label to clarify direction
            dialog.info_label.setText(
                "💡 Review each change chunk. ◀ = Apply from Git | ▶ = Keep Source. Click 'Apply Selected Changes' when done."
            )
            
            result = dialog.exec()
            
            if result:
                # Dialog accepted - changes were applied to source file
                self.status_label.setText(f"✅ Changes applied to {os.path.basename(source_file)}")
                # Rescan to update the list
                self.scan_changes()
            else:
                # Dialog cancelled - no changes made
                self.status_label.setText(f"❌ No changes applied to {os.path.basename(source_file)}")
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error reading files: {e}")
    
    def copy_to_source(self):
        """Copy selected files from Git to Source"""
        selected_rows = set(item.row() for item in self.file_list.selectedItems())
        
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select files to copy")
            return
        
        # Create backup folder with date-time if backup path is configured
        backup_folder = None
        if self.backup_path and os.path.exists(self.backup_path):
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_folder = os.path.join(self.backup_path, timestamp)
            try:
                os.makedirs(backup_folder, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Backup Error", f"Could not create backup folder: {e}")
                backup_folder = None
        
        copied_count = 0
        backed_up_count = 0
        for row in selected_rows:
            change = self.changes[row]
            if change['status'] != "Only in Source":
                try:
                    # Backup existing file if it exists and backup is configured
                    if backup_folder and os.path.exists(change['source_file']):
                        backup_file = os.path.join(backup_folder, change['rel_path'])
                        os.makedirs(os.path.dirname(backup_file), exist_ok=True)
                        shutil.copy2(change['source_file'], backup_file)
                        backed_up_count += 1
                    
                    # Create directory if needed
                    os.makedirs(os.path.dirname(change['source_file']), exist_ok=True)
                    # Copy file
                    shutil.copy2(change['git_file'], change['source_file'])
                    copied_count += 1
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Error copying {change['rel_path']}: {e}")
        
        msg = f"Copied {copied_count} file(s) to source"
        if backed_up_count > 0:
            msg += f"\nBacked up {backed_up_count} file(s) to {backup_folder}"
        QMessageBox.information(self, "Success", msg)
        self.scan_changes()  # Refresh the list

class FileDiffDialog(QDialog):
    """Dialog to view old code vs new code comparison for a single file"""
    def __init__(self, file_path, old_content, new_content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"File Comparison - {os.path.basename(file_path)}")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(600)
        # Enable window resizing with minimize and maximize buttons
        self.setWindowFlags(Qt.WindowType.Window | 
                          Qt.WindowType.WindowMinimizeButtonHint | 
                          Qt.WindowType.WindowMaximizeButtonHint | 
                          Qt.WindowType.WindowCloseButtonHint)
        self.setSizeGripEnabled(True)
        self.old_content = old_content
        self.new_content = new_content
        self.file_path = file_path
        
        layout = QVBoxLayout(self)
        
        # Top bar with filename (not full path)
        top_bar = QHBoxLayout()
        filename = os.path.basename(file_path)
        path_label = QLabel(f"📄 File: {filename}")
        path_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #569cd6;")
        path_label.setToolTip(file_path)  # Show full path on hover
        top_bar.addWidget(path_label)
        top_bar.addStretch()
        
        layout.addLayout(top_bar)
        
        # Create side-by-side comparison
        comparison_layout = QHBoxLayout()
        
        # Old content panel
        self.old_panel = QGroupBox("Old Code")
        old_layout = QVBoxLayout()
        self.old_text = QTextEdit()
        self.old_text.setReadOnly(True)
        self.old_text.setFont(QFont("Consolas", 10))  # Better IDE font
        self.old_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
                padding: 5px;
            }
        """)
        if old_content is None:
            self.old_text.setHtml("<span style='color: #858585; font-style: italic;'>[File did not exist]</span>")
        else:
            self.old_text.setHtml(self._highlight_content(old_content, new_content, is_old=True))
        old_layout.addWidget(self.old_text)
        self.old_panel.setLayout(old_layout)
        comparison_layout.addWidget(self.old_panel)
        
        # Connect scrollbars for synchronized scrolling
        old_scrollbar = self.old_text.verticalScrollBar()
        
        # Middle panel with arrow buttons - smaller and follow changes
        middle_panel = QWidget()
        middle_layout = QVBoxLayout(middle_panel)
        middle_layout.setSpacing(5)
        middle_layout.addStretch()
        
        # Arrow left button - Accept new changes
        self.arrow_left_btn = QPushButton("◄")
        self.arrow_left_btn.setFixedSize(30, 25)
        self.arrow_left_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.arrow_left_btn.clicked.connect(self.select_new_change)
        self.arrow_left_btn.setToolTip("Accept New Code - Keep changes (including your comments)")
        middle_layout.addWidget(self.arrow_left_btn)
        
        middle_layout.addSpacing(10)
        
        # Arrow right button - Revert to old
        self.arrow_right_btn = QPushButton("►")
        self.arrow_right_btn.setFixedSize(30, 25)
        self.arrow_right_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.arrow_right_btn.clicked.connect(self.select_old_version)
        self.arrow_right_btn.setToolTip("Revert to Old Code - Discard all new changes")
        middle_layout.addWidget(self.arrow_right_btn)
        
        middle_layout.addStretch()
        comparison_layout.addWidget(middle_panel)
        
        # New content panel
        self.new_panel = QGroupBox("New Code (Current)")
        new_layout = QVBoxLayout()
        self.new_text = QTextEdit()
        self.new_text.setReadOnly(True)
        self.new_text.setFont(QFont("Consolas", 10))  # Better IDE font
        self.new_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
                padding: 5px;
            }
        """)
        if new_content is None:
            self.new_text.setHtml("<span style='color: #858585; font-style: italic;'>[File was deleted]</span>")
        else:
            self.new_text.setHtml(self._highlight_content(new_content, old_content, is_old=False))
        new_layout.addWidget(self.new_text)
        self.new_panel.setLayout(new_layout)
        comparison_layout.addWidget(self.new_panel)
        
        # Connect scrollbars for synchronized scrolling
        new_scrollbar = self.new_text.verticalScrollBar()
        old_scrollbar.valueChanged.connect(new_scrollbar.setValue)
        new_scrollbar.valueChanged.connect(old_scrollbar.setValue)
        
        layout.addLayout(comparison_layout)
        
        # Bottom button layout with close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
    
    def _highlight_content(self, content, other_content, is_old=True):
        """Highlight differences between two contents with colors and line numbers (IDE-style)"""
        if content is None or other_content is None:
            # If one file doesn't exist, show as is with line numbers
            if content:
                lines = content.split('\n')
                html_lines = []
                for line_num, line in enumerate(lines, 1):
                    escaped = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    if is_old:
                        bg_color = '#4b1818'  # Dark red for deleted file
                    else:
                        bg_color = '#1a4b1a'  # Dark green for new file
                    html_lines.append(
                        f'<div style="background-color: {bg_color}; padding: 2px 0;">'
                        f'<span style="color: #858585; user-select: none; padding: 0 10px; min-width: 50px; display: inline-block; text-align: right; border-right: 1px solid #3e3e3e; margin-right: 10px;">{line_num}</span>'
                        f'<span style="color: #d4d4d4;">{escaped if escaped else "&nbsp;"}</span>'
                        f'</div>'
                    )
                return '<div style="margin: 0; font-family: Consolas, monospace; font-size: 10pt; line-height: 1.6;">' + ''.join(html_lines) + '</div>'
            return content
        
        # Split into lines for comparison
        content_lines = content.split('\n')
        other_lines = other_content.split('\n')
        
        # Use difflib to get differences
        import difflib
        diff = difflib.ndiff(content_lines if is_old else other_lines, 
                            other_lines if is_old else content_lines)
        
        html_lines = []
        line_num = 0
        for line in diff:
            # Escape HTML characters but preserve tabs
            escaped = line[2:].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\t', '    ')
            
            if line.startswith('- ') and is_old:
                # Line removed (only show in old) - dark red background
                line_num += 1
                html_lines.append(
                    f'<div style="background-color: #4b1818; padding: 2px 0;">'
                    f'<span style="color: #858585; user-select: none; padding: 0 10px; min-width: 50px; display: inline-block; text-align: right; border-right: 1px solid #3e3e3e; margin-right: 10px;">{line_num}</span>'
                    f'<span style="color: #f48771;">{escaped if escaped else "&nbsp;"}</span>'
                    f'</div>'
                )
            elif line.startswith('+ ') and not is_old:
                # Line added (only show in new) - dark green background
                line_num += 1
                html_lines.append(
                    f'<div style="background-color: #1a4b1a; padding: 2px 0;">'
                    f'<span style="color: #858585; user-select: none; padding: 0 10px; min-width: 50px; display: inline-block; text-align: right; border-right: 1px solid #3e3e3e; margin-right: 10px;">{line_num}</span>'
                    f'<span style="color: #89d185;">{escaped if escaped else "&nbsp;"}</span>'
                    f'</div>'
                )
            elif line.startswith('  '):
                # Line unchanged - normal background
                line_num += 1
                html_lines.append(
                    f'<div style="background-color: transparent; padding: 2px 0;">'
                    f'<span style="color: #858585; user-select: none; padding: 0 10px; min-width: 50px; display: inline-block; text-align: right; border-right: 1px solid #3e3e3e; margin-right: 10px;">{line_num}</span>'
                    f'<span style="color: #d4d4d4;">{escaped if escaped else "&nbsp;"}</span>'
                    f'</div>'
                )
            elif line.startswith('? '):
                # Skip these marker lines from ndiff
                continue
        
        return '<div style="margin: 0; font-family: Consolas, monospace; font-size: 10pt; line-height: 1.6;">' + ''.join(html_lines) + '</div>'
    
    def select_new_change(self):
        """Accept new change - write new content to file"""
        # Write the new content to the file
        if self.new_content is not None:
            try:
                with open(self.file_path, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(self.new_content)
                self.selected_action = 'accept_new'
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Applied", f"✅ New code applied to:\n{os.path.basename(self.file_path)}")
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"Failed to write file: {e}")
        self.accept()
    
    def select_old_version(self):
        """Revert to old version - discard new changes and restore old code"""
        # Write the old content back to the file to revert changes
        if self.old_content is not None:
            try:
                with open(self.file_path, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(self.old_content)
                self.selected_action = 'revert_to_old'
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Reverted", f"File reverted to old version:\n{os.path.basename(self.file_path)}")
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"Failed to revert file: {e}")
        self.accept()

class ChangeReviewDialog(QDialog):
    """Dialog to review all file changes with line-by-line diff and undo capability"""
    def __init__(self, changes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review File Changes")
        self.setMinimumWidth(900)
        self.setMinimumHeight(700)
        # Enable window resizing with minimize and maximize buttons
        self.setWindowFlags(Qt.WindowType.Window | 
                          Qt.WindowType.WindowMinimizeButtonHint | 
                          Qt.WindowType.WindowMaximizeButtonHint | 
                          Qt.WindowType.WindowCloseButtonHint)
        self.setSizeGripEnabled(True)
        self.changes = changes  # List of FileChangeEntry objects
        
        layout = QVBoxLayout(self)
        
        # Info label
        info_label = QLabel(f"Total changes: {len(changes)} files")
        info_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(info_label)
        
        # File list table
        self.file_list = QTableWidget()
        self.file_list.setColumnCount(3)
        self.file_list.setHorizontalHeaderLabels(["Include", "File Path", "Status"])
        self.file_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.file_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_list.setMaximumHeight(250)  # Set max height to force scrolling for many files
        self.file_list.currentItemChanged.connect(self.on_file_selected)
        
        # Populate file list
        self.checkboxes = []
        for idx, change in enumerate(changes):
            self.file_list.insertRow(idx)
            
            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(change.is_selected)
            checkbox.stateChanged.connect(lambda state, i=idx: self.on_checkbox_changed(i, state))
            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.addWidget(checkbox)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            self.file_list.setCellWidget(idx, 0, cell_widget)
            self.checkboxes.append(checkbox)
            
            # File path
            self.file_list.setItem(idx, 1, QTableWidgetItem(change.relative_path))
            
            # Status
            if change.old_content is None:
                status = "New"
            elif change.new_content is None:
                status = "Deleted"
            else:
                status = "Modified"
            self.file_list.setItem(idx, 2, QTableWidgetItem(status))
        
        layout.addWidget(self.file_list)
        
        # Current file display label
        self.current_file_label = QLabel("Select a file to view changes")
        self.current_file_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #569cd6; padding: 5px;")
        layout.addWidget(self.current_file_label)
        
        self.diff_viewer = QTextEdit()
        self.diff_viewer.setReadOnly(True)
        self.diff_viewer.setFont(QFont("Consolas", 10))
        self.diff_viewer.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
                padding: 5px;
            }
        """)
        layout.addWidget(self.diff_viewer)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        btn_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        btn_layout.addWidget(self.deselect_all_btn)
        
        btn_layout.addStretch()
        
        self.apply_btn = QPushButton("Apply Selected Changes")
        self.apply_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.apply_btn)
        
        self.cancel_btn = QPushButton("Cancel All")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
        
        # Select first file by default
        if self.file_list.rowCount() > 0:
            self.file_list.setCurrentCell(0, 1)
    
    def on_checkbox_changed(self, idx, state):
        self.changes[idx].is_selected = (state == Qt.CheckState.Checked.value)
    
    def on_file_selected(self, current, previous):
        if current is None:
            return
        row = current.row()
        if row < 0 or row >= len(self.changes):
            return
        
        change = self.changes[row]
        
        # Update the current file label with filename
        filename = os.path.basename(change.file_path)
        self.current_file_label.setText(f"📄 Currently viewing: {filename}")
        
        diff_lines = change.get_diff_lines()
        
        # Format diff with IDE-style colors and line numbers
        formatted_diff = []
        line_num = 0
        for line in diff_lines:
            # Escape HTML but preserve structure
            escaped = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            if line.startswith('+'):
                # Added line - green background
                line_num += 1
                formatted_diff.append(
                    f'<div style="background-color: #1a4b1a; padding: 2px 0;">'
                    f'<span style="color: #858585; padding: 0 10px; min-width: 50px; display: inline-block; text-align: right; border-right: 1px solid #3e3e3e; margin-right: 10px;">{line_num}</span>'
                    f'<span style="color: #89d185;">{escaped}</span>'
                    f'</div>'
                )
            elif line.startswith('-'):
                # Removed line - red background
                line_num += 1
                formatted_diff.append(
                    f'<div style="background-color: #4b1818; padding: 2px 0;">'
                    f'<span style="color: #858585; padding: 0 10px; min-width: 50px; display: inline-block; text-align: right; border-right: 1px solid #3e3e3e; margin-right: 10px;">{line_num}</span>'
                    f'<span style="color: #f48771;">{escaped}</span>'
                    f'</div>'
                )
            elif line.startswith('@@'):
                # Diff header - blue
                formatted_diff.append(
                    f'<div style="background-color: #1a1a4b; padding: 2px 0;">'
                    f'<span style="color: #858585; padding: 0 10px; min-width: 50px; display: inline-block; text-align: right; border-right: 1px solid #3e3e3e; margin-right: 10px;">...</span>'
                    f'<span style="color: #569cd6; font-weight: bold;">{escaped}</span>'
                    f'</div>'
                )
            else:
                # Context line - normal
                line_num += 1
                formatted_diff.append(
                    f'<div style="background-color: transparent; padding: 2px 0;">'
                    f'<span style="color: #858585; padding: 0 10px; min-width: 50px; display: inline-block; text-align: right; border-right: 1px solid #3e3e3e; margin-right: 10px;">{line_num}</span>'
                    f'<span style="color: #d4d4d4;">{escaped}</span>'
                    f'</div>'
                )
        
        self.diff_viewer.setHtml(
            '<div style="margin: 0; font-family: Consolas, monospace; font-size: 10pt; line-height: 1.6;">' + 
            ''.join(formatted_diff) + 
            '</div>'
        )
    
    def select_all(self):
        for i, checkbox in enumerate(self.checkboxes):
            checkbox.setChecked(True)
            self.changes[i].is_selected = True
    
    def deselect_all(self):
        for i, checkbox in enumerate(self.checkboxes):
            checkbox.setChecked(False)
            self.changes[i].is_selected = False
    
    def get_selected_changes(self):
        return [change for change in self.changes if change.is_selected]


class FileEventHandler(FileSystemEventHandler, QObject):
    #open_log_dialog_signal = pyqtSignal() 
    def __init__(self, table, watch_path, excluded_folders, excluded_files, dialog):
        super().__init__()
        self.table = table
        self.watch_path = watch_path
        self.excluded_folders = excluded_folders
        self.excluded_files = excluded_files
        self.file_hashes = {}  # Dictionary to store last known file hashes
        self.load_file_hash = True
        self.preload_complete = False  # Flag to ignore events until baseline is captured
        self.dialog = dialog

        #print(f"FileEventHandler log_txt {self.log_txt}")
    def stopp_reload_file_hashes(self):
        self.load_file_hash = False
        
    def calculate_file_hash(self, file_path, keep_hash = True):
        # print(f"cal={file_path}")
        """Calculate and cache the file hash based solely on its content."""
        forward_slash_path = file_path.replace("\\", "/")
        try:
            # If the file path exists and has a cached hash, return the cached hash
            #if file_path in self.file_hashes:
            #    return self.file_hashes[file_path]  # Return cached hash

            # Otherwise, compute the file hash
            hasher = hashlib.md5()
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):  # Read in chunks for efficiency
                    hasher.update(chunk)

            file_hash = hasher.hexdigest()
            # Store the hash in the cache (no need to store mtime)
            #normpath = os.path.normpath(file_path)
            if keep_hash:
                self.file_hashes[forward_slash_path] = file_hash
            return file_hash
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return None
        
    def preload_file_hashes(self, table_index):
        print(f"Preloading file hashes for table {table_index}")
        threads = []
        lock = threading.Lock()  # Lock to ensure thread-safe dictionary updates

        def process_file(file_path):
            """Hash a file and update the dictionary safely. Also capture file content as baseline."""
            if not self.load_file_hash:
                return

            file_hash = self.calculate_file_hash(file_path)
            if file_hash:
                with lock:  # Ensure thread-safe update
                    self.file_hashes[file_path] = file_hash
                    print(f"{file_path}=>{file_hash}")
                    
                    # Capture file content as "old" baseline when scanning starts
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            self.table.file_contents[file_path] = content
                            if DEBUG:
                                print(f"Captured baseline content for: {file_path}")
                    except Exception as e:
                        print(f"Error capturing baseline content for {file_path}: {e}")
                        self.table.file_contents[file_path] = None
                        
                self.dialog.add_log_signal.emit(file_path)

        for root, dirs, files in os.walk(self.watch_path):
            if not self.load_file_hash:
                print("Stopped preloading file hashes")
                return

            root = root.replace("\\", "/")  # Convert paths for cross-platform compatibility
            dirs[:] = [d for d in dirs if not self._is_excluded(os.path.join(root, d))]  # Skip excluded dirs

            for file in files:
                if not self.load_file_hash:
                    print("Stopped preloading file hashes")
                    return

                file_path = os.path.join(root, file).replace("\\", "/")
                if not self._is_excluded(file_path):
                    thread = threading.Thread(target=process_file, args=(file_path,))
                    thread.start()
                    threads.append(thread)

        # Wait for all threads to finish
        for thread in threads:
            thread.join()

        # Mark preload as complete - now we can start processing file change events
        self.preload_complete = True
        print(f"Preload complete for table {table_index}, baseline captured for all files")

        #self.dialog.upt_log_signal.emit("Scan files Completed")  # Emit completion signal
        
    def on_modified(self, event):
        """Handle file modifications efficiently."""
        # Ignore all events until preload is complete (baseline captured)
        if not self.preload_complete:
            return
        if event.is_directory:
            return  # Ignore directory-level modifications
        
        file_path =  os.path.normpath(event.src_path)
        if self._is_excluded(file_path) or event.is_directory:
            return
        
        # Calculate the new hash for the file
        new_hash = self.calculate_file_hash(file_path, False)
        forward_slash_path  = file_path.replace("\\", "/")
        if DEBUG == True:
            print(f"new_hash={forward_slash_path} {new_hash}")
        if new_hash:
            if forward_slash_path not in self.file_hashes:
                if DEBUG == True:
                    print(f"add hash")
                self.file_hashes[forward_slash_path] = new_hash
                #QCoreApplication.postEvent(self.table, FileUpdateEvent(self.table, file_path))
            else:
                if DEBUG == True:
                    print(f"check hash {self.file_hashes[forward_slash_path]}, {new_hash}")

                if self.file_hashes[forward_slash_path] != new_hash:
                    if DEBUG == True:
                        print(f"upt hash")

                    self.file_hashes[forward_slash_path] = new_hash
                    QCoreApplication.postEvent(self.table, FileUpdateEvent(self.table, file_path))

    def on_created(self, event):
        #print(f"on_created triggered for {event.src_path}")
        if self._is_excluded(event.src_path):
            print(f"Skipping on_created {event.src_path}")
            return

        file_path = event.src_path
        file_hash = self.calculate_file_hash(file_path)
        
        if file_hash:
            forward_slash_path  = file_path.replace("\\", "/")
            self.file_hashes[forward_slash_path] = file_hash         
            # Create and post event
            event_obj = FileCreateEvent(self.table, file_path)
            QCoreApplication.postEvent(self.table, event_obj)

    def on_deleted(self, event):
        if self._is_excluded(event.src_path):
            print(f"Skipping on_deleted {event.src_path}")
            return
        
        if not event.is_directory:
            file_path = event.src_path
            forward_slash_path  = file_path.replace("\\", "/")
            if forward_slash_path in self.file_hashes:
                del self.file_hashes[forward_slash_path]  # Remove the file from the hash dictionary
                print(f"File deleted: {forward_slash_path}")
                # Handle the deletion event as needed
                QCoreApplication.postEvent(self.table, FileDeleteEvent(self.table, file_path))

    def _is_excluded(self, path):
        excluded_paths = [os.path.join(self.watch_path, folder) for folder in self.excluded_folders]
        # Normalize the path
        abs_path = os.path.abspath(path)
        basename = os.path.basename(path)
        # Check if path is inside any excluded folder
        if any(abs_path.startswith(os.path.abspath(folder)) for folder in excluded_paths):
            return True
        
        if basename in self.excluded_files:
            return True

        return False
    
def get_pixmap_from_base64(base64_string):
    """Convert Base64 string to QPixmap."""
    image_data = QByteArray.fromBase64(base64_string.encode("utf-8"))
    pixmap = QPixmap()
    pixmap.loadFromData(image_data)
    return pixmap

def escape_markdown(text):
    special_chars = r'_\*\[\]\(\)~`>#+-=|{}.!'
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", text)
    
class FileWatcherTable(QTableWidget):
    def __init__(self, folder_to_watch):
        super().__init__()
        self.folder_to_watch = folder_to_watch
        self.file_contents = {}  # Track old file content for diff {file_path: content}
        
        self.setColumnCount(2)  # Ensure only 2 columns
        self.setHorizontalHeaderLabels(["File Name", "Action"])
        self.verticalHeader().setDefaultSectionSize(36)  # Set row height to 36 (increased)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 100)  # Set the width of the second column
        self.setMinimumWidth(400)  # Ensure table doesn't shrink below a minimum width
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Remove dotted focus border
        self.setStyleSheet("""
            QTableWidget::item:focus {
                outline: none;
                border: none;
            }
        """)
        
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
        # Try normalized path first, then try original path format if not found
        old_content = self.file_contents.get(file_path)
        if old_content is None:
            # Try with backslashes (Windows format) in case baseline was stored differently
            file_path_backslash = file_path.replace("/", "\\")
            old_content = self.file_contents.get(file_path_backslash)
            if old_content is not None:
                # Found with backslashes - copy to normalized format for consistency
                self.file_contents[file_path] = old_content
        
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
        #removeRow build-in, but overrite to see log
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
        if DEBUG == True:
            print(f"update_file FileWatcherTable={file_path}")

        file_name = os.path.relpath(file_path, self.folder_to_watch)
        
        # Normalize path to forward slashes to match preload storage format
        normalized_path = file_path.replace("\\", "/")
        
        # Check if file is already in table
        file_exists = False
        for row in range(self.rowCount()):
            if self.item(row, 0) and self.item(row, 0).text() == file_name:
                file_exists = True
                break
        
        # If file doesn't exist in table yet, add it
        # IMPORTANT: Baseline content should already exist from preload_file_hashes
        # If it doesn't exist, it means file was created after preload
        if not file_exists:
            # Check if baseline content exists (file was preloaded)
            # Try both normalized and original path formats
            baseline_exists = normalized_path in self.file_contents
            if not baseline_exists:
                # Try with original path format (backslashes)
                baseline_exists = file_path in self.file_contents
                if baseline_exists:
                    # Found with original format - copy to normalized format for consistency
                    self.file_contents[normalized_path] = self.file_contents[file_path]
            
            # Now add the file to table - baseline will be preserved in add_file
            self.add_file(file_path)
        # If file already exists in table, do nothing - keep the original baseline content
        # The baseline was captured when scanning started in preload_file_hashes

    def add_file(self, file_path):
        """Add new file to table"""
        if DEBUG == True:
            print(f"add_file FileWatcherTable={file_path}")

        #file_name = os.path.basename(file_path)
        file_name = os.path.relpath(file_path, self.folder_to_watch)
        
        # Check if file is already added
        for row in range(self.rowCount()):
            if self.item(row, 0) and self.item(row, 0).text() == file_name:
                return
        
        # Normalize path to forward slashes to match preload storage format
        normalized_path = file_path.replace("\\", "/")
        
        # IMPORTANT: Only store current content if baseline doesn't exist from preload
        # If baseline exists (from preload), preserve it - don't overwrite with current content
        # This ensures we can show the diff between baseline (from start) and current content
        if normalized_path not in self.file_contents:
            # No baseline exists - file was created after preload
            # Store current content as baseline (but there won't be a diff for first change)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    self.file_contents[normalized_path] = f.read()
            except Exception as e:
                print(f"Error reading file {file_path}: {e}")
                self.file_contents[normalized_path] = None
        # If baseline already exists (from preload), don't overwrite it - preserve the baseline
        
        row_position = self.rowCount()
        self.insertRow(row_position)
        self.setItem(row_position, 0, QTableWidgetItem(file_name))
        
        # Ensure column width remains fixed after adding a new row
        if self.rowCount() >= 10:
            self.setColumnWidth(0, 278)
        else :
            self.setColumnWidth(0, 286)  # Maintain column width for the first column
        
        self.setColumnWidth(1, 100)  # Maintain column width for the second column
        
        btn_remove = QPushButton()
        btn_remove.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_remove.setFixedSize(20, 20)  # Make delete button smaller than the row
        btn_remove.setStyleSheet("""
            QPushButton {
                border: none;
                padding: 0px;
                background: transparent;
            }
            QPushButton:hover {
                background: rgba(255, 0, 0, 0.1);
                border-radius: 3px;
            }
        """)
        
        # Set icon
        # icon_path = "remove_icon.png" 
        # btn_remove.setIcon(QIcon(QPixmap(icon_path)))
        # btn_remove.setIconSize(QSize(20, 30))
        #data:image/png;base64,
        ICON_BASE64 = "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"
        btn_remove.setIcon(QIcon(get_pixmap_from_base64(ICON_BASE64)))
        btn_remove.setIconSize(QSize(14, 14))
        btn_remove.clicked.connect(lambda _, btn= btn_remove: self.remove_button_row(btn))  # Capture row index
        
        # Center button in cell
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)  # Remove padding
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Align center
        btn_layout.addWidget(btn_remove)
        cell_widget = QWidget()
        cell_widget.setLayout(btn_layout)
        
        self.setCellWidget(row_position, 1, cell_widget)

    def remove_file(self, file_path):
        #work when remove file from system
        file_name = os.path.relpath(file_path, self.folder_to_watch).strip()
        print(f"remove_file {file_name} from {self.rowCount()}")
        for row in range(self.rowCount()):
            if self.item(row, 0) and self.item(row, 0).text().strip() == file_name:
                self.removeRow(row)
                return  # Stop after removing the first match
    
#================
class SettingsDialog(QDialog):
    """Professional settings dialog."""
    def __init__(self, setting, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Application Settings")
        self.setMinimumWidth(900)
        self.setMinimumHeight(700)
        self.setting = setting
        
        # Apply professional styling
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
            }
            QLabel {
                color: #CCCCCC;
                font-size: 13px;
                font-weight: 500;
            }
            QGroupBox {
                color: #FFFFFF;
                font-size: 14px;
                font-weight: 600;
                border: 1px solid #3C3C3C;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 16px;
                background-color: #252526;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0px 8px;
                background-color: #252526;
            }
            QPushButton {
                background-color: #007ACC;
                color: #FFFFFF;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1C97EA;
            }
            QPushButton:pressed {
                background-color: #005A9E;
            }
        """)

        sys_path = setting.get("sys_path", {})
        sys_path2 = setting.get("sys_path2", {})
        dest_path = setting.get("dest_path", {})
        source_path = setting.get("source_path", {})
        git_path = setting.get("git_path", {})
        backup_path = setting.get("backup_path", {})
        user    = setting.get("user", {})
        
        # Get number of systems configured
        self.num_systems = setting.get("num_systems", 3)
        
        # Main layout (vertical) with scroll area
        self.main_layout = QVBoxLayout(self)
        
        # Create scroll area for the settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # User info section
        self.row_layout_user = QHBoxLayout()
        self.user_label_name = QLabel("Username:", self)
        self.user_label_name.setStyleSheet("color: #E0E0E0; font-size: 12px;")
        self.user_input_name = QLineEdit(self)
        self.user_input_name.setText(user.get("username", ""))
        self.user_input_name.setFixedHeight(30)
        self.user_input_name.setStyleSheet("""
            QLineEdit {
                background-color: #3C3C3C;
                color: #E0E0E0;
                border: 2px solid #5A5A5A;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #1976D2;
                border-radius: 6px;
            }
        """)
        self.row_layout_user.addWidget(self.user_label_name)
        self.row_layout_user.addWidget(self.user_input_name)
        scroll_layout.addLayout(self.row_layout_user)
        scroll_layout.addSpacing(15)  # Add space between rows

        # Telegram section
        self.row_layout_tele = QHBoxLayout()
        self.tele_label_token = QLabel("Telegram Token:", self)
        self.tele_label_token.setStyleSheet("color: #E0E0E0; font-size: 12px;")
        self.tele_input_token = QLineEdit(self)
        self.tele_input_token.setText(setting.get("telegram_token", ""))
        self.tele_input_token.setFixedHeight(30)
        self.tele_input_token.setStyleSheet("""
            QLineEdit {
                background-color: #3C3C3C;
                color: #E0E0E0;
                border: 2px solid #5A5A5A;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #1976D2;
                border-radius: 6px;
            }
        """)
        self.tele_label_chat = QLabel("Telegram Group ID:", self)
        self.tele_label_chat.setStyleSheet("color: #E0E0E0; font-size: 12px;")
        self.tele_input_chat = QLineEdit(self)
        self.tele_input_chat.setText(setting.get("telegram_chat_id", ""))
        self.tele_input_chat.setFixedHeight(30)
        self.tele_input_chat.setStyleSheet("""
            QLineEdit {
                background-color: #3C3C3C;
                color: #E0E0E0;
                border: 2px solid #5A5A5A;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #1976D2;
                border-radius: 6px;
            }
        """)
        self.row_layout_tele.addWidget(self.tele_label_token)
        self.row_layout_tele.addWidget(self.tele_input_token)
        self.row_layout_tele.addSpacing(20)
        self.row_layout_tele.addWidget(self.tele_label_chat)
        self.row_layout_tele.addWidget(self.tele_input_chat)
        scroll_layout.addLayout(self.row_layout_tele)
        scroll_layout.addSpacing(20)  # Add space between rows
        
        # Systems section
        systems_group = QGroupBox("Systems Configuration")
        systems_layout = QVBoxLayout()
        
        # Add/Remove system buttons
        sys_btn_layout = QHBoxLayout()
        self.add_sys_btn = QPushButton("Add System")
        self.add_sys_btn.clicked.connect(self.add_system)
        self.remove_sys_btn = QPushButton("Remove Last System")
        self.remove_sys_btn.clicked.connect(self.remove_system)
        sys_btn_layout.addWidget(self.add_sys_btn)
        sys_btn_layout.addWidget(self.remove_sys_btn)
        sys_btn_layout.addStretch()
        systems_layout.addLayout(sys_btn_layout)
        
        # Container for system rows
        self.systems_container = QWidget()
        self.systems_layout = QVBoxLayout(self.systems_container)
        self.systems_layout.setSpacing(15)  # Increased spacing between system rows
        
        # Store system input widgets
        self.source_inputs = []
        self.dest_inputs = []
        self.git_inputs = []
        self.backup_inputs = []  # New backup path inputs
        self.system_rows = []
        
        # Create initial system rows
        for i in range(self.num_systems):
            sys_key = f"sys{i+1}"
            self.create_system_row(i, 
                                  source_path.get(sys_key, ""),
                                  dest_path.get(sys_key, ""),
                                  git_path.get(sys_key, ""),
                                  backup_path.get(sys_key, ""))
        
        systems_layout.addWidget(self.systems_container)
        systems_group.setLayout(systems_layout)
        scroll_layout.addWidget(systems_group)

        # Create dynamic table headers based on number of systems
        sys_paths_grouped = {}
        for i in range(1, self.num_systems + 1):
            sys_paths_grouped[i] = [item for item in sys_path if item["sys"] == i]
        
        max_value = max([len(sys_paths_grouped[i]) for i in range(1, self.num_systems + 1)]) if sys_paths_grouped else 0

        self.table = QTableWidget(max_value, self.num_systems, self)
        headers = [f"Sys{i}" for i in range(1, self.num_systems + 1)]
        self.table.setHorizontalHeaderLabels(headers)

        for i in range(max_value):
            for sys_num in range(1, self.num_systems + 1):
                if i < len(sys_paths_grouped[sys_num]):
                    vcol = sys_paths_grouped[sys_num][i].get("path", "")
                else:
                    vcol = ""
                self.table.setItem(i, sys_num - 1, QTableWidgetItem(vcol))

        # Connect cellChanged signal to a slot
        self.table.cellChanged.connect(self.cell_changed)

        # Make table columns stretch to fit the table
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        layout_relative = QHBoxLayout()
        layout_relative_inner = QHBoxLayout()
        self.row_layout4 = QHBoxLayout()
        layout_relative_inner.addLayout(self.row_layout4)

        legend_relative  = QGroupBox("Without")
        legend_relative.setLayout(layout_relative_inner)
        layout_relative.addWidget(legend_relative)
        scroll_layout.addLayout(layout_relative)
        # Add Row Button
        self.def_row_button = QPushButton("Default", self)
        self.def_row_button.clicked.connect(lambda: self.load_def_setting(self.table, 'without'))
        self.add_row_button = QPushButton("Add", self)
        self.add_row_button.clicked.connect(self.add_row)

        self.delete_row_button = QPushButton("Delete", self)
        self.delete_row_button.clicked.connect(self.delete_row)  # Connect button to delete_row method

        self.path_cont_col1 = QVBoxLayout()
        self.path_cont_col1.addWidget(self.table)

        self.row_layout_btn = QVBoxLayout()        
        self.row_layout_btn.addWidget(self.def_row_button)
        self.row_layout_btn.addWidget(self.add_row_button)
        self.row_layout_btn.addWidget(self.delete_row_button)
        

        self.path_cont_col2 = QVBoxLayout()
        self.path_cont_col2.addLayout(self.row_layout_btn)

        self.row_layout4.addLayout(self.path_cont_col1)
        self.row_layout4.addLayout(self.path_cont_col2)

        #skip folders setting
        layout_except = QHBoxLayout()
        legend_groupbox = QGroupBox("Except")

        sys_paths2_grouped = {}
        for i in range(1, self.num_systems + 1):
            sys_paths2_grouped[i] = [item for item in sys_path2 if item["sys"] == i]

        max_value2 = max([len(sys_paths2_grouped[i]) for i in range(1, self.num_systems + 1)]) if sys_paths2_grouped else 0

        self.table_except = QTableWidget(max_value2, self.num_systems)
        headers2 = [f"Sys{i}" for i in range(1, self.num_systems + 1)]
        self.table_except.setHorizontalHeaderLabels(headers2)
        self.table_except.verticalHeader().setVisible(True)

        header_except_file = self.table_except.horizontalHeader()
        header_except_file.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for i in range(max_value2):
            for sys_num in range(1, self.num_systems + 1):
                if i < len(sys_paths2_grouped[sys_num]):
                    vcol2 = sys_paths2_grouped[sys_num][i].get("path", "")
                else:
                    vcol2 = ""
                self.table_except.setItem(i, sys_num - 1, QTableWidgetItem(vcol2))

        layout_except_inner = QHBoxLayout()
        row_except_inner = QVBoxLayout() 



        except_col1 = QVBoxLayout()
        except_col1.addWidget(QLabel("File:"))
        except_col1.addWidget(self.table_except)
        layout_except_inner.addLayout(except_col1)

        except_def_button = QPushButton("Default", self)
        except_def_button.clicked.connect(lambda: self.load_def_setting(self.table_except, 'except'))
        except_add_row_btn = QPushButton("Add", self)
        except_add_row_btn.clicked.connect(self.add_row2)

        except_del_row_btn = QPushButton("Delete", self)
        except_del_row_btn.clicked.connect(self.delete_row2)  # Connect button to delete_row method

        except_file_btn = QVBoxLayout()
        except_file_btn.addWidget(except_def_button)
        except_file_btn.addWidget(except_add_row_btn)
        except_file_btn.addWidget(except_del_row_btn)
        row_except_inner.addLayout(except_file_btn)
        layout_except_inner.addLayout(row_except_inner)

        legend_groupbox.setLayout(layout_except_inner)
        layout_except.addWidget(legend_groupbox)
        scroll_layout.addLayout(layout_except)
        
        # Set scroll widget
        scroll.setWidget(scroll_widget)
        self.main_layout.addWidget(scroll)
        
        # Save Button
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_settings)
        self.main_layout.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignCenter)
    
    def create_system_row(self, index, source="", dest="", git="", backup=""):
        """Create a system configuration row"""
        sys_num = index + 1
        row_widget = QWidget()
        row_layout = QVBoxLayout(row_widget)  # Changed to vertical for better layout
        row_layout.setContentsMargins(0, 5, 0, 5)
        row_layout.setSpacing(8)
        
        # System label (header)
        sys_label = QLabel(f"System {sys_num}")
        sys_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #1976D2;")
        row_layout.addWidget(sys_label)
        
        # First row: Source and Destination paths
        first_row = QHBoxLayout()
        
        # Source path
        source_label = QLabel("Source:", row_widget)
        source_label.setFixedWidth(60)
        source_label.setStyleSheet("color: #E0E0E0; font-size: 12px;")
        source_input = QLineEdit(row_widget)
        source_input.setText(source)
        source_input.setFixedHeight(30)
        source_input.setStyleSheet("""
            QLineEdit {
                background-color: #3C3C3C;
                color: #E0E0E0;
                border: 2px solid #5A5A5A;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #1976D2;
                border-radius: 6px;
            }
        """)
        first_row.addWidget(source_label)
        first_row.addWidget(source_input, 1)
        first_row.addSpacing(10)
        
        # Destination path
        dest_label = QLabel("Destination:", row_widget)
        dest_label.setFixedWidth(80)
        dest_label.setStyleSheet("color: #E0E0E0; font-size: 12px;")
        dest_input = QLineEdit(row_widget)
        dest_input.setText(dest)
        dest_input.setFixedHeight(30)
        dest_input.setStyleSheet("""
            QLineEdit {
                background-color: #3C3C3C;
                color: #E0E0E0;
                border: 2px solid #5A5A5A;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #1976D2;
                border-radius: 6px;
            }
        """)
        first_row.addWidget(dest_label)
        first_row.addWidget(dest_input, 1)
        
        row_layout.addLayout(first_row)
        
        # Second row: Git and Backup paths
        second_row = QHBoxLayout()
        
        # Git path
        git_label = QLabel("Git:", row_widget)
        git_label.setFixedWidth(60)
        git_label.setStyleSheet("color: #E0E0E0; font-size: 12px;")
        git_input = QLineEdit(row_widget)
        git_input.setText(git)
        git_input.setFixedHeight(30)
        git_input.setStyleSheet("""
            QLineEdit {
                background-color: #3C3C3C;
                color: #E0E0E0;
                border: 2px solid #5A5A5A;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #1976D2;
                border-radius: 6px;
            }
        """)
        second_row.addWidget(git_label)
        second_row.addWidget(git_input, 1)
        second_row.addSpacing(10)
        
        # Backup path
        backup_label = QLabel("Backup:", row_widget)
        backup_label.setFixedWidth(80)
        backup_label.setStyleSheet("color: #E0E0E0; font-size: 12px;")
        backup_input = QLineEdit(row_widget)
        backup_input.setText(backup)
        backup_input.setFixedHeight(30)
        backup_input.setStyleSheet("""
            QLineEdit {
                background-color: #3C3C3C;
                color: #E0E0E0;
                border: 2px solid #5A5A5A;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #1976D2;
                border-radius: 6px;
            }
        """)
        backup_input.setPlaceholderText("Path to store backups with date-time folders")
        second_row.addWidget(backup_label)
        second_row.addWidget(backup_input, 1)
        
        row_layout.addLayout(second_row)
        
        self.source_inputs.append(source_input)
        self.dest_inputs.append(dest_input)
        self.git_inputs.append(git_input)
        self.backup_inputs.append(backup_input)
        self.system_rows.append(row_widget)
        
        self.systems_layout.addWidget(row_widget)
    
    def add_system(self):
        """Add a new system configuration row"""
        self.num_systems += 1
        self.create_system_row(self.num_systems - 1, "", "", "")
        
        # Update tables
        self.table.setColumnCount(self.num_systems)
        headers = [f"Sys{i}" for i in range(1, self.num_systems + 1)]
        self.table.setHorizontalHeaderLabels(headers)
        
        self.table_except.setColumnCount(self.num_systems)
        self.table_except.setHorizontalHeaderLabels(headers)
    
    def remove_system(self):
        """Remove the last system configuration row"""
        if self.num_systems <= 1:
            QMessageBox.warning(self, "Cannot Remove", "At least one system must be configured.")
            return
        
        # Remove the last row widget
        if self.system_rows:
            row_widget = self.system_rows.pop()
            row_widget.deleteLater()
            self.source_inputs.pop()
            self.dest_inputs.pop()
            self.git_inputs.pop()
            self.backup_inputs.pop()
            self.num_systems -= 1
            
            # Update tables
            self.table.setColumnCount(self.num_systems)
            headers = [f"Sys{i}" for i in range(1, self.num_systems + 1)]
            self.table.setHorizontalHeaderLabels(headers)
            
            self.table_except.setColumnCount(self.num_systems)
            self.table_except.setHorizontalHeaderLabels(headers)

    def load_def_setting(self, table, type):
        response = requests.get(f"{API_URL}log_sys.php")
        # Check if request was successful (status code 200)
        if response.status_code == 200:
            json = response.json()  # Convert response to JSON
            #print(f"json={json}")
            data_set = json.get(type, [])
            #print(f"data_set={data_set}")
            table.setRowCount(0)
            for item in data_set:
                row_position = table.rowCount()
                table.insertRow(row_position)
                table.setItem(row_position, 0, QTableWidgetItem(item))
                table.setItem(row_position, 1, QTableWidgetItem(item))
                table.setItem(row_position, 2, QTableWidgetItem(item))
                # print(f"data_set {item}")

        else:
            print(f"Error: {response.status_code}")


    def cell_changed(self, row, column):
        """Handle cell changes and print the new value."""
        new_value = self.table.item(row, column).text()
        #print(f"Cell ({row}, {column}) changed to: {new_value}")

    def add_row(self):
        """Add a new empty row to the table."""
        row_count = self.table.rowCount()
        self.table.insertRow(row_count)
    def delete_row(self):
        """Delete the currently selected row."""
        selected_row = self.table.currentRow()  # Get the currently selected row
        if selected_row != -1:  # Ensure a row is selected
            self.table.removeRow(selected_row)

    def add_row2(self):
        """Add a new empty row to the table."""
        row_count = self.table_except.rowCount()
        self.table_except.insertRow(row_count)
    def delete_row2(self):
        """Delete the currently selected row."""
        selected_row = self.table_except.currentRow()  # Get the currently selected row
        if selected_row != -1:  # Ensure a row is selected
            self.table_except.removeRow(selected_row)

    def get_table_values(self, table):
        """Retrieve values from the table."""
        rows = table.rowCount()
        cols = table.columnCount()
        table_data = []

        for row in range(rows):
            row_data = []
            for col in range(cols):
                item = table.item(row, col)
                if item:
                    row_data.append(item.text())  # Get the text of the item
                else:
                    row_data.append("")  # Handle empty cells
            table_data.append(row_data)

        return table_data

    def save_settings(self):
        """Save the destination path and return it to the main window."""
        # Collect system paths dynamically
        git_path = {}
        dest_path = {}
        source_path = {}
        backup_path = {}
        
        for i in range(self.num_systems):
            sys_key = f"sys{i+1}"
            source_path[sys_key] = self.source_inputs[i].text() if i < len(self.source_inputs) else ""
            dest_path[sys_key] = self.dest_inputs[i].text() if i < len(self.dest_inputs) else ""
            git_path[sys_key] = self.git_inputs[i].text() if i < len(self.git_inputs) else ""
            backup_path[sys_key] = self.backup_inputs[i].text() if i < len(self.backup_inputs) else ""
        
        username = self.user_input_name.text()
        telegram_token = self.tele_input_token.text()
        telegram_chat_id = self.tele_input_chat.text()
        user = {
            "username": username
        }

        self.parent().setting["user"] = user
        self.parent().setting["telegram_token"] = telegram_token
        self.parent().setting["telegram_chat_id"] = telegram_chat_id
        self.parent().setting["dest_path"] = dest_path
        self.parent().setting["source_path"] = source_path
        self.parent().setting["git_path"] = git_path
        self.parent().setting["backup_path"] = backup_path
        self.parent().setting["num_systems"] = self.num_systems

        table_data = self.get_table_values(self.table)
        table_data2 = self.get_table_values(self.table_except)

        path_setting_data  = []
        path_setting_data2 = []
        for row in table_data:
            for i, col_value in enumerate(row):
                if col_value:  # Only add non-empty values
                    path_setting_data.append({"path": col_value, "sys": i + 1})

        for row in table_data2:
            for i, col_value in enumerate(row):
                if col_value:  # Only add non-empty values
                    path_setting_data2.append({"path": col_value, "sys": i + 1})

        self.parent().setting["sys_path"] = path_setting_data
        self.parent().setting["sys_path2"] = path_setting_data2

        # print(f"new update={self.parent().setting}")

        self.parent().update_destination_path({
            "user": user,
            "git_path": git_path,
            "dest_path": dest_path,
            "source_path": source_path,
            "sys_path" : path_setting_data,
            "sys_path2" : path_setting_data2,
            "telegram_token": telegram_token,
            "telegram_chat_id": telegram_chat_id,
            "num_systems": self.num_systems,
        })
        self.accept()  # Close the settings panel
        
        # Auto-restart the application after saving settings
        QTimer.singleShot(100, self.parent().restart_app)
#================
class FileWatcherApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setting = self.load_setting()
        
        # Get number of systems (default to 3 if not set)
        self.num_systems = self.setting.get("num_systems", 3)
        
        #load default set from api start
        app_def_set = self.load_app_setting()

        app_data_set    = app_def_set.get('without', [])
        app_data_set2   = app_def_set.get('except', [])

        if len(app_data_set) > 0:
            def_sys_path    = []
            def_sys_path2   = []
            for i in range(1, self.num_systems + 1):        
                for item in app_data_set:
                    def_sys_path.append({"path": item, "sys": i})

                for item in app_data_set2:
                    def_sys_path2.append({"path": item, "sys": i})
                    

            self.setting["sys_path"]    = def_sys_path
            self.setting["sys_path2"]   = def_sys_path2

        # Track file changes for diff view
        self.file_changes = {}  # Dictionary to track FileChangeEntry objects by system

        self.setWindowTitle("KG File Watcher")
        self.resize(1200, 800)
        self.center_window()

        # Compact professional theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1E1E1E;
            }
            QWidget {
                color: #CCCCCC;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 12px;
            }
            QPushButton {
                background-color: #007ACC;
                color: #FFFFFF;
                border: none;
                padding: 5px 12px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #1C97EA;
            }
            QPushButton:pressed {
                background-color: #005A9E;
            }
            QPushButton:disabled {
                background-color: #3A3A3A;
                color: #6E6E6E;
            }
            QPushButton:checked {
                background-color: #16825D;
            }
            QLineEdit {
                background-color: #252526;
                color: #CCCCCC;
                border: 1px solid #3C3C3C;
                border-radius: 6px;
                padding: 4px 8px;
                selection-background-color: #264F78;
                min-height: 22px;
                max-height: 28px;
            }
            QLineEdit:focus {
                border: 1px solid #007ACC;
                background-color: #292929;
            }
            QTextEdit {
                background-color: #252526;
                color: #CCCCCC;
                border: 1px solid #3C3C3C;
                border-radius: 6px;
                padding: 4px 8px;
                selection-background-color: #264F78;
            }
            QTextEdit:focus {
                border: 1px solid #007ACC;
                background-color: #292929;
            }
            QLabel {
                color: #CCCCCC;
                background-color: transparent;
                font-size: 12px;
            }
            QTableWidget {
                background-color: #252526;
                color: #CCCCCC;
                gridline-color: #2D2D2D;
                border: 1px solid #3C3C3C;
                border-radius: 6px;
            }
            QTableWidget::item {
                padding: 6px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #094771;
                color: #FFFFFF;
            }
            QTableWidget::item:hover {
                background-color: #2A2D2E;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #CCCCCC;
                padding: 8px 6px;
                border: none;
                border-bottom: 1px solid #3C3C3C;
                border-radius: 6px;
                font-weight: 600;
                font-size: 11px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 4px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #3C3C3C;
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4E4E4E;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 4px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background: #3C3C3C;
                border-radius: 2px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #4E4E4E;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        # Hide default menu bar and create custom title bar
        self.setMenuWidget(QWidget())  # Hide menu bar
        
        # Create custom title bar with tabs
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(38)
        self.title_bar.setStyleSheet("""
            QWidget {
                background-color: #2D2D2D;
                border-bottom: 1px solid #1E1E1E;
            }
        """)
        
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(16, 0, 16, 0)
        title_layout.setSpacing(24)
        
        # App title/logo on the left
        app_title = QLabel("KG File Watcher")
        app_title.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 600;
                padding: 0px;
            }
        """)
        title_layout.addWidget(app_title)
        
        # Tab navigation buttons
        self.tab_buttons = QWidget()
        tab_buttons_layout = QHBoxLayout(self.tab_buttons)
        tab_buttons_layout.setContentsMargins(0, 0, 0, 0)
        tab_buttons_layout.setSpacing(2)
        
        # Watcher tab
        self.watcher_tab = QPushButton("Watcher")
        self.watcher_tab.setCheckable(True)
        self.watcher_tab.setChecked(True)
        self.watcher_tab.clicked.connect(lambda: self.switch_page(0))
        self.watcher_tab.setFixedHeight(38)
        self.watcher_tab.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #9D9D9D;
                border: none;
                border-bottom: 2px solid transparent;
                padding: 0px 16px;
                font-size: 13px;
                font-weight: 500;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #2A2A2A;
                color: #FFFFFF;
            }
            QPushButton:checked {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border-bottom: 2px solid #007ACC;
            }
        """)
        
        # Git & Source tab
        self.git_tab = QPushButton("Git & Source")
        self.git_tab.setCheckable(True)
        self.git_tab.clicked.connect(lambda: self.switch_page(1))
        self.git_tab.setFixedHeight(38)
        self.git_tab.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #9D9D9D;
                border: none;
                border-bottom: 2px solid transparent;
                padding: 0px 16px;
                font-size: 13px;
                font-weight: 500;
                border-radius: 0px;
            }
            QPushButton:hover {
                background-color: #2A2A2A;
                color: #FFFFFF;
            }
            QPushButton:checked {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border-bottom: 2px solid #007ACC;
            }
        """)
        
        tab_buttons_layout.addWidget(self.watcher_tab)
        tab_buttons_layout.addWidget(self.git_tab)
        
        title_layout.addWidget(self.tab_buttons)
        title_layout.addStretch()
        
        # Settings button (gear icon)
        settings_btn = QPushButton("⚙ Settings")
        settings_btn.clicked.connect(self.open_settings)
        settings_btn.setFixedHeight(26)
        settings_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #9D9D9D;
                border: 1px solid transparent;
                padding: 3px 10px;
                font-size: 11px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
                color: #FFFFFF;
                border: 1px solid #3C3C3C;
            }
        """)
        title_layout.addWidget(settings_btn)

        # Create central widget with stacked pages
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Add custom title bar
        main_layout.addWidget(self.title_bar)
        
        # Create stacked widget for pages
        from PyQt6.QtWidgets import QStackedWidget
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("QStackedWidget { background-color: #1E1E1E; }")
        main_layout.addWidget(self.stacked_widget)
        
        # Create Watcher Page with professional layout
        self.watcher_page = QWidget()
        self.watcher_page.setStyleSheet("""
            QWidget {
                background-color: #1E1E1E;
            }
        """)
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.watcher_page.setLayout(self.layout)

        # Toolbar at top
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet("""
            QWidget {
                background-color: #252526;
                border-bottom: 1px solid #3C3C3C;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(20, 0, 20, 0)
        toolbar_layout.setSpacing(12)
        
        toolbar_title = QLabel("File Monitoring")
        toolbar_title.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 14px;
                font-weight: 600;
            }
        """)
        toolbar_layout.addWidget(toolbar_title)
        toolbar_layout.addStretch()

        self.button_start = QPushButton("▶ Start Watching")
        self.button_start.setCheckable(True)
        self.button_start.setFixedHeight(28)
        self.button_start.clicked.connect(self.toggle_watching)
        self.button_start.setStyleSheet("""
            QPushButton {
                background-color: #16825D;
                color: #FFFFFF;
                border: none;
                padding: 0px 16px;
                font-size: 12px;
                font-weight: 500;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #1B9A6F;
            }
            QPushButton:checked {
                background-color: #DC3545;
            }
        """)

        toolbar_layout.addWidget(self.button_start)
        self.layout.addWidget(toolbar)
        
        # Content area with padding
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #1E1E1E;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)
        self.layout.addWidget(content_widget)
        
        # Replace self.layout references with content_layout for child widgets
        self.content_layout = content_layout

        self.watcher_threads = []

        self.tables = []
        self.observers = []

        get_source_path = self.setting.get("source_path", {})
        self.watch_paths = []
        for i in range(self.num_systems):
            sys_key = f"sys{i+1}"
            self.watch_paths.append(get_source_path.get(sys_key, ""))

        self.watch_tables = {}
        self.input_desc = {}
        self.log_display = {}
        
        # Initialize file_changes for each system
        for i in range(self.num_systems):
            self.file_changes[f"sys{i}"] = []

        for i, path in enumerate(self.watch_paths):
            # Create a container widget for the label and text edit
            desc_container = QWidget()
            desc_layout = QHBoxLayout(desc_container)
            desc_layout.setContentsMargins(0, 0, 0, 0)  # Remove unnecessary margins
            desc_layout.setSpacing(10)  # Add spacing between the label and text edit

            # Create a label for the description
            label_desc = QLabel(f"Description for sys{i+1}:")
            label_desc.setStyleSheet("font-weight: bold; color: #E0E0E0; font-size: 12px;")
            label_desc.setAlignment(Qt.AlignmentFlag.AlignLeft)  # Align text to the left

            # Create a QLineEdit for user input
            text_edit = QLineEdit()
            text_edit.setPlaceholderText("Enter description here...")  # Placeholder text
            text_edit.setFixedHeight(30)  # Compact height
            text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            text_edit.setStyleSheet("""
                QLineEdit {
                    background-color: #3C3C3C;
                    color: #E0E0E0;
                    border: 2px solid #5A5A5A;
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 11px;
                }
                QLineEdit:focus {
                    border: 2px solid #1976D2;
                }
            """)

            # Store the QTextEdit in a dictionary for later access
            self.input_desc[f"sys{i}"] = text_edit

            # Add the label and text edit to the horizontal layout
            desc_layout.addWidget(label_desc)
            desc_layout.addWidget(text_edit)

            # Add the container widget (label + text edit) to the main layout
            self.content_layout.addWidget(desc_container)

            # Create the table for the current path
            table = FileWatcherTable(path)
            self.watch_tables[f"sys{i}"] = table
            self.tables.append(table)

            # Create a container widget for the table and buttons
            container_widget = QWidget()
            row_layout = QHBoxLayout(container_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            # Add the table to the layout
            row_layout.addWidget(table)

            # Add buttons (Copy, Copy & Send, and Git Compare)
            btn_copy = QPushButton("Copy")
            btn_copy.setFixedSize(110, 32)
            btn_copy.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_copy.clicked.connect(lambda checked, idx=i: self.copy_files_from_table(idx))
            btn_copy.setStyleSheet("""
                QPushButton {
                    background-color: #0D47A1;
                    color: #FFFFFF;
                    border: 1px solid #1565C0;
                    font-size: 11px;
                    font-weight: bold;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #1565C0;
                }
            """)

            btn_copy_send = QPushButton("Copy & Send")
            btn_copy_send.setFixedSize(110, 32)
            btn_copy_send.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_copy_send.clicked.connect(lambda checked, idx=i: self.copy_files_from_table(idx, True))
            btn_copy_send.setStyleSheet("""
                QPushButton {
                    background-color: #388E3C;
                    color: #FFFFFF;
                    border: 1px solid #4CAF50;
                    font-size: 11px;
                    font-weight: bold;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #4CAF50;
                }
            """)
            
            btn_git_compare = QPushButton("Git Compare")
            btn_git_compare.setFixedSize(110, 32)
            btn_git_compare.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_git_compare.clicked.connect(lambda checked, idx=i: self.open_git_compare(idx))
            btn_git_compare.setStyleSheet("""
                QPushButton {
                    background-color: #F57C00;
                    color: #FFFFFF;
                    border: 1px solid #FB8C00;
                    font-size: 11px;
                    font-weight: bold;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #FB8C00;
                }
            """)

            # Arrange buttons vertically
            row_layout_btn = QVBoxLayout()
            row_layout_btn.setSpacing(2)
            row_layout_btn.setContentsMargins(0, 0, 0, 0)
            row_layout_btn.addWidget(btn_copy)
            row_layout_btn.addWidget(btn_copy_send)
            row_layout_btn.addWidget(btn_git_compare)

            # Create a button container widget
            button_container = QWidget()
            button_container.setLayout(row_layout_btn)
            button_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

            # Add the button container to the layout
            row_layout.addWidget(button_container)

            # Set size policy for the container widget
            container_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

            # Add the container widget to the main layout
            self.content_layout.addWidget(container_widget)
        
        # Add watcher page to stacked widget
        self.stacked_widget.addWidget(self.watcher_page)
        
        # Create Git & Source Page
        self.git_page = self.create_git_source_page()
        self.stacked_widget.addWidget(self.git_page)
        
        # Set initial page to Watcher
        self.stacked_widget.setCurrentIndex(0)
    
    def create_git_source_page(self):
        """Create the Git & Source comparison page - professional design"""
        page = QWidget()
        page.setStyleSheet("""
            QWidget {
                background-color: #1E1E1E;
            }
        """)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar header
        toolbar = QWidget()
        toolbar.setFixedHeight(52)
        toolbar.setStyleSheet("""
            QWidget {
                background-color: #252526;
                border-bottom: 1px solid #3C3C3C;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(20, 0, 20, 0)
        toolbar_layout.setSpacing(12)
        
        title_label = QLabel("Git & Source Comparison")
        title_label.setStyleSheet("""
            QLabel {
                color: #FFFFFF; 
                font-size: 14px;
                font-weight: 600;
                background-color: transparent;
            }
        """)
        toolbar_layout.addWidget(title_label)
        toolbar_layout.addStretch()
        
        layout.addWidget(toolbar)
        
        # Content area with scroll
        content_scroll = QWidget()
        content_scroll.setStyleSheet("background-color: #1E1E1E;")
        content_layout = QVBoxLayout(content_scroll)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)
        
        # Description
        desc_label = QLabel("Select a system to compare and review changes")
        desc_label.setStyleSheet("""
            QLabel {
                font-size: 13px; 
                color: #858585; 
                background-color: transparent;
            }
        """)
        content_layout.addWidget(desc_label)
        
        # Systems list
        from PyQt6.QtWidgets import QVBoxLayout as QVBoxLayout2
        systems_widget = QWidget()
        systems_widget.setStyleSheet("background-color: transparent;")
        systems_layout = QVBoxLayout2(systems_widget)
        systems_layout.setSpacing(12)
        
        # Get configured systems
        get_source_path = self.setting.get("source_path", {})
        get_git_path = self.setting.get("git_path", {})
        
        has_systems = False
        for i in range(self.num_systems):
            sys_num = i + 1
            dest_key = f"sys{sys_num}"
            source_path = get_source_path.get(dest_key, "")
            git_path = get_git_path.get(dest_key, "")
            
            if source_path and git_path:
                has_systems = True
                
                # Create system card - Cursor style
                system_card = QWidget()
                system_card.setStyleSheet("""
                    QWidget {
                        background-color: #252526;
                        border-radius: 6px;
                        border: 1px solid #3C3C3C;
                    }
                    QWidget:hover {
                        border: 1px solid: #505050;
                        background-color: #2A2D2E;
                    }
                """)
                card_layout = QVBoxLayout(system_card)
                card_layout.setContentsMargins(20, 18, 20, 18)
                card_layout.setSpacing(14)
                
                # System title and button in horizontal layout
                header_layout = QHBoxLayout()
                
                system_title = QLabel(f"System {sys_num}")
                system_title.setStyleSheet("""
                    font-size: 15px;
                    font-weight: 600;
                    color: #FFFFFF;
                    background-color: transparent;
                """)
                
                system_btn = QPushButton("Compare")
                system_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #007ACC;
                        color: #FFFFFF;
                        border: none;
                        padding: 5px 14px;
                        font-size: 12px;
                        font-weight: 500;
                        border-radius: 6px;
                        min-height: 24px;
                    }
                    QPushButton:hover {
                        background-color: #1C97EA;
                    }
                    QPushButton:pressed {
                        background-color: #005A9E;
                    }
                """)
                system_btn.clicked.connect(lambda checked, gp=git_path, sp=source_path, sn=sys_num: 
                                          self.open_git_compare_embedded(gp, sp, sn))
                
                header_layout.addWidget(system_title)
                header_layout.addStretch()
                header_layout.addWidget(system_btn)
                
                # Paths
                paths_container = QWidget()
                paths_container.setStyleSheet("background-color: transparent;")
                paths_layout = QVBoxLayout(paths_container)
                paths_layout.setContentsMargins(0, 0, 0, 0)
                paths_layout.setSpacing(6)
                
                git_label = QLabel(f"Git: {git_path}")
                git_label.setStyleSheet("""
                    font-size: 12px; 
                    color: #858585; 
                    background-color: transparent;
                """)
                git_label.setWordWrap(True)
                
                source_label = QLabel(f"Source: {source_path}")
                source_label.setStyleSheet("""
                    font-size: 12px; 
                    color: #858585; 
                    background-color: transparent;
                """)
                source_label.setWordWrap(True)
                
                paths_layout.addWidget(git_label)
                paths_layout.addWidget(source_label)
                
                card_layout.addLayout(header_layout)
                card_layout.addWidget(paths_container)
                
                systems_layout.addWidget(system_card)
        
        if not has_systems:
            # No systems configured - Cursor style empty state
            no_config_card = QWidget()
            no_config_card.setStyleSheet("""
                QWidget {
                    background-color: transparent;
                }
            """)
            no_config_layout = QVBoxLayout(no_config_card)
            no_config_layout.setContentsMargins(40, 60, 40, 60)
            no_config_layout.setSpacing(12)
            
            no_config_label = QLabel("No systems configured")
            no_config_label.setStyleSheet("""
                font-size: 16px; 
                font-weight: 500;
                color: #CCCCCC; 
                background-color: transparent;
            """)
            no_config_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            no_config_desc = QLabel("Configure Git and Source paths in Settings to get started")
            no_config_desc.setStyleSheet("""
                font-size: 13px; 
                color: #858585; 
                background-color: transparent;
            """)
            no_config_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            no_config_layout.addWidget(no_config_label)
            no_config_layout.addWidget(no_config_desc)
            
            systems_layout.addWidget(no_config_card)
        
        systems_layout.addStretch()
        content_layout.addWidget(systems_widget)
        
        layout.addWidget(content_scroll)
        
        return page
    
    def open_git_compare_embedded(self, git_path, source_path, sys_num):
        """Open Git to Source comparison dialog from embedded page"""
        sys_key = f"sys{sys_num}"
        backup_path = self.setting.get("backup_path", {}).get(sys_key, "")
        
        # Get filtered paths for this system
        get_sys_path = self.setting.get("sys_path", [])
        get_sys_path2 = self.setting.get("sys_path2", [])
        
        without_list = [item.get("path", "") for item in get_sys_path if item.get("sys") == sys_num]
        except_list = [item.get("path", "") for item in get_sys_path2 if item.get("sys") == sys_num]
        
        # Remove empty strings
        without_list = [p for p in without_list if p]
        except_list = [p for p in except_list if p]
        
        # DEBUG OUTPUT
        print(f"\n{'='*60}")
        print(f"Git Compare Embedded - System {sys_num}")
        print(f"{'='*60}")
        print(f"  WITHOUT paths ({len(without_list)}): {without_list}")
        print(f"  EXCEPT paths ({len(except_list)}): {except_list}")
        print(f"{'='*60}\n")
        
        dialog = GitSourceCompareDialog(git_path, source_path, backup_path, without_list, except_list, self)
        dialog.setWindowTitle(f"Git ↔ Source - System {sys_num}")
        dialog.exec()
    
    def switch_page(self, page_index):
        """Switch to a different page and update tab highlighting"""
        self.stacked_widget.setCurrentIndex(page_index)
        
        # Update tab button states
        if page_index == 0:
            self.watcher_tab.setChecked(True)
            self.git_tab.setChecked(False)
        elif page_index == 1:
            self.watcher_tab.setChecked(False)
            self.git_tab.setChecked(True)
    
    def center_window(self):
        screen = QApplication.primaryScreen().geometry()  # Get screen size
        window = self.frameGeometry()  # Get window size
        window.moveCenter(screen.center())  # Center the window
        self.move(window.topLeft())

    def load_app_setting(self):
        response = requests.get(f"{API_URL}log_sys.php")
        # Check if request was successful (status code 200)
        json = {}
        if response.status_code == 200:
            json = response.json()  # Convert response to JSON

        return json

    def toggle_watching(self, checked):
        if checked:
            self.button_start.setText("⏹ Stop Watching")
            self.start_watching()
        else:
            self.button_start.setText("▶ Start Watching")
            self.stop_watching()

    def start_watching(self):
        if self.watcher_threads:
            print("Watchers are already running!")
            self.button_start.setText("⏹ Stop Watching")
            return

        self.dialog = LogDialog()
        self.dialog.show()

        self.button_start.setText("Stop")
        self.get_sys_path2 = self.setting.get("sys_path2", {})

        self.total_threads = len(self.watch_paths) 

        # Start the first thread
        self.start_next_thread(0)

    def start_next_thread(self, i):
        # Check if there are still threads to be started
        if i < len(self.watch_paths):
            path = self.watch_paths[i]
            if path:
                base_directory = rf"{path}"

                # Get excluded folders and files
                sys_excluded_folders = [
                    item for item in self.get_sys_path2
                    if item["sys"] == (i + 1) and os.path.isdir(os.path.join(base_directory, item["path"]))
                ]
                excluded_folders = [item["path"] for item in sys_excluded_folders]

                sys_excluded_files = [
                    item for item in self.get_sys_path2
                    if item["sys"] == (i + 1) and os.path.isfile(os.path.join(base_directory, item["path"]))
                ]
                excluded_files = [item["path"] for item in sys_excluded_files]

                table = self.watch_tables[f"sys{i}"]

                watcher_thread = WatcherThread(i, table, path, excluded_folders, excluded_files, self.dialog)
                watcher_thread.started_watching.connect(lambda p=path: self.on_started_watching(p))
                watcher_thread.stopped_watching.connect(lambda p=path: self.on_stopped_watching(p))

                # Connect preload_complete signal to update the counter and start the next thread
                watcher_thread.preload_complete.connect(lambda j=i: self.on_preload_complete(j + 1))

                # Append the thread to the list and start it
                self.watcher_threads.append(watcher_thread)

                # Start the thread
                watcher_thread.start()

    def on_preload_complete(self, j):
        print(f"called {j}")
        # Start the next thread if it hasn't started yet
        # if self.completed_threads < self.total_threads:
        if j < self.total_threads:
            self.start_next_thread(j)

        # Check if all threads have finished preloading
        print(f"completed_threads{j}={self.total_threads}")
        if j == self.total_threads:
            # Emit the signal to the dialog when all threads have finished preloading
            self.dialog.upt_log_signal.emit("Scan files Completed")

    def stop_watching(self):
        print("stop watch")
        for thread in self.watcher_threads:
            if thread.isRunning():
                thread.stop()  # Ensure each thread is properly stopped
                thread.wait()  # Wait for thread to finish before clearing
        self.watcher_threads.clear()  # Remove all references
        
        # Clear file contents from all tables to reset baseline for next scan
        for table_name, table in self.watch_tables.items():
            table.file_contents.clear()
            if DEBUG:
                print(f"Cleared file contents for {table_name}")
        
        self.button_start.setText("Start")  # Reset button text

    def on_started_watching(self, path):
        #print(f"on_started_watching start {self.button_start.isChecked()}")
        print(f"on_started_watching start {path}")
        self.button_start.setChecked(True)

    def on_stopped_watching(self, path):
        print(f"on_stopped_watching stop {path}")
        self.button_start.setText("Start")
        self.button_start.setChecked(False)

    def load_setting(self):
        settings = QSettings("KgObservedApp", "KgObservedAppStorage")
        setting = settings.value("setting", "")
        
        print(f"\n{'='*60}")
        print(f"Loading Settings")
        print(f"{'='*60}")
        print(f"Raw setting string length: {len(setting) if setting else 0}")
        
        if not setting:
            print("No settings found - returning empty dict")
            print(f"{'='*60}\n")
            return {}
        
        try:
            loaded = json.loads(setting)
            print(f"Settings loaded successfully")
            print(f"Keys: {list(loaded.keys())}")
            print(f"sys_path entries: {len(loaded.get('sys_path', []))}")
            print(f"sys_path2 entries: {len(loaded.get('sys_path2', []))}")
            
            # Show samples
            sys_path = loaded.get('sys_path', [])
            if sys_path:
                print(f"\nSample sys_path (WITHOUT):")
                for item in sys_path[:3]:
                    print(f"  - sys{item.get('sys')}: {item.get('path')}")
            
            sys_path2 = loaded.get('sys_path2', [])
            if sys_path2:
                print(f"\nSample sys_path2 (EXCEPT):")
                for item in sys_path2[:3]:
                    print(f"  - sys{item.get('sys')}: {item.get('path')}")
            
            print(f"{'='*60}\n")
            return loaded
        except Exception as e:
            print(f"Error loading settings: {e}")
            print(f"{'='*60}\n")
            return {}
    
    def update_destination_path(self, setting):
        """Update the destination path and save it to local storage."""
        self.save_destination_path(setting)  # Save the new path
        #QMessageBox.information(self, "Settings Updated", f"Destination path updated to:\n{self.destination_path}")
    def save_destination_path(self, setting):
        settings = QSettings("KgObservedApp", "KgObservedAppStorage")
        if DEBUG == True:
            print(f"save set {setting}")
        json_string = json.dumps(setting)
        settings.setValue("setting", json_string)

    def open_settings(self):
        dialog = SettingsDialog(self.setting, self)
        if dialog.exec():
            # Reload the app if number of systems changed
            if self.num_systems != self.setting.get("num_systems", 3):
                QMessageBox.information(self, "Settings Updated", "Number of systems changed. Please restart the application for changes to take effect.")
            
            # Update num_systems
            self.num_systems = self.setting.get("num_systems", 3)
    
    def open_git_compare(self, table_index):
        """Open Git to Source comparison dialog"""
        sys_num = table_index + 1
        dest_key = f"sys{sys_num}"
        
        get_source_path = self.setting.get("source_path", {})
        get_git_path = self.setting.get("git_path", {})
        get_backup_path = self.setting.get("backup_path", {})
        get_sys_path = self.setting.get("sys_path", [])
        get_sys_path2 = self.setting.get("sys_path2", [])
        
        source_path = get_source_path.get(dest_key, "")
        git_path = get_git_path.get(dest_key, "")
        backup_path = get_backup_path.get(dest_key, "")
        
        # Filter paths for this system
        without_list = [item.get("path", "") for item in get_sys_path if item.get("sys") == sys_num]
        except_list = [item.get("path", "") for item in get_sys_path2 if item.get("sys") == sys_num]
        
        # Remove empty strings
        without_list = [p for p in without_list if p]
        except_list = [p for p in except_list if p]
        
        # DEBUG OUTPUT
        print(f"\n{'='*60}")
        print(f"Git Compare - System {sys_num}")
        print(f"{'='*60}")
        print(f"Source: {source_path}")
        print(f"Git: {git_path}")
        print(f"Backup: {backup_path}")
        print(f"\nRaw sys_path (total): {len(get_sys_path)} items")
        if get_sys_path:
            print(f"Sample sys_path items:")
            for item in get_sys_path[:3]:
                print(f"  - sys{item.get('sys')}: {item.get('path')}")
        
        print(f"\nRaw sys_path2 (total): {len(get_sys_path2)} items")
        if get_sys_path2:
            print(f"Sample sys_path2 items:")
            for item in get_sys_path2[:3]:
                print(f"  - sys{item.get('sys')}: {item.get('path')}")
        
        print(f"\nFiltered for sys{sys_num}:")
        print(f"  WITHOUT paths ({len(without_list)}): {without_list}")
        print(f"  EXCEPT paths ({len(except_list)}): {except_list}")
        print(f"{'='*60}\n")
        
        if not source_path:
            QMessageBox.warning(self, "Configuration Error", 
                            f"Source path for System {sys_num} is not configured.")
            return
        
        if not git_path:
            QMessageBox.warning(self, "Configuration Error", 
                            f"Git path for System {sys_num} is not configured.")
            return
        
        dialog = GitSourceCompareDialog(git_path, source_path, backup_path, 
                                    without_list, except_list, self)
        dialog.exec()

    def copy_files_from_table(self, table_index, send = False):
        sys_num  = table_index+1
        dest_key = f"sys{sys_num}"
        desc_input = self.input_desc[f"sys{table_index}"]
        
        get_user = self.setting.get("user", {})
        get_source_path = self.setting.get("source_path", {})
        get_dest_path   = self.setting.get("dest_path", {})
        get_git_path    = self.setting.get("git_path", {})
        get_backup_path = self.setting.get("backup_path", {})
        get_sys_path    = self.setting.get("sys_path", {})
        telegram_token      = self.setting.get("telegram_token", "")
        telegram_chat_id    = self.setting.get("telegram_chat_id", "")
        
        src_root        = get_source_path.get(dest_key, "")
        dest_root       = get_dest_path.get(dest_key, "")
        git_root        = get_git_path.get(dest_key, "")
        backup_root     = get_backup_path.get(dest_key, "")
        sys_path        = [item for item in get_sys_path if item["sys"] == sys_num]

        # Collect file changes for diff view
        table = self.tables[table_index]
        changes = []
        
        for row in range(table.rowCount()):
            file_name   = table.item(row, 0).text()
            source_path = os.path.join(src_root, file_name)
            
            # Read current file content
            try:
                with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
                    new_content = f.read()
            except Exception as e:
                print(f"Error reading file {source_path}: {e}")
                new_content = None
            
            # Get old content from table storage (baseline from when Start was clicked)
            # Normalize path to forward slashes to match preload storage format
            normalized_source_path = source_path.replace("\\", "/")
            old_content = table.file_contents.get(normalized_source_path)
            
            # If not found with normalized path, try original path format
            if old_content is None:
                old_content = table.file_contents.get(source_path)
                # If found with original format, copy to normalized format for consistency
                if old_content is not None:
                    table.file_contents[normalized_source_path] = old_content
            
            # Create file change entry
            change = FileChangeEntry(source_path, old_content, new_content, src_root)
            changes.append(change)
        
        # Show diff dialog
        if changes:
            dialog = ChangeReviewDialog(changes, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return  # User cancelled
            
            # Get selected changes
            selected_changes = dialog.get_selected_changes()
            
            # Update file_contents with new content for selected files
            for change in selected_changes:
                if change.new_content is not None:
                    # Normalize path to forward slashes to match preload storage format
                    normalized_path = change.file_path.replace("\\", "/")
                    table.file_contents[normalized_path] = change.new_content
        else:
            QMessageBox.information(self, "No Changes", "No file changes to copy.")
            return

        # Create backup folder with timestamp if backup_path is configured
        backup_folder = None
        if backup_root and os.path.exists(backup_root):
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_folder = os.path.join(backup_root, timestamp)
            try:
                os.makedirs(backup_folder, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Backup Error", f"Could not create backup folder: {e}")
                backup_folder = None
        
        file_name_concat = ""
        backed_up_count = 0
        
        # Copy only selected files
        for change in selected_changes:
            source_path = change.file_path
            file_name = change.relative_path
            
            dir_path = os.path.dirname(file_name)
            base_name = os.path.basename(file_name)
            
            keep_relative = True
            for item in sys_path:
                if "path" in item and item["path"] and os.path.normpath(item["path"]) == os.path.normpath(dir_path):
                    keep_relative = False
                    break
            
            if src_root != '' and dest_root != '' and git_root != '': 
                git_path = os.path.join(git_root, file_name)
                dest_path = os.path.join(dest_root, file_name)
                
                # Backup git file before overwriting if it exists and backup is configured
                # Only backup once per file, before copying
                if backup_folder and os.path.exists(git_path) and os.path.isfile(git_path):
                    try:
                        backup_git_path = os.path.join(backup_folder, file_name)
                        os.makedirs(os.path.dirname(backup_git_path), exist_ok=True)
                        shutil.copy2(git_path, backup_git_path)
                        backed_up_count += 1
                    except Exception as e:
                        QMessageBox.warning(self, "Backup Warning", f"Could not backup git file {file_name}: {e}")
                
                if keep_relative:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(source_path, dest_path)
                    os.makedirs(os.path.dirname(git_path), exist_ok=True)
                    shutil.copy2(source_path, git_path)
                    file_name_concat += "\n" + file_name
                else:
                    dest_root_path = os.path.join(dest_root, base_name)
                    shutil.copy2(source_path, dest_root_path)
                    
                    os.makedirs(os.path.dirname(git_path), exist_ok=True)
                    shutil.copy2(source_path, git_path)
                    file_name_concat += "\n" + base_name
                    
            elif src_root != '' and dest_root != '':
                dest_path = os.path.join(dest_root, file_name)
                
                if keep_relative:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(source_path, dest_path)
                    file_name_concat += "\n" + file_name
                else:
                    dest_root_path = os.path.join(dest_root, base_name)
                    shutil.copy2(source_path, dest_root_path)
                    file_name_concat += "\n" + base_name
            
            # Remove copied file from table
            for row in range(table.rowCount()):
                if table.item(row, 0) and table.item(row, 0).text() == file_name:
                    table.removeRow(row)
                    # Remove from file_contents tracking (try both path formats)
                    normalized_source_path = source_path.replace("\\", "/")
                    if normalized_source_path in table.file_contents:
                        del table.file_contents[normalized_source_path]
                    elif source_path in table.file_contents:
                        del table.file_contents[source_path]
                    break
        if(send):

            # Telegram API endpoint for sending messages
            url = f'https://api.telegram.org/bot{telegram_token}/sendMessage'

            DESCIPTION = f"{get_user.get('username')}: "+ desc_input.text()
            MESSAGE = escape_markdown(file_name_concat)
            formatted_message = f"`{DESCIPTION}` \n {MESSAGE}"
            # inline_keyboard = [
            #     [
            #         {
            #             "text": "Click to Copy",
            #             "callback_data": f"copy_{DESCIPTION}"
            #         }
            #     ]
            # ]

            # Parameters for the API request
            params = {
                'chat_id': telegram_chat_id,
                'text': formatted_message,
                "parse_mode": "MarkdownV2",
                #"reply_markup": json.dumps({"inline_keyboard": inline_keyboard})
            }
            desc_input.setText('')
            response = requests.post(url, data=params)
            if response.status_code == 200:
                print("Message sent successfully!")
            else:
                print(f"Failed to send message. Status code: {response.status_code}")
                print(f"Response: {response.text}")
        
        # Show success message with backup info if files were backed up
        if backed_up_count > 0 and backup_folder:
            QMessageBox.information(
                self, "Backup Complete",
                f"✅ {backed_up_count} file(s) backed up to:\n{backup_folder}"
            )

        print(f"file_name_concat {file_name_concat}")

    def restart_app(self):
        """Restart the application"""
        print("Restarting application...")
        # Stop all watchers before restarting
        if self.watcher_threads:
            self.stop_watching()
        
        # Get the current executable path
        python = sys.executable
        script = sys.argv[0]
        
        # Close the current application
        QCoreApplication.quit()
        
        # Start a new instance
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            subprocess.Popen([sys.executable] + sys.argv[1:])
        else:
            # Running as script
            subprocess.Popen([python, script] + sys.argv[1:])
    
    def closeEvent(self, event):
        for observer in self.observers:
            observer.stop()
            observer.join()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = FileWatcherApp()
    main_window.show()
    sys.exit(app.exec())
