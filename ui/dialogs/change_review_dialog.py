"""Change review dialog for file modifications"""
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
                            QTableWidget, QTableWidgetItem, QPushButton, QCheckBox, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHeaderView
from PyQt6.QtGui import QFont

from ui.styles import COLORS, FONTS, SPACING, STYLES


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
        layout.setSpacing(int(SPACING['md'].replace('px', '')))
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Info label
        info_label = QLabel(f"📋 Total changes: {len(changes)} files")
        info_label.setStyleSheet(STYLES['label_heading'])
        layout.addWidget(info_label)
        
        # File list table
        self.file_list = QTableWidget()
        self.file_list.setColumnCount(3)
        self.file_list.setHorizontalHeaderLabels(["✓", "File Path", "Status"])
        self.file_list.setStyleSheet(STYLES['table'])
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
        self.current_file_label = QLabel("💡 Select a file from the list above to view changes")
        self.current_file_label.setStyleSheet(STYLES['label_subheading'])
        layout.addWidget(self.current_file_label)
        
        self.diff_viewer = QTextEdit()
        self.diff_viewer.setReadOnly(True)
        self.diff_viewer.setFont(QFont("Consolas", 10))
        self.diff_viewer.setStyleSheet(STYLES['text_edit_code'])
        layout.addWidget(self.diff_viewer)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(int(SPACING['sm'].replace('px', '')))
        
        self.select_all_btn = QPushButton("✅ Select All")
        self.select_all_btn.setStyleSheet(STYLES['button_secondary'])
        self.select_all_btn.clicked.connect(self.select_all)
        btn_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("❌ Deselect All")
        self.deselect_all_btn.setStyleSheet(STYLES['button_secondary'])
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        btn_layout.addWidget(self.deselect_all_btn)
        
        btn_layout.addStretch()
        
        self.apply_btn = QPushButton("✓ Apply Selected Changes")
        self.apply_btn.setStyleSheet(STYLES['button_primary'])
        self.apply_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.apply_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(STYLES['button_secondary'])
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

