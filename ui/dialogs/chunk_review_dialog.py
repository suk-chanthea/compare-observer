"""Chunk-by-chunk file review dialog"""
import os
import difflib
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
                            QPushButton, QWidget, QScrollArea, QGroupBox, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QFileSystemWatcher
from PyQt6.QtGui import QCursor, QFont

from ui.styles import COLORS, FONTS, SPACING, STYLES


class ChangeChunk:
    """Represents a single change chunk"""
    def __init__(self, old_lines, new_lines, start_line):
        self.old_lines = old_lines
        self.new_lines = new_lines
        self.start_line = start_line
        self.decision = None  # None=pending, 'new'=accept new, 'old'=keep old
        

class ChunkReviewDialog(QDialog):
    """Dialog to review file changes chunk by chunk with individual accept/reject"""
    def __init__(self, file_path, old_content, new_content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Review Changes - {os.path.basename(file_path)}")
        self.setWindowFlags(Qt.WindowType.Window | 
                          Qt.WindowType.WindowMinimizeButtonHint | 
                          Qt.WindowType.WindowMaximizeButtonHint | 
                          Qt.WindowType.WindowCloseButtonHint)
        self.setSizeGripEnabled(True)
        
        self.file_path = file_path
        self.old_content = old_content or ""
        self.new_content = new_content or ""
        self.chunks = []
        self.chunk_widgets = []
        self.last_modified_time = 0
        
        # Parse changes into chunks
        self._parse_chunks()
        
        # Set size based on number of chunks (more compact for small changes)
        self.setMinimumWidth(1200)
        self._update_dialog_size()
        
        # Setup file watcher for auto-refresh
        self.file_watcher = QFileSystemWatcher([file_path])
        self.file_watcher.fileChanged.connect(self._on_file_changed)
        
        # Timer to debounce rapid file changes
        self.refresh_timer = QTimer()
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.setInterval(500)  # 500ms delay
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(int(SPACING['md'].replace('px', '')))
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header with auto-refresh indicator
        header_layout = QHBoxLayout()
        self.header = QLabel(f"📄 {os.path.basename(file_path)} - {len(self.chunks)} change(s) found")
        self.header.setStyleSheet(STYLES['label_heading'])
        header_layout.addWidget(self.header)
        
        header_layout.addStretch()
        
        # Auto-refresh indicator
        self.auto_refresh_label = QLabel("🔄 Auto-refresh ON")
        self.auto_refresh_label.setStyleSheet(f"color: {COLORS['accent_green']}; {FONTS['small']} padding: 4px 8px; background-color: {COLORS['bg_tertiary']}; border-radius: 4px;")
        self.auto_refresh_label.setToolTip("Dialog will automatically update when file changes")
        header_layout.addWidget(self.auto_refresh_label)
        
        header_layout.addSpacing(int(SPACING['sm'].replace('px', '')))
        
        refresh_btn = QPushButton("🔄")
        refresh_btn.setStyleSheet(STYLES['button_icon'])
        refresh_btn.setFixedSize(32, 32)
        refresh_btn.setToolTip("Manual refresh")
        refresh_btn.clicked.connect(self.refresh_changes)
        header_layout.addWidget(refresh_btn)
        
        self.main_layout.addLayout(header_layout)
        
        self.info_label = QLabel("💡 Review each change individually. Click ◄ to keep new code, ► to revert to old code.")
        self.info_label.setStyleSheet(STYLES['label_info'])
        self.main_layout.addWidget(self.info_label)
        
        # Scrollable area for chunks
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; }")
        
        self.chunks_widget = QWidget()
        self.chunks_layout = QVBoxLayout(self.chunks_widget)
        self.chunks_layout.setSpacing(15)
        self.chunks_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Create UI for each chunk
        self._rebuild_chunks()
        
        self.scroll.setWidget(self.chunks_widget)
        self.main_layout.addWidget(self.scroll)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(int(SPACING['sm'].replace('px', '')))
        
        self.accept_all_btn = QPushButton("✅ Accept All New")
        self.accept_all_btn.setStyleSheet(STYLES['button_success'])
        self.accept_all_btn.clicked.connect(self.accept_all_new)
        button_layout.addWidget(self.accept_all_btn)
        
        self.reject_all_btn = QPushButton("❌ Revert All to Old")
        self.reject_all_btn.setStyleSheet(STYLES['button_danger'])
        self.reject_all_btn.clicked.connect(self.reject_all_new)
        button_layout.addWidget(self.reject_all_btn)
        
        button_layout.addStretch()
        
        self.apply_btn = QPushButton("✓ Apply Selected Changes")
        self.apply_btn.setStyleSheet(STYLES['button_primary'])
        self.apply_btn.clicked.connect(self.apply_changes)
        button_layout.addWidget(self.apply_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(STYLES['button_secondary'])
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.main_layout.addLayout(button_layout)
    
    def _update_dialog_size(self):
        """Update dialog size based on number of chunks"""
        if len(self.chunks) <= 2:
            self.setMinimumHeight(400)
            self.resize(1200, 500)
        elif len(self.chunks) <= 5:
            self.setMinimumHeight(550)
            self.resize(1200, 600)
        else:
            self.setMinimumHeight(700)
            self.resize(1200, 750)
    
    def _rebuild_chunks(self):
        """Rebuild chunk widgets from current chunks list"""
        # Clear existing widgets
        for widget in self.chunk_widgets:
            widget.deleteLater()
        self.chunk_widgets.clear()
        
        # Remove stretch if it exists
        if self.chunks_layout.count() > 0:
            item = self.chunks_layout.takeAt(self.chunks_layout.count() - 1)
            if item and item.spacerItem():
                del item
        
        # Create new chunk widgets
        for i, chunk in enumerate(self.chunks):
            chunk_widget = self._create_chunk_widget(chunk, i + 1)
            self.chunks_layout.addWidget(chunk_widget, alignment=Qt.AlignmentFlag.AlignTop)
            self.chunk_widgets.append(chunk_widget)
        
        # Add stretch to push chunks to the top
        self.chunks_layout.addStretch()
    
    def _on_file_changed(self, path):
        """Handle file change event from file watcher"""
        # Debounce rapid changes (like auto-save)
        self.refresh_timer.start()
        
        # Re-add file to watcher (sometimes it gets removed on save)
        if path not in self.file_watcher.files():
            self.file_watcher.addPath(path)
    
    def _auto_refresh(self):
        """Auto-refresh after file changes (debounced)"""
        try:
            # Check if file was actually modified
            import os.path
            current_mtime = os.path.getmtime(self.file_path)
            if current_mtime == self.last_modified_time:
                return  # No actual change
            
            self.last_modified_time = current_mtime
            
            # Read current file content
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                new_content = f.read()
            
            # Only update if content actually changed
            if new_content == self.new_content:
                return
            
            self.new_content = new_content
            
            # Store current chunk count
            old_chunk_count = len(self.chunks)
            
            # Re-parse chunks
            self.chunks = []
            self._parse_chunks()
            
            # Update header
            self.header.setText(f"📄 {os.path.basename(self.file_path)} - {len(self.chunks)} change(s) found")
            
            # Update info label with auto-refresh notification
            if len(self.chunks) != old_chunk_count:
                self.info_label.setText(f"✨ Auto-updated! Found {len(self.chunks)} change(s). Review each change individually.")
                # Briefly highlight the auto-refresh label
                self.auto_refresh_label.setStyleSheet(f"color: white; {FONTS['small']} padding: 4px 8px; background-color: {COLORS['accent_green']}; border-radius: 4px; font-weight: bold;")
                QTimer.singleShot(1000, lambda: self.auto_refresh_label.setStyleSheet(f"color: {COLORS['accent_green']}; {FONTS['small']} padding: 4px 8px; background-color: {COLORS['bg_tertiary']}; border-radius: 4px;"))
            
            # Rebuild chunk widgets
            self._rebuild_chunks()
            
            # Update dialog size
            self._update_dialog_size()
            
        except Exception as e:
            print(f"Auto-refresh error: {e}")
    
    def refresh_changes(self):
        """Manual refresh - reload file content and update display"""
        try:
            # Read current file content
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                self.new_content = f.read()
            
            # Update modified time
            import os.path
            self.last_modified_time = os.path.getmtime(self.file_path)
            
            # Re-parse chunks
            self.chunks = []
            self._parse_chunks()
            
            # Update header
            self.header.setText(f"📄 {os.path.basename(self.file_path)} - {len(self.chunks)} change(s) found")
            
            # Update info label
            self.info_label.setText(f"🔄 Manually refreshed! Found {len(self.chunks)} change(s). Review each change individually.")
            
            # Rebuild chunk widgets
            self._rebuild_chunks()
            
            # Update dialog size
            self._update_dialog_size()
            
        except Exception as e:
            QMessageBox.warning(
                self,
                "Refresh Failed",
                f"Could not refresh changes: {e}"
            )
    
    def _parse_chunks(self):
        """Parse diff into separate change chunks"""
        old_lines = self.old_content.splitlines(keepends=True)
        new_lines = self.new_content.splitlines(keepends=True)
        
        # Generate diff
        differ = difflib.Differ()
        diff = list(differ.compare(old_lines, new_lines))
        
        # Group consecutive changes into chunks
        current_chunk_old = []
        current_chunk_new = []
        current_start = 0
        in_chunk = False
        line_num = 0
        
        for i, line in enumerate(diff):
            if line.startswith('  '):  # Unchanged line
                if in_chunk:
                    # End current chunk
                    self.chunks.append(ChangeChunk(
                        current_chunk_old,
                        current_chunk_new,
                        current_start
                    ))
                    current_chunk_old = []
                    current_chunk_new = []
                    in_chunk = False
                line_num += 1
            elif line.startswith('- '):  # Removed line
                if not in_chunk:
                    current_start = line_num
                    in_chunk = True
                current_chunk_old.append(line[2:])
            elif line.startswith('+ '):  # Added line
                if not in_chunk:
                    current_start = line_num
                    in_chunk = True
                current_chunk_new.append(line[2:])
                line_num += 1
            elif line.startswith('? '):  # Hint line (ignore)
                continue
        
        # Add last chunk if exists
        if in_chunk:
            self.chunks.append(ChangeChunk(
                current_chunk_old,
                current_chunk_new,
                current_start
            ))
    
    def _create_chunk_widget(self, chunk, chunk_num):
        """Create UI widget for a single chunk"""
        widget = QGroupBox(f"📝 Change #{chunk_num} (Line {chunk.start_line + 1})")
        widget.setStyleSheet(STYLES['group_box'])
        
        layout = QHBoxLayout(widget)
        layout.setSpacing(int(SPACING['md'].replace('px', '')))
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Old code
        old_box = QWidget()
        old_layout = QVBoxLayout(old_box)
        old_layout.setSpacing(int(SPACING['xs'].replace('px', '')))
        old_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        old_label = QLabel("❌ Old Code")
        old_label.setStyleSheet(f"color: {COLORS['diff_removed_text']}; {FONTS['subheading']}")
        old_layout.addWidget(old_label)
        
        old_text = QTextEdit()
        old_text.setReadOnly(True)
        old_text.setFont(QFont("Consolas", 10))
        
        # Calculate height based on number of lines (more compact)
        old_content = ''.join(chunk.old_lines) if chunk.old_lines else "[No content]"
        line_count = len(old_content.splitlines())
        # Dynamic height: min 40px, max 200px, ~25px per line
        text_height = min(max(40, line_count * 25), 200)
        old_text.setMaximumHeight(text_height)
        old_text.setMinimumHeight(40)
        
        old_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['diff_removed_bg']};
                color: {COLORS['diff_removed_text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: {SPACING['sm']};
            }}
        """)
        old_text.setPlainText(old_content)
        old_layout.addWidget(old_text)
        layout.addWidget(old_box)
        
        # Arrow buttons - align at top
        arrows = QWidget()
        arrows_layout = QVBoxLayout(arrows)
        arrows_layout.setSpacing(int(SPACING['md'].replace('px', '')))
        arrows_layout.setContentsMargins(0, 0, 0, 0)
        arrows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        arrow_left = QPushButton("◀")
        arrow_left.setFixedSize(40, 35)
        arrow_left.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        arrow_left.setToolTip("✅ Keep New Code")
        arrow_left.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent_green']};
                color: white;
                font-size: 18px;
                font-weight: bold;
                border: 2px solid {COLORS['accent_green']};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #13a313;
                border-color: #13a313;
            }}
        """)
        arrow_left.clicked.connect(lambda: self._select_chunk(chunk, 'new', widget))
        arrows_layout.addWidget(arrow_left)
        
        arrows_layout.addSpacing(int(SPACING['md'].replace('px', '')))
        
        arrow_right = QPushButton("▶")
        arrow_right.setFixedSize(40, 35)
        arrow_right.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        arrow_right.setToolTip("❌ Keep Old Code")
        arrow_right.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent_red']};
                color: white;
                font-size: 18px;
                font-weight: bold;
                border: 2px solid {COLORS['accent_red']};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #ff1f38;
                border-color: #ff1f38;
            }}
        """)
        arrow_right.clicked.connect(lambda: self._select_chunk(chunk, 'old', widget))
        arrows_layout.addWidget(arrow_right)
        
        arrows_layout.addStretch()  # Push buttons to top
        layout.addWidget(arrows)
        
        # New code
        new_box = QWidget()
        new_layout = QVBoxLayout(new_box)
        new_layout.setSpacing(int(SPACING['xs'].replace('px', '')))
        new_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        new_label = QLabel("✅ New Code")
        new_label.setStyleSheet(f"color: {COLORS['diff_added_text']}; {FONTS['subheading']}")
        new_layout.addWidget(new_label)
        
        new_text = QTextEdit()
        new_text.setReadOnly(True)
        new_text.setFont(QFont("Consolas", 10))
        
        # Calculate height based on number of lines (more compact)
        new_content = ''.join(chunk.new_lines) if chunk.new_lines else "[Deleted]"
        new_line_count = len(new_content.splitlines())
        # Dynamic height: min 40px, max 200px, ~25px per line
        new_text_height = min(max(40, new_line_count * 25), 200)
        new_text.setMaximumHeight(new_text_height)
        new_text.setMinimumHeight(40)
        
        new_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['diff_added_bg']};
                color: {COLORS['diff_added_text']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: {SPACING['sm']};
            }}
        """)
        new_text.setPlainText(new_content)
        new_layout.addWidget(new_text)
        layout.addWidget(new_box)
        
        return widget
    
    def _select_chunk(self, chunk, decision, widget):
        """Mark chunk with decision"""
        chunk.decision = decision
        
        # Visual feedback
        if decision == 'new':
            widget.setStyleSheet(f"""
                QGroupBox {{
                    {FONTS['subheading']}
                    border: 3px solid {COLORS['accent_green']};
                    border-radius: 6px;
                    margin-top: {SPACING['md']};
                    padding-top: {SPACING['md']};
                    background-color: {COLORS['diff_added_bg']};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: {SPACING['md']};
                    padding: 0 {SPACING['sm']};
                    color: {COLORS['accent_green']};
                }}
            """)
        else:  # old
            widget.setStyleSheet(f"""
                QGroupBox {{
                    {FONTS['subheading']}
                    border: 3px solid {COLORS['accent_red']};
                    border-radius: 6px;
                    margin-top: {SPACING['md']};
                    padding-top: {SPACING['md']};
                    background-color: {COLORS['diff_removed_bg']};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: {SPACING['md']};
                    padding: 0 {SPACING['sm']};
                    color: {COLORS['accent_red']};
                }}
            """)
    
    def accept_all_new(self):
        """Accept all new changes"""
        for i, chunk in enumerate(self.chunks):
            self._select_chunk(chunk, 'new', self.chunk_widgets[i])
    
    def reject_all_new(self):
        """Reject all new changes (keep old)"""
        for i, chunk in enumerate(self.chunks):
            self._select_chunk(chunk, 'old', self.chunk_widgets[i])
    
    def apply_changes(self):
        """Apply selected changes to file"""
        # Check if all chunks have decisions
        pending = [i+1 for i, c in enumerate(self.chunks) if c.decision is None]
        if pending:
            QMessageBox.warning(
                self,
                "Pending Decisions",
                f"Please make a decision for change(s): {', '.join(map(str, pending))}"
            )
            return
        
        # Rebuild file by merging chunks based on decisions
        final_lines = []
        old_lines = self.old_content.splitlines(keepends=True)
        new_lines = self.new_content.splitlines(keepends=True)
        
        # Use differ to get full comparison
        differ = difflib.Differ()
        diff = list(differ.compare(old_lines, new_lines))
        
        # Track which chunk we're in
        chunk_idx = 0
        in_chunk = False
        current_chunk_lines_old = []
        current_chunk_lines_new = []
        
        for line in diff:
            if line.startswith('  '):  # Unchanged line
                # If we were in a chunk, process it
                if in_chunk:
                    if chunk_idx < len(self.chunks):
                        chunk = self.chunks[chunk_idx]
                        if chunk.decision == 'new':
                            final_lines.extend(current_chunk_lines_new)
                        else:  # 'old'
                            final_lines.extend(current_chunk_lines_old)
                        chunk_idx += 1
                    current_chunk_lines_old = []
                    current_chunk_lines_new = []
                    in_chunk = False
                
                # Add unchanged line
                final_lines.append(line[2:])
                
            elif line.startswith('- '):  # Removed line
                in_chunk = True
                current_chunk_lines_old.append(line[2:])
                
            elif line.startswith('+ '):  # Added line
                in_chunk = True
                current_chunk_lines_new.append(line[2:])
                
            elif line.startswith('? '):  # Hint line
                continue
        
        # Process last chunk if exists
        if in_chunk and chunk_idx < len(self.chunks):
            chunk = self.chunks[chunk_idx]
            if chunk.decision == 'new':
                final_lines.extend(current_chunk_lines_new)
            else:  # 'old'
                final_lines.extend(current_chunk_lines_old)
        
        # Write to file
        final_content = ''.join(final_lines)
        
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            new_count = sum(1 for c in self.chunks if c.decision == 'new')
            old_count = sum(1 for c in self.chunks if c.decision == 'old')
            
            QMessageBox.information(
                self, 
                "Success", 
                f"File saved successfully!\n\n"
                f"✅ Kept {new_count} new change(s)\n"
                f"❌ Reverted {old_count} change(s) to old"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write file: {e}")
    
    def closeEvent(self, event):
        """Clean up resources when dialog closes"""
        # Stop timers
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        
        # Remove file watcher
        if hasattr(self, 'file_watcher'):
            self.file_watcher.removePath(self.file_path)
        
        event.accept()

