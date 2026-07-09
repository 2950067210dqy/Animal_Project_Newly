@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

set "PYTHONPATH="
set "PYTHONHOME="
set "PYTHONNOUSERSITE=1"
set "VIRTUAL_ENV=%PROJECT_ROOT%venv"
set "PATH=%PROJECT_ROOT%venv\Scripts;%PATH%"

"%PROJECT_ROOT%venv\Scripts\python.exe" "%PROJECT_ROOT%main.py" %*

