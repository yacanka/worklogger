@echo off
setlocal
color 0A
cls

cd /d "%~dp0"

if not exist "icon.png" (
    echo ERROR: icon.png was not found in %CD%
    echo Add the application icon and run this script again.
    pause
    exit /b 1
)

echo Building...
python -m PyInstaller --clean --noconfirm workLogger.spec
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo Finished: dist\workLogger.exe
pause >nul
endlocal
