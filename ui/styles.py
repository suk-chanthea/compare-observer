"""Consistent UI styles for the application"""

# Color Palette - Modern Dark Theme
COLORS = {
    # Background colors
    'bg_primary': '#1e1e1e',
    'bg_secondary': '#252526',
    'bg_tertiary': '#2d2d30',
    'bg_input': '#3c3c3c',
    
    # Text colors
    'text_primary': '#cccccc',
    'text_secondary': '#858585',
    'text_heading': '#ffffff',
    'text_link': '#569cd6',
    
    # Accent colors
    'accent_blue': '#0e639c',
    'accent_green': '#107c10',
    'accent_red': '#e81123',
    'accent_yellow': '#ffc83d',
    
    # Diff colors
    'diff_added_bg': '#1a4b1a',
    'diff_added_text': '#89d185',
    'diff_removed_bg': '#4b1818',
    'diff_removed_text': '#f48771',
    'diff_modified_bg': '#1a1a4b',
    
    # Border colors
    'border': '#3e3e3e',
    'border_hover': '#569cd6',
    'border_focus': '#0e639c',
}

# Typography
FONTS = {
    'heading': 'font-size: 14px; font-weight: bold;',
    'subheading': 'font-size: 12px; font-weight: bold;',
    'body': 'font-size: 11px;',
    'small': 'font-size: 10px;',
    'code': 'font-family: Consolas, Monaco, monospace; font-size: 10px;',
}

# Spacing
SPACING = {
    'xs': '4px',
    'sm': '8px',
    'md': '12px',
    'lg': '16px',
    'xl': '24px',
}

