"""Git to source comparison dialog - COMPLETE FIXED VERSION"""
import os
import hashlib
import shutil
import threading
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QTableWidget, QTableWidgetItem, QMessageBox, QProgressBar,
                            QCheckBox, QWidget)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QHeaderView

from ui.dialogs.chunk_review_dialog import ChunkReviewDialog
from ui.styles import COLORS, FONTS, SPACING, STYLES


class ScanThread(QThread):
    """Thread for scanning file differences with progress"""
    progress = pyqtSignal(int, str)
    finished_scan = pyqtSignal(list)
    
    def __init__(self, git_path, source_path, without_paths, except_paths):
        super().__init__()
        self.git_path = git_path
        self.source_path = source_path
        self.without_paths = [self._normalize_path(p) for p in (without_paths or []) if p]
        self.except_paths = [self._normalize_path(p) for p in (except_paths or []) if p]
        self._running = True
        
        # Auto-add common exclusions
        common_auto_exclude = ['.git', '__pycache__', '.DS_Store', 'Thumbs.db']
        for exc in common_auto_exclude:
            if exc not in self.except_paths:
                self.except_paths.append(exc)
    
    def _normalize_path(self, path):
        return path.replace("\\", "/").strip("/")
    
    def _safe_relpath(self, path, start):
        try:
            return os.path.relpath(path, start)
        except ValueError:
            path_norm = os.path.normpath(path)
            start_norm = os.path.normpath(start)
            
            if os.path.isabs(path_norm) and os.path.isabs(start_norm):
                path_drive = os.path.splitdrive(path_norm)[0]
                start_drive = os.path.splitdrive(start_norm)[0]
                
                if path_drive != start_drive and path_drive and start_drive:
                    return os.path.basename(path_norm)
            
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
        """Check if path should be excluded"""
        normalized = self._normalize_path(rel_path)
        
        for pattern in self.except_paths:
            # Exact match
            if normalized == pattern:
                return True
            # Directory match
            # Directory match (full or partial)
            if normalized == pattern or normalized.startswith(pattern + "/"):
                return True

            # Parent directory match
            parts = normalized.split("/")
            if pattern in parts:
                return True
            # Basename match
            if os.path.basename(normalized) == pattern:
                return True
            # Extension match
            if pattern.startswith('.') and normalized.endswith(pattern):
                return True
        
        return False
    
    def _matches_without_dir(self, rel_path):
        """Find the most specific WITHOUT directory that matches this path"""
        normalized = self._normalize_path(rel_path)
        best_match = None
        best_match_len = 0
        
        for directory in self.without_paths:
            if normalized.startswith(f"{directory}/") or normalized == directory:
                # Use the longest (most specific) match
                if len(directory) > best_match_len:
                    best_match = directory
                    best_match_len = len(directory)
        
        return best_match
    
    def _resolve_source_path_from_git(self, git_rel_path):
        normalized = self._normalize_path(git_rel_path)
        display_rel = normalized
        source_file = os.path.join(self.source_path, normalized.replace("/", os.sep))

        if os.path.exists(source_file):
            return display_rel, source_file

        # Only try flattening if without_paths is explicitly set and file not found directly
        if self.without_paths:
            basename = os.path.basename(normalized)
            for directory in self.without_paths:
                candidate_rel = self._normalize_path(os.path.join(directory, basename))
                candidate_file = os.path.join(self.source_path, candidate_rel.replace("/", os.sep))
                if os.path.exists(candidate_file):
                    return candidate_rel, candidate_file

            # If still not found, try first directory as fallback
            candidate_rel = self._normalize_path(os.path.join(self.without_paths[0], basename))
            candidate_file = os.path.join(self.source_path, candidate_rel.replace("/", os.sep))
            return candidate_rel, candidate_file

        # No without_paths: return the direct path (it may not exist yet)
        return display_rel, source_file
    
    def _resolve_git_path_from_source(self, source_rel_path):
        normalized = self._normalize_path(source_rel_path)
        
        # First, try direct path mapping
        git_file = os.path.join(self.git_path, normalized.replace("/", os.sep))
        if os.path.exists(git_file):
            return normalized, git_file
        
        # Only use flattening logic if without_paths is set and direct path not found
        if self.without_paths:
            matched_dir = self._matches_without_dir(normalized)
            if matched_dir:
                basename = os.path.basename(normalized)
                git_rel = basename
            else:
                git_rel = normalized
        else:
            git_rel = normalized
            
        git_file = os.path.join(self.git_path, git_rel.replace("/", os.sep))
        return git_rel, git_file
    
    def _check_path_with_timeout(self, path, timeout=10):
        result = [None]
        exception = [None]
        
        def check_path():
            try:
                if path.startswith('\\\\') or path.startswith('//'):
                    normalized_path = path.replace('/', '\\') if path.startswith('\\\\') else '\\' + path[1:].replace('/', '\\')
                    normalized_path = os.path.normpath(normalized_path)
                    
                    try:
                        os.listdir(normalized_path)
                        result[0] = True
                    except (OSError, PermissionError) as e:
                        try:
                            result[0] = os.path.exists(normalized_path)
                        except:
                            exception[0] = e
                            result[0] = False
                else:
                    result[0] = os.path.exists(path)
            except Exception as e:
                exception[0] = e
                result[0] = False
        
        is_network = path.startswith('\\\\') or path.startswith('//')
        
        if is_network:
            thread = threading.Thread(target=check_path)
            thread.daemon = True
            thread.start()
            thread.join(timeout=timeout)
            
            if thread.is_alive():
                return False, f"Network timeout after {timeout}s"
            
            if result[0] is None:
                return False, "Path check did not complete"
            
            if exception[0]:
                return result[0], str(exception[0])
            
            if not result[0]:
                return False, "Path not accessible"
            
            return result[0], None
        else:
            try:
                return os.path.exists(path), None
            except Exception as e:
                return False, str(e)
    
    def run(self):
        changes = []
        
        # Check paths
        self.progress.emit(0, "Checking Git path access...")
        git_accessible, git_error = self._check_path_with_timeout(self.git_path, timeout=10)
        if not git_accessible:
            self.progress.emit(0, f"❌ Git path not accessible: {git_error or 'Unknown error'}")
            self.finished_scan.emit(changes)
            return
        
        self.progress.emit(0, "Checking Source path access...")
        source_accessible, source_error = self._check_path_with_timeout(self.source_path, timeout=10)
        if not source_accessible:
            self.progress.emit(0, f"❌ Source path not accessible: {source_error or 'Unknown error'}")
            self.finished_scan.emit(changes)
            return
        
        # Count files
        total_files = 0
        try:
            for root, dirs, files in os.walk(self.git_path):
                try:
                    rel_dir = self._normalize_path(self._safe_relpath(root, self.git_path))
                    if rel_dir == ".":
                        rel_dir = ""
                    
                    dirs[:] = [
                        d for d in dirs
                        if not self._is_excluded(self._join_rel_paths(rel_dir, d))
                    ]
                    
                    total_files += len(files)
                except (OSError, PermissionError, TimeoutError):
                    continue
        except (OSError, PermissionError, TimeoutError) as e:
            self.progress.emit(0, f"❌ Error scanning Git path: {str(e)}")
            self.finished_scan.emit(changes)
            return
            
        try:
            for root, dirs, files in os.walk(self.source_path):
                try:
                    rel_dir = self._normalize_path(self._safe_relpath(root, self.source_path))
                    if rel_dir == ".":
                        rel_dir = ""
                    
                    dirs[:] = [
                        d for d in dirs
                        if not self._is_excluded(self._join_rel_paths(rel_dir, d))
                    ]
                    
                    total_files += len(files)
                except (OSError, PermissionError, TimeoutError):
                    continue
        except (OSError, PermissionError, TimeoutError) as e:
            self.progress.emit(0, f"❌ Error scanning Source path: {str(e)}")
            self.finished_scan.emit(changes)
            return
        
        if total_files == 0:
            self.finished_scan.emit(changes)
            return
        
        processed = 0
        
        # Scan git path
        try:
            for root, dirs, files in os.walk(self.git_path):
                if not self._running:
                    break
                
                try:
                    rel_dir = self._normalize_path(self._safe_relpath(root, self.git_path))
                    if rel_dir == ".":
                        rel_dir = ""
                    
                    dirs[:] = [
                        d for d in dirs
                        if not self._is_excluded(self._join_rel_paths(rel_dir, d))
                    ]
                        
                    for file in files:
                        if not self._running:
                            break
                        
                        try:
                            git_file = os.path.join(root, file)
                            git_rel_path = self._normalize_path(self._safe_relpath(git_file, self.git_path))
                            
                            if self._is_excluded(git_rel_path):
                                processed += 1
                                continue
                            
                            # Try to find corresponding file in source with the same relative path
                            source_file = os.path.join(self.source_path, git_rel_path.replace("/", os.sep))
                            found_in_source = os.path.exists(source_file)
                            status = ""
                            
                            # Compare if file exists in both
                            if found_in_source:
                                try:
                                    with open(git_file, 'rb') as f1, open(source_file, 'rb') as f2:
                                        git_hash = hashlib.md5(f1.read()).hexdigest()
                                        source_hash = hashlib.md5(f2.read()).hexdigest()
                                        if git_hash != source_hash:
                                            status = "Modified"
                                except (OSError, PermissionError, TimeoutError) as e:
                                    status = f"Error: {str(e)[:40]}"
                            else:
                                status = "New in Git"
                            
                            if status:
                                changes.append({
                                    'rel_path': git_rel_path,
                                    'status': status,
                                    'git_file': git_file,
                                    'source_file': source_file,
                                    'git_rel_path': git_rel_path
                                })
                            
                            processed += 1
                            if total_files > 0:
                                progress = int((processed / total_files) * 100)
                                self.progress.emit(progress, f"Scanning: {git_rel_path}")
                        except (OSError, PermissionError, TimeoutError):
                            processed += 1
                            continue
                except (OSError, PermissionError, TimeoutError):
                    continue
        except (OSError, PermissionError, TimeoutError) as e:
            self.progress.emit(0, f"❌ Error: {str(e)}")
        
        # Scan source path
        try:
            for root, dirs, files in os.walk(self.source_path):
                if not self._running:
                    break
                
                try:
                    rel_dir = self._normalize_path(self._safe_relpath(root, self.source_path))
                    if rel_dir == ".":
                        rel_dir = ""
                    
                    dirs[:] = [
                        d for d in dirs
                        if not self._is_excluded(self._join_rel_paths(rel_dir, d))
                    ]
                        
                    for file in files:
                        if not self._running:
                            break
                        
                        try:
                            source_file = os.path.join(root, file)
                            rel_path = self._normalize_path(self._safe_relpath(source_file, self.source_path))

                            # Check exclusions first
                            if self._is_excluded(rel_path):
                                processed += 1
                                continue
                            
                            # Skip files that are in WITHOUT directories - they're expected to be handled specially
                            if self._matches_without_dir(rel_path):
                                processed += 1
                                continue
                            
                            # Try to find corresponding file in git with the same relative path
                            git_file = os.path.join(self.git_path, rel_path.replace("/", os.sep))
                            found_in_git = os.path.exists(git_file)
                            
                            # Only report as "Only in Source" if file not found (and NOT in WITHOUT)
                            if not found_in_git:
                                try:
                                    changes.append({
                                        'rel_path': rel_path,
                                        'status': "Only in Source",
                                        'git_file': git_file,
                                        'source_file': source_file,
                                        'git_rel_path': rel_path
                                    })
                                except (OSError, PermissionError, TimeoutError):
                                    pass
                            
                            processed += 1
                            if total_files > 0:
                                progress = int((processed / total_files) * 100)
                                self.progress.emit(progress, f"Scanning: {rel_path}")
                        except (OSError, PermissionError, TimeoutError):
                            processed += 1
                            continue
                except (OSError, PermissionError, TimeoutError):
                    continue
        except (OSError, PermissionError, TimeoutError) as e:
            self.progress.emit(0, f"❌ Error: {str(e)}")
        
        self.finished_scan.emit(changes)
    
    def stop(self):
        self._running = False


