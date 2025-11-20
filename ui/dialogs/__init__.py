"""Dialog windows for the application"""
from .log_dialog import LogDialog
from .file_diff_dialog import FileDiffDialog
from .git_compare_dialog import GitSourceCompareDialog
from .change_review_dialog import ChangeReviewDialog
from .settings_dialog import SettingsDialog

__all__ = [
    'LogDialog',
    'FileDiffDialog', 
    'GitSourceCompareDialog',
    'ChangeReviewDialog',
    'SettingsDialog'
]