# Component Styles
STYLES = {
    'dialog': f"""
        QDialog {{
            background-color: {COLORS['bg_primary']};
            color: {COLORS['text_primary']};
        }}
    """,
    
    'label_heading': f"""
        QLabel {{
            color: {COLORS['text_heading']};
            {FONTS['heading']}
            padding: {SPACING['sm']};
        }}
    """,
    
    'label_subheading': f"""
        QLabel {{
            color: {COLORS['text_link']};
            {FONTS['subheading']}
            padding: {SPACING['xs']};
        }}
    """,
    
    'label_info': f"""
        QLabel {{
            color: {COLORS['text_secondary']};
            {FONTS['body']}
            padding: {SPACING['xs']};
        }}
    """,
    
    'button_primary': f"""
        QPushButton {{
            background-color: {COLORS['accent_blue']};
            color: white;
            border: none;
            border-radius: 4px;
            padding: {SPACING['sm']} {SPACING['lg']};
            {FONTS['body']}
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: #1177bb;
        }}
        QPushButton:pressed {{
            background-color: #0d5a8f;
        }}
        QPushButton:disabled {{
            background-color: {COLORS['bg_tertiary']};
            color: {COLORS['text_secondary']};
        }}
    """,
    
    'button_success': f"""
        QPushButton {{
            background-color: {COLORS['accent_green']};
            color: white;
            border: none;
            border-radius: 4px;
            padding: {SPACING['sm']} {SPACING['lg']};
            {FONTS['body']}
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: #13a313;
        }}
        QPushButton:pressed {{
            background-color: #0d660d;
        }}
    """,
    
    'button_danger': f"""
        QPushButton {{
            background-color: {COLORS['accent_red']};
            color: white;
            border: none;
            border-radius: 4px;
            padding: {SPACING['sm']} {SPACING['lg']};
            {FONTS['body']}
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: #ff1f38;
        }}
        QPushButton:pressed {{
            background-color: #c20d1f;
        }}
    """,
    
    'button_secondary': f"""
        QPushButton {{
            background-color: {COLORS['bg_tertiary']};
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            padding: {SPACING['sm']} {SPACING['lg']};
            {FONTS['body']}
        }}
        QPushButton:hover {{
            background-color: {COLORS['bg_input']};
            border-color: {COLORS['border_hover']};
        }}
        QPushButton:pressed {{
            background-color: {COLORS['bg_secondary']};
        }}
    """,
    
    'button_icon': f"""
        QPushButton {{
            background-color: transparent;
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            padding: {SPACING['xs']};
            font-size: 14px;
        }}
        QPushButton:hover {{
            background-color: {COLORS['bg_tertiary']};
            border-color: {COLORS['border_hover']};
        }}
        QPushButton:pressed {{
            background-color: {COLORS['bg_secondary']};
        }}
    """,
    
    'text_edit_code': f"""
        QTextEdit {{
            background-color: {COLORS['bg_primary']};
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            padding: {SPACING['sm']};
            {FONTS['code']}
            selection-background-color: {COLORS['accent_blue']};
        }}
    """,
    
    'text_edit_readonly': f"""
        QTextEdit {{
            background-color: {COLORS['bg_secondary']};
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            padding: {SPACING['sm']};
            {FONTS['code']}
        }}
    """,
    
    'group_box': f"""
        QGroupBox {{
            border: 2px solid {COLORS['border']};
            border-radius: 6px;
            margin-top: {SPACING['md']};
            padding-top: {SPACING['md']};
            {FONTS['subheading']}
            color: {COLORS['text_heading']};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: {SPACING['md']};
            padding: 0 {SPACING['sm']};
        }}
    """,
    
    'table': f"""
        QTableWidget {{
            background-color: {COLORS['bg_primary']};
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            gridline-color: {COLORS['border']};
            {FONTS['body']}
        }}
        QTableWidget::item {{
            padding: {SPACING['xs']};
        }}
        QTableWidget::item:selected {{
            background-color: {COLORS['accent_blue']};
            color: white;
        }}
        QTableWidget::item:hover {{
            background-color: {COLORS['bg_tertiary']};
        }}
        QHeaderView::section {{
            background-color: {COLORS['bg_tertiary']};
            color: {COLORS['text_heading']};
            padding: {SPACING['sm']};
            border: none;
            border-bottom: 2px solid {COLORS['border']};
            {FONTS['subheading']}
        }}
    """,
    
    'scrollbar': f"""
        QScrollBar:vertical {{
            background-color: {COLORS['bg_secondary']};
            width: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {COLORS['bg_input']};
            border-radius: 6px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {COLORS['border_hover']};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background-color: {COLORS['bg_secondary']};
            height: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {COLORS['bg_input']};
            border-radius: 6px;
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {COLORS['border_hover']};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
    """,
    
    'input': f"""
        QLineEdit, QComboBox, QSpinBox {{
            background-color: {COLORS['bg_input']};
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            padding: {SPACING['sm']};
            {FONTS['body']}
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border-color: {COLORS['border_focus']};
        }}
        QComboBox::drop-down {{
            border: none;
            padding-right: {SPACING['sm']};
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid {COLORS['text_primary']};
            margin-right: {SPACING['xs']};
        }}
    """,
    
    'checkbox': f"""
        QCheckBox {{
            color: {COLORS['text_primary']};
            {FONTS['body']}
            spacing: {SPACING['sm']};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {COLORS['border']};
            border-radius: 3px;
            background-color: {COLORS['bg_input']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {COLORS['accent_blue']};
            border-color: {COLORS['accent_blue']};
        }}
        QCheckBox::indicator:hover {{
            border-color: {COLORS['border_hover']};
        }}
    """,
    
    'tab_widget': f"""
        QTabWidget::pane {{
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            background-color: {COLORS['bg_primary']};
        }}
        QTabBar::tab {{
            background-color: {COLORS['bg_secondary']};
            color: {COLORS['text_primary']};
            border: 1px solid {COLORS['border']};
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            padding: {SPACING['sm']} {SPACING['lg']};
            {FONTS['body']}
        }}
        QTabBar::tab:selected {{
            background-color: {COLORS['bg_primary']};
            color: {COLORS['text_heading']};
            font-weight: bold;
        }}
        QTabBar::tab:hover {{
            background-color: {COLORS['bg_tertiary']};
        }}
    """,
}

def get_app_stylesheet():
    """Get the complete application stylesheet"""
    return f"""
        QWidget {{
            background-color: {COLORS['bg_primary']};
            color: {COLORS['text_primary']};
            {FONTS['body']}
        }}
        {STYLES['scrollbar']}
        {STYLES['table']}
        {STYLES['input']}
        {STYLES['checkbox']}
        {STYLES['tab_widget']}
    """

