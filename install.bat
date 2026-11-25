@echo off
setlocal
title Translate to English - install
cd /d "%~dp0"

echo.
echo  Translate to English - install
echo  ===============================
echo.

rem --- Find Python 3.10 to 3.13 ---------------------------------------------
set "PY="
for %%V in (3.12 3.11 3.13 3.10) do (
    if not defined PY (
        py -%%V -c "import tkinter" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys, tkinter; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1 && set "PY=python"
)
if defined PY goto :have_python

echo Python 3.10 - 3.13 is needed and wasn't found.
where winget >nul 2>&1
if errorlevel 1 goto :no_python
choice /c YN /m "Install Python 3.12 now"
if errorlevel 2 goto :no_python
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" goto :no_python
set "PY="%PY%""

:have_python
echo Using Python: %PY%

rem --- Virtual environment and libraries -----------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Creating the environment...
    %PY% -m venv .venv || goto :failed
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check

echo Installing libraries (a few minutes)...
"%VPY%" -m pip install -r live_translator\requirements.txt --disable-pip-version-check || goto :failed

where nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo.
    echo No NVIDIA graphics card found. It will run on the processor with a
    echo smaller model: it works, but translations are slower and less accurate.
) else (
    echo Installing the NVIDIA GPU libraries ^(about 1 GB^)...
    "%VPY%" -m pip install -r live_translator\requirements-gpu.txt --disable-pip-version-check || goto :failed
)

echo.
echo  Done. The speech model (about 3 GB) downloads the first time you start it.
echo  Next: set up Discord as described in README.md, then run start.bat.
echo.
pause
exit /b 0

:no_python
echo.
echo Install Python 3.12 from https://www.python.org/downloads/ (tick "Add
echo python.exe to PATH"), then run install.bat again.
pause
exit /b 1

:failed
echo.
echo Something went wrong (see the messages above). Check your internet
echo connection and run install.bat again.
pause
exit /b 1
