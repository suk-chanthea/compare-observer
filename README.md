# Compare Observer - File Watcher Application

A PyQt6-based file monitoring application with Telegram notifications and git synchronization capabilities.

## Project Structure (Clean Architecture)

```
compare_observer/
├── core/                   # Core business logic
│   ├── __init__.py
│   ├── models.py          # Data models (FileChangeEntry)
│   └── events.py          # Custom Qt events
├── services/              # Business services
│   ├── __init__.py
│   ├── file_watcher.py    # File monitoring service
│   └── telegram_service.py # Telegram notification service
├── ui/                    # User interface components
│   ├── __init__.py
│   ├── dialogs/           # Dialog windows
│   │   ├── __init__.py
│   │   ├── log_dialog.py
│   │   ├── file_diff_dialog.py
│   │   ├── git_compare_dialog.py
│   │   ├── change_review_dialog.py
│   │   └── settings_dialog.py
│   ├── widgets/           # Custom widgets
│   │   ├── __init__.py
│   │   ├── custom_text_edit.py
│   │   └── file_watcher_table.py
│   └── models/            # UI data models
│       ├── __init__.py
│       └── log_table_model.py
├── utils/                 # Utility functions
│   ├── __init__.py
│   └── helpers.py
├── config.py              # Application configuration
├── main.py                # Main application entry point
├── compare_observer.py    # Legacy/compatibility wrapper
├── requirements.txt       # Python dependencies
├── compare_observer.spec  # PyInstaller spec file
└── README.md             # This file
```

## Features

- **Real-time File Monitoring**: Watch multiple directories for file changes
- **File Comparison**: Side-by-side diff view with syntax highlighting
- **Git Integration**: Compare and synchronize files between git and source directories
- **Telegram Notifications**: Send file change notifications to Telegram
- **Multi-System Support**: Monitor multiple source/destination pairs
- **Change Review**: Review and selectively apply file changes

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

### Setup

1. Clone or download the repository:
```bash
git clone <repository-url>
cd compare_observer
```

2. Create a virtual environment (recommended):
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

### Development Mode

Run directly with Python:

```bash
python main.py
```

Or use the legacy file:

```bash
python compare_observer.py
```

## Building EXE File

### Method 1: Using PyInstaller (Recommended)

1. **Install PyInstaller** (if not already installed):
```bash
pip install pyinstaller
```

2. **Build the executable**:

For a single-file executable:
```bash
pyinstaller --onefile --windowed --name compare_observer main.py
```

For a directory-based executable (faster startup):
```bash
pyinstaller --onedir --windowed --name compare_observer main.py
```

3. **Advanced build with custom icon** (optional):
```bash
pyinstaller --onefile --windowed --name compare_observer --icon=icon.ico main.py
```

4. **Using the existing spec file**:
```bash
pyinstaller compare_observer.spec
```

### Method 2: Manual PyInstaller Configuration

Create or edit `compare_observer.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui', 
        'PyQt6.QtWidgets',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='compare_observer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True to see console output for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

Then build:
```bash
pyinstaller compare_observer.spec
```

### Build Output

After building, the executable will be located in:
- **onefile**: `dist/compare_observer.exe`
- **onedir**: `dist/compare_observer/compare_observer.exe`

### Troubleshooting Build Issues

1. **Missing modules error**:
   - Add the module name to `hiddenimports` in the spec file
   - Example: `hiddenimports=['missing_module_name']`

2. **Application doesn't start**:
   - Build with console enabled to see error messages:
     ```bash
     pyinstaller --console main.py
     ```

3. **Large file size**:
   - Use `--onedir` instead of `--onefile`
   - Exclude unnecessary packages using `--exclude-module`

4. **PyQt6 issues**:
   - Ensure PyQt6 is properly installed: `pip install --upgrade PyQt6`
   - Clear PyInstaller cache: `pyinstaller --clean compare_observer.spec`

## Configuration

### First Run

1. Launch the application
2. Go to `Config` → `App Settings`
3. Configure:
   - Username
   - Telegram Bot Token (optional)
   - Telegram Chat ID (optional)
   - Source/Destination/Git paths for each system
   - File/folder exclusions

### Telegram Setup (Optional)

1. Create a Telegram bot via [@BotFather](https://t.me/botfather)
2. Get your bot token
3. Get your chat ID (use [@userinfobot](https://t.me/userinfobot))
4. Enter credentials in App Settings

## Usage

1. **Configure Paths**: Set up source, destination, and git paths
2. **Start Watching**: Click the "Start" button
3. **Monitor Changes**: Changes will appear in the tables
4. **Copy Files**: Use "Copy" or "Copy & Send" buttons
5. **Review Changes**: Click on files to see diff comparison
6. **Git Compare**: Use "Git Compare" to sync with git repository

## Development

### Code Style

The project follows clean architecture principles:
- **Core**: Business logic and domain models
- **Services**: External integrations and business services  
- **UI**: User interface components
- **Utils**: Helper functions and utilities

### Adding New Features

1. Add models to `core/models.py`
2. Add business logic to `services/`
3. Add UI components to `ui/dialogs/` or `ui/widgets/`
4. Update `main.py` to integrate new features

## License

[Your License Here]

## Support

For issues or questions, please open an issue on the repository.

## Version History

- **v1.0.0**: Initial release with clean architecture refactoring
  - Multi-system file monitoring
  - Git integration
  - Telegram notifications
  - Side-by-side file comparison

## Credits

Developed using:
- PyQt6 for GUI
- Watchdog for file monitoring
- Python standard library

