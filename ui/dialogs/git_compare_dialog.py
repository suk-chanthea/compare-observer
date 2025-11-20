"""Git to source comparison dialog - UPDATED WITH FIXES"""
import os
import hashlib
import shutil
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QTableWidget, QTableWidgetItem, QMessageBox, QProgressBar,
                            QCheckBox, QWidget)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QHeaderView

from ui.dialogs.chunk_review_dialog import ChunkReviewDialog
from ui.styles import COLORS, FONTS, SPACING, STYLES


class ScanThread(QThread):
    """Thread for scanning file differences with progress"""
    progress = pyqtSignal(int, str)  # progress percentage, status message
    finished_scan = pyqtSignal(list)  # list of changes
    
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
    
    def _join_rel_paths(self, base, child):
        base_normalized = self._normalize_path(base)
        child_normalized = self._normalize_path(child)
        if not base_normalized:
            return child_normalized
        if not child_normalized:
            return base_normalized
        return f"{base_normalized}/{child_normalized}"
    
    def _is_excluded(self, rel_path):
        normalized = self._normalize_path(rel_path)
        
        # Auto-exclude .git and common system files
        if normalized.startswith('.git/') or normalized == '.git':
            return True
        if normalized.startswith('__pycache__/') or normalized == '__pycache__':
            return True
        if '.DS_Store' in normalized or 'Thumbs.db' in normalized:
            return True
        
        # Check user-defined exceptions
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
    
    def run(self):
        changes = []
        
        # Count total files first
        total_files = 0
        for root, dirs, files in os.walk(self.git_path):
            rel_dir = self._normalize_path(os.path.relpath(root, self.git_path))
            if rel_dir == ".":
                rel_dir = ""
            # Filter directories
            dirs[:] = [
                d for d in dirs
                if not self._is_excluded(self._join_rel_paths(rel_dir, d))
            ]
            total_files += len(files)
            
        for root, dirs, files in os.walk(self.source_path):
            rel_dir = self._normalize_path(os.path.relpath(root, self.source_path))
            if rel_dir == ".":
                rel_dir = ""
            dirs[:] = [
                d for d in dirs
                if not self._is_excluded(self._join_rel_paths(rel_dir, d))
            ]
            total_files += len(files)
        
        if total_files == 0:
            self.finished_scan.emit(changes)
            return
        
        processed = 0
        
        # Compare files in git path
        for root, dirs, files in os.walk(self.git_path):
            if not self._running:
                break
            
            rel_dir = self._normalize_path(os.path.relpath(root, self.git_path))
            if rel_dir == ".":
                rel_dir = ""
            
            # IMPORTANT: Filter out excluded directories BEFORE walking into them
            dirs[:] = [
                d for d in dirs
                if not self._is_excluded(self._join_rel_paths(rel_dir, d))
            ]
                
            for file in files:
                if not self._running:
                    break
                    
                git_file = os.path.join(root, file)
                git_rel_path = self._normalize_path(os.path.relpath(git_file, self.git_path))
                
                # Skip if file is excluded
                if self._is_excluded(git_rel_path):
                    processed += 1
                    continue
                
                display_rel_path, source_file = self._resolve_source_path_from_git(git_rel_path)
                
                status = ""
                if not os.path.exists(source_file):
                    status = "New in Git"
                else:
                    # Compare file contents
                    try:
                        with open(git_file, 'rb') as f1, open(source_file, 'rb') as f2:
                            git_hash = hashlib.md5(f1.read()).hexdigest()
                            source_hash = hashlib.md5(f2.read()).hexdigest()
                            if git_hash != source_hash:
                                status = "Modified"
                    except Exception as e:
                        status = f"Error: {e}"
                
                if status:
                    changes.append({
                        'rel_path': display_rel_path,
                        'status': status,
                        'git_file': git_file,
                        'source_file': source_file,
                        'git_rel_path': git_rel_path
                    })
                
                processed += 1
                if total_files > 0:
                    progress = int((processed / total_files) * 100)
                    self.progress.emit(progress, f"Scanning: {git_rel_path}")
        
        # Check for files in source but not in git
        for root, dirs, files in os.walk(self.source_path):
            if not self._running:
                break
            
            rel_dir = self._normalize_path(os.path.relpath(root, self.source_path))
            if rel_dir == ".":
                rel_dir = ""
            
            # Filter directories
            dirs[:] = [
                d for d in dirs
                if not self._is_excluded(self._join_rel_paths(rel_dir, d))
            ]
                
            for file in files:
                if not self._running:
                    break
                    
                source_file = os.path.join(root, file)
                rel_path = self._normalize_path(os.path.relpath(source_file, self.source_path))
                
                # Skip if excluded
                if self._is_excluded(rel_path):
                    processed += 1
                    continue
                
                git_rel_path, git_file = self._resolve_git_path_from_source(rel_path)
                
                if not os.path.exists(git_file):
                    changes.append({
                        'rel_path': rel_path,
                        'status': "Only in Source",
                        'git_file': git_file,
                        'source_file': source_file,
                        'git_rel_path': git_rel_path
                    })
                
                processed += 1
                if total_files > 0:
                    progress = int((processed / total_files) * 100)
                    self.progress.emit(progress, f"Scanning: {rel_path}")
        
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
        # Enable window resizing with minimize and maximize buttons
        self.setWindowFlags(Qt.WindowType.Window | 
                          Qt.WindowType.WindowMinimizeButtonHint | 
                          Qt.WindowType.WindowMaximizeButtonHint | 
                          Qt.WindowType.WindowCloseButtonHint)
        self.setSizeGripEnabled(True)
        self.git_path = git_path
        self.source_path = source_path
        self.backup_path = backup_path
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
        self.copy_to_source_btn.setToolTip("Copy all checked files from Git to Source (overwrites entire files)")
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
        """Scan for differences between Git and Source paths"""
        if not os.path.exists(self.git_path):
            QMessageBox.warning(self, "Error", f"Git path does not exist: {self.git_path}")
            return
        
        if not os.path.exists(self.source_path):
            QMessageBox.warning(self, "Error", f"Source path does not exist: {self.source_path}")
            return
        
        # Clear previous results
        self.file_list.setRowCount(0)
        self.changes.clear()
        self.checkboxes.clear()
        
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("⏳ Scanning files...")
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("⏳ Scanning...")
        
        # Start scan thread with exclusion paths
        self.scan_thread = ScanThread(self.git_path, self.source_path, self.without_paths, self.except_paths)
        self.scan_thread.progress.connect(self.on_scan_progress)
        self.scan_thread.finished_scan.connect(self.on_scan_finished)
        self.scan_thread.start()
    
    def on_scan_progress(self, percentage, message):
        """Update progress bar"""
        self.progress_bar.setValue(percentage)
        self.status_label.setText(f"⏳ {message} ({percentage}%)")
    
    def on_scan_finished(self, changes):
        """Handle scan completion"""
        self.changes = changes
        
        # Populate table
        for change in changes:
            self.add_change_to_list(
                change['rel_path'],
                change['status'],
                change['git_file'],
                change['source_file']
            )
        
        # Update UI
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"✅ Found {len(self.changes)} difference(s)")
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🔍 Scan for Changes")
        self.copy_to_source_btn.setEnabled(len(self.changes) > 0)
        self.select_all_btn.setEnabled(len(self.changes) > 0)
        self.deselect_all_btn.setEnabled(len(self.changes) > 0)
    
    def add_change_to_list(self, rel_path, status, git_file, source_file):
        """Add a change to the file list"""
        row = self.file_list.rowCount()
        self.file_list.insertRow(row)
        
        # Add checkbox
        checkbox = QCheckBox()
        checkbox.setChecked(True)  # Default checked
        cell_widget = QWidget()
        cell_layout = QHBoxLayout(cell_widget)
        cell_layout.addWidget(checkbox)
        cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list.setCellWidget(row, 0, cell_widget)
        self.checkboxes.append(checkbox)
        
        # File path
        self.file_list.setItem(row, 1, QTableWidgetItem(rel_path))
        
        # Color-code status
        status_item = QTableWidgetItem(status)
        if status == "Modified":
            status_item.setForeground(Qt.GlobalColor.yellow)
        elif status == "New in Git":
            status_item.setForeground(Qt.GlobalColor.green)
        elif status == "Only in Source":
            status_item.setForeground(Qt.GlobalColor.red)
        self.file_list.setItem(row, 2, status_item)
        
        # Add view button with icon
        view_btn = QPushButton("👁️ View & Apply")
        view_btn.setStyleSheet(STYLES['button_secondary'])
        view_btn.setToolTip("Review changes line-by-line and choose which to apply")
        view_btn.clicked.connect(lambda checked, g=git_file, s=source_file: self.view_diff(g, s))
        self.file_list.setCellWidget(row, 3, view_btn)
    
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
    
    def select_all_files(self):
        """Select all checkboxes"""
        for checkbox in self.checkboxes:
            checkbox.setChecked(True)
    
    def deselect_all_files(self):
        """Deselect all checkboxes"""
        for checkbox in self.checkboxes:
            checkbox.setChecked(False)
    
    def copy_to_source(self):
        """Copy checked files from Git to Source"""
        # Get checked rows
        checked_rows = [i for i, cb in enumerate(self.checkboxes) if cb.isChecked()]
        
        if not checked_rows:
            QMessageBox.information(self, "No Selection", "Please check files to copy")
            return
        
        # Confirm action
        reply = QMessageBox.question(
            self,
            "Confirm Copy",
            f"Copy {len(checked_rows)} file(s) from Git to Source?\n\n"
            f"⚠️ This will overwrite entire files in Source!",
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
                    # Backup existing file if backup path is configured
                    if self.backup_path and os.path.exists(self.backup_path) and os.path.exists(change['source_file']):
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        backup_folder = os.path.join(self.backup_path, timestamp)
                        os.makedirs(backup_folder, exist_ok=True)
                        
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
                    errors.append(f"{change['rel_path']}: {e}")
        
        # Show results
        if errors:
            error_msg = "\n".join(errors[:5])  # Show first 5 errors
            if len(errors) > 5:
                error_msg += f"\n... and {len(errors) - 5} more errors"
            QMessageBox.warning(
                self,
                "Partial Success",
                f"Copied {copied_count} file(s), but {len(errors)} failed:\n\n{error_msg}"
            )
        else:
            msg = f"✅ Successfully copied {copied_count} file(s) to Source!"
            if backed_up_count > 0:
                msg += f"\n💾 Backed up {backed_up_count} file(s) to {self.backup_path}"
            QMessageBox.information(self, "Success", msg)
        
        # Refresh the list
        self.scan_changes()
    
    def closeEvent(self, event):
        """Clean up when dialog closes"""
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.stop()
            self.scan_thread.wait()
        event.accept()