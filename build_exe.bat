@echo off
echo Building compare_observer.exe...
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Check if executable is running and close it
if exist "dist\compare_observer.exe" (
    echo Checking if compare_observer.exe is running...
    tasklist /FI "IMAGENAME eq compare_observer.exe" 2>nul | find /I /N "compare_observer.exe" >nul
    if "%ERRORLEVEL%"=="0" (
        echo Closing running instance...
        taskkill /F /IM compare_observer.exe 2>nul
        timeout /t 2 /nobreak >nul
    )
)

REM Clean previous builds (optional - uncomment to clean)
REM rmdir /s /q build dist 2>nul

REM Build the executable
pyinstaller compare_observer.spec

echo.
echo Build complete!
echo Executable location: dist\compare_observer.exe
echo.
pause

