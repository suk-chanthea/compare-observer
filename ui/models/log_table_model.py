"""Table model for log display"""
from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex


class LogTableModel(QAbstractTableModel):
    """Efficient model for handling large log files in QTableView"""
    def __init__(self, log_file=None):
        super().__init__()
        self.log_file = log_file
        self.lines = []  # Initialize with an empty list
        if log_file:
            self.load_lines()

    def load_lines(self):
        """Loads only line references (not full file) for efficiency"""
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
        """Append a new row to the model"""
        QIndex = QModelIndex()  
        self.beginInsertRows(QIndex, len(self.lines), len(self.lines))  # Notify about row insertion
        self.lines.append(new_line + "\n")  # Add the new line to the data
        self.endInsertRows()  # End the row insertion process

