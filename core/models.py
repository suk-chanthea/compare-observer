"""Data models for the application"""
import os
import difflib


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
            old_lines = self.old_content.splitlines(keepends=True)
            new_lines = self.new_content.splitlines(keepends=True)
            diff = difflib.unified_diff(old_lines, new_lines, lineterm='')
            return list(diff)[2:]  # Skip the file header lines

