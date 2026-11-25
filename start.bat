@echo off
title Translate to English
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Translate to English is not installed yet.
    choice /c YN /m "Run install.bat now"
    if errorlevel 2 exit /b 1
    call install.bat || exit /b 1
)
chcp 65001 >nul
".venv\Scripts\python.exe" -m live_translator
if errorlevel 1 pause
