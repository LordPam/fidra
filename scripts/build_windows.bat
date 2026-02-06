@echo off
REM Build Fidra for Windows
REM
REM This script builds Fidra.exe for Windows.
REM
REM Usage:
REM   scripts\build_windows.bat
REM
REM Requirements:
REM   - Python 3.11+
REM   - pip install pyinstaller cairosvg pillow

setlocal enabledelayedexpansion

echo Building Fidra for Windows
echo.

REM Get script directory and project root
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

cd /d "%PROJECT_ROOT%"
echo Project root: %PROJECT_ROOT%
echo.

REM Check for pyinstaller
where pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: pyinstaller not found
    echo Install with: pip install pyinstaller
    exit /b 1
)

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
echo Running PyInstaller...
pyinstaller fidra.spec --noconfirm

REM Check if build succeeded
if not exist "dist\Fidra.exe" (
    echo Build failed: Fidra.exe not found
    exit /b 1
)

echo.
echo Build complete: dist\Fidra.exe
echo.

REM Get file size
for %%A in ("dist\Fidra.exe") do set "SIZE=%%~zA"
set /a "SIZE_MB=!SIZE! / 1048576"
echo Executable size: !SIZE_MB! MB

echo.
echo Build successful!
