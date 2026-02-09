@echo off
REM Build Fidra for Windows
REM
REM This script builds Fidra.exe for Windows.
REM
REM Usage:
REM   scripts\build_windows.bat
REM
REM Requirements:
REM   - Python 3.11 or 3.12

setlocal enabledelayedexpansion

echo ========================================
echo Building Fidra for Windows
echo ========================================
echo.

REM Get script directory and project root
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

cd /d "%PROJECT_ROOT%"
echo Project root: %CD%
echo.

REM Check for Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: Python not found
    echo Install Python 3.11 or 3.12 from https://python.org
    exit /b 1
)

REM Show Python version
echo Checking Python version...
python --version
echo.

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo Error: Failed to create virtual environment
        exit /b 1
    )
    echo Virtual environment created.
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install/upgrade dependencies
echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo Error: Failed to install dependencies
    exit /b 1
)
echo.

REM Generate icons if they don't exist
set "ICON_PATH=%PROJECT_ROOT%\fidra\resources\icons\fidra.ico"
if not exist "%ICON_PATH%" (
    echo Generating application icons...
    python scripts\generate_icons.py
)

REM Clean previous builds
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Run PyInstaller
echo.
echo Running PyInstaller...
pyinstaller fidra.spec --noconfirm

REM Check if build succeeded
if not exist "dist\Fidra.exe" (
    echo.
    echo Build failed: Fidra.exe not found
    exit /b 1
)

echo.
echo ========================================
echo Build complete: dist\Fidra.exe
echo ========================================
echo.

REM Get file size
for %%A in ("dist\Fidra.exe") do set "SIZE=%%~zA"
set /a "SIZE_MB=!SIZE! / 1048576"
echo Executable size: !SIZE_MB! MB

echo.
echo Build successful!
echo.
pause
