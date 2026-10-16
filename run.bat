@echo off
setlocal enableextensions
cd /d "%~dp0"
title Invoice Pilot
set "PYEXE="
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
if not defined PYEXE ( py -3.11 -c "import sys" >nul 2>&1 && set "PYEXE=py -3.11" )
if not defined PYEXE ( python -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,11) else 1)" >nul 2>&1 && set "PYEXE=python" )
if not defined PYEXE (
  echo Python 3.11 not found. Install 3.11.9 from https://www.python.org/downloads/release/python-3119/
  pause & exit /b 1
)
%PYEXE% -c "import customtkinter, reportlab, PIL" >nul 2>&1
if errorlevel 1 (
  echo Installing packages ^(first run only^)...
  %PYEXE% -m pip install -r requirements.txt || ( echo Install failed. & pause & exit /b 1 )
)
%PYEXE% main.py
if errorlevel 1 pause
endlocal
