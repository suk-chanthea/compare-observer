"""Log dialog for displaying file scanning progress"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QTableView
from PyQt6.QtCore import pyqtSignal

from ui.models.log_table_model import LogTableModel


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
        self.user_input_name = QTextEdit(self)
        self.user_input_name.setFixedHeight(25)

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

