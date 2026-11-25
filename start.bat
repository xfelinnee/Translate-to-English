@echo off
title Translate to English
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Not installed yet, running install.bat first...
    call install.bat || exit /b 1
)
chcp 65001 >nul
".venv\Scripts\python.exe" -m live_translator
if errorlevel 1 pause