class GitSourceCompareDialog(QDialog):
    """Dialog to compare files between Git path and Source path"""
    
    def __init__(self, git_path, source_path, backup_path="", without_paths=None, except_paths=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Git to Source Comparison")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(700)
        self.setWindowFlags(Qt.WindowType.Window | 
                          Qt.WindowType.WindowMinimizeButtonHint | 
                          Qt.WindowType.WindowMaximizeButtonHint | 
                          Qt.WindowType.WindowCloseButtonHint)
        self.setSizeGripEnabled(True)
        
        self.git_path = os.path.normpath(git_path)
        self.source_path = os.path.normpath(source_path)
        self.backup_path = os.path.normpath(backup_path) if backup_path else ""
        self.without_paths = without_paths or []
        self.except_paths = except_paths or []
        self.scan_thread = None
        
        layout = QVBoxLayout(self)
        layout.setSpacing(int(SPACING['md'].replace('px', '')))
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Info label
        info_layout = QHBoxLayout()
        info_label = QLabel(f"📂 Git: {os.path.basename(git_path)} ↔️ Source: {os.path.basename(source_path)}")
        info_label.setStyleSheet(STYLES['label_heading'])
        info_label.setToolTip(f"Git: {git_path}\nSource: {source_path}")
        info_layout.addWidget(info_label)
        
        info_layout.addStretch()
        
        # Scan button
        self.scan_btn = QPushButton("🔍 Scan for Changes")
        self.scan_btn.setStyleSheet(STYLES['button_primary'])
        self.scan_btn.clicked.connect(self.scan_changes)
        info_layout.addWidget(self.scan_btn)
        
        layout.addLayout(info_layout)
        
        # Exclusion info
        exclusion_parts = []
        if self.except_paths:
            exclusion_parts.append(f"Excluding: {', '.join(self.except_paths[:5])}" + ("..." if len(self.except_paths) > 5 else ""))
        if self.without_paths:
            exclusion_parts.append(f"Flattening: {', '.join(self.without_paths[:3])}" + ("..." if len(self.without_paths) > 3 else ""))
        
        if exclusion_parts:
            exclusion_info = QLabel(f"ℹ️ {' | '.join(exclusion_parts)}")
        else:
            exclusion_info = QLabel(f"ℹ️ Auto-excluding: .git, __pycache__, .DS_Store, Thumbs.db")
        exclusion_info.setStyleSheet(STYLES['label_info'])
        layout.addWidget(exclusion_info)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                text-align: center;
                background-color: {COLORS['bg_secondary']};
                color: {COLORS['text_primary']};
                height: 24px;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['accent_blue']};
                border-radius: 3px;
            }}
        """)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # File list table
        self.file_list = QTableWidget()
        self.file_list.setColumnCount(4)
        self.file_list.setHorizontalHeaderLabels(["☑️", "File Path", "Status", "Action"])
        self.file_list.setStyleSheet(STYLES['table'])
        self.file_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.file_list.setColumnWidth(0, 40)
        self.file_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.file_list)
        
        # Status label
        self.status_label = QLabel("💡 Click 'Scan for Changes' to start")
        self.status_label.setStyleSheet(STYLES['label_info'])
        layout.addWidget(self.status_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(int(SPACING['sm'].replace('px', '')))
        
        self.select_all_btn = QPushButton("☑️ Select All")
        self.select_all_btn.setStyleSheet(STYLES['button_secondary'])
        self.select_all_btn.clicked.connect(self.select_all_files)
        self.select_all_btn.setEnabled(False)
        btn_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("☐ Deselect All")
        self.deselect_all_btn.setStyleSheet(STYLES['button_secondary'])
        self.deselect_all_btn.clicked.connect(self.deselect_all_files)
        self.deselect_all_btn.setEnabled(False)
        btn_layout.addWidget(self.deselect_all_btn)
        
        btn_layout.addStretch()
        
        self.copy_to_source_btn = QPushButton("📋 Copy Checked to Source")
        self.copy_to_source_btn.setStyleSheet(STYLES['button_success'])
        self.copy_to_source_btn.clicked.connect(self.copy_to_source)
        self.copy_to_source_btn.setEnabled(False)
        btn_layout.addWidget(self.copy_to_source_btn)
        
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(STYLES['button_secondary'])
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        self.changes = []
        self.checkboxes = []
    
    def scan_changes(self):
        """Scan for differences"""
        self.file_list.setRowCount(0)
        self.changes.clear()
        self.checkboxes.clear()
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("⏳ Scanning files...")
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("⏳ Scanning...")
        
        self.scan_thread = ScanThread(self.git_path, self.source_path, self.without_paths, self.except_paths)
        self.scan_thread.progress.connect(self.on_scan_progress)
        self.scan_thread.finished_scan.connect(self.on_scan_finished)
        self.scan_thread.start()
    
    def on_scan_progress(self, percentage, message):
        self.progress_bar.setValue(percentage)
        self.status_label.setText(f"⏳ {message} ({percentage}%)")
    
    def on_scan_finished(self, changes):
        self.changes = changes
        
        for change in changes:
            self.add_change_to_list(
                change['rel_path'],
                change['status'],
                change['git_file'],
                change['source_file']
            )
        
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"✅ Found {len(self.changes)} difference(s)")
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🔍 Scan for Changes")
        self.copy_to_source_btn.setEnabled(len(self.changes) > 0)
        self.select_all_btn.setEnabled(len(self.changes) > 0)
        self.deselect_all_btn.setEnabled(len(self.changes) > 0)
    
    def add_change_to_list(self, rel_path, status, git_file, source_file):
        row = self.file_list.rowCount()
        self.file_list.insertRow(row)
        
        checkbox = QCheckBox()
        checkbox.setChecked(True)
        cell_widget = QWidget()
        cell_layout = QHBoxLayout(cell_widget)
        cell_layout.addWidget(checkbox)
        cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list.setCellWidget(row, 0, cell_widget)
        self.checkboxes.append(checkbox)
        
        self.file_list.setItem(row, 1, QTableWidgetItem(rel_path))
        
        status_item = QTableWidgetItem(status)
        if status == "Modified":
            status_item.setForeground(Qt.GlobalColor.yellow)
        elif status == "New in Git":
            status_item.setForeground(Qt.GlobalColor.green)
        elif status == "Only in Source":
            status_item.setForeground(Qt.GlobalColor.red)
        self.file_list.setItem(row, 2, status_item)
        
        view_btn = QPushButton("👁️ View & Apply")
        view_btn.setStyleSheet(STYLES['button_secondary'])
        view_btn.clicked.connect(lambda checked, g=git_file, s=source_file: self.view_diff(g, s))
        self.file_list.setCellWidget(row, 3, view_btn)
    
    def view_diff(self, git_file, source_file):
        try:
            if os.path.exists(source_file):
                with open(source_file, 'r', encoding='utf-8', errors='ignore') as f:
                    source_content = f.read()
            else:
                source_content = ""
            
            if os.path.exists(git_file):
                with open(git_file, 'r', encoding='utf-8', errors='ignore') as f:
                    git_content = f.read()
            else:
                git_content = ""
            
            if source_content == git_content:
                QMessageBox.information(self, "No Differences", "Files are identical.")
                return
            
            dialog = ChunkReviewDialog(source_file, source_content, git_content, self)
            dialog.setWindowTitle(f"Git → Source - {os.path.basename(source_file)}")
            
            result = dialog.exec()
            
            if result:
                self.status_label.setText(f"✅ Changes applied to {os.path.basename(source_file)}")
                self.scan_changes()
            else:
                self.status_label.setText(f"❌ No changes applied")
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error reading files: {e}")
    
    def select_all_files(self):
        for checkbox in self.checkboxes:
            checkbox.setChecked(True)
    
    def deselect_all_files(self):
        for checkbox in self.checkboxes:
            checkbox.setChecked(False)
    
    def copy_to_source(self):
        checked_rows = [i for i, cb in enumerate(self.checkboxes) if cb.isChecked()]
        
        if not checked_rows:
            QMessageBox.information(self, "No Selection", "Please check files to copy")
            return
        
        reply = QMessageBox.question(
            self, "Confirm Copy",
            f"Copy {len(checked_rows)} file(s) from Git to Source?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        copied_count = 0
        backed_up_count = 0
        errors = []
        
        for row in checked_rows:
            change = self.changes[row]
            if change['status'] != "Only in Source":
                try:
                    if self.backup_path and os.path.exists(self.backup_path) and os.path.exists(change['source_file']):
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        backup_folder = os.path.join(self.backup_path, timestamp)
                        os.makedirs(backup_folder, exist_ok=True)
                        
                        backup_file = os.path.join(backup_folder, change['rel_path'])
                        os.makedirs(os.path.dirname(backup_file), exist_ok=True)
                        shutil.copy2(change['source_file'], backup_file)
                        backed_up_count += 1
                    
                    os.makedirs(os.path.dirname(change['source_file']), exist_ok=True)
                    shutil.copy2(change['git_file'], change['source_file'])
                    copied_count += 1
                except Exception as e:
                    errors.append(f"{change['rel_path']}: {e}")
        
        if errors:
            error_msg = "\n".join(errors[:5])
            if len(errors) > 5:
                error_msg += f"\n... and {len(errors) - 5} more errors"
            QMessageBox.warning(
                self, "Partial Success",
                f"Copied {copied_count} file(s), but {len(errors)} failed:\n\n{error_msg}"
            )
        else:
            msg = f"✅ Successfully copied {copied_count} file(s) to Source!"
            if backed_up_count > 0:
                msg += f"\n💾 Backed up {backed_up_count} file(s)"
            QMessageBox.information(self, "Success", msg)
        
        self.scan_changes()
    
    def closeEvent(self, event):
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.stop()
            self.scan_thread.wait()
        event.accept()