"""File diff comparison dialog"""
import os
import difflib
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
                            QGroupBox, QPushButton, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QFont


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

