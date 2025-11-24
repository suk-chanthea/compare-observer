@echo off
echo Building compare_observer.exe...
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Clean previous builds (optional - uncomment to clean)
REM rmdir /s /q build dist 2>nul

REM Build the executable
pyinstaller compare_observer.spec

echo.
echo Build complete!
echo Executable location: dist\compare_observer.exe
echo.
pause

