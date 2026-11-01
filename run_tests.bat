@echo off
setlocal
rem Always run from the repository root, even when double-clicked or started elsewhere.
cd /d "%~dp0"
title NetCoop AI - Pytest Diagnostic Suite
echo ========================================================
echo NetCoop AI - Pytest Diagnostic Suite
echo ========================================================

call :find_python
if errorlevel 1 goto :fail

%PY% -c "import pytest, fastapi, httpx, pandas" >nul 2>nul
if errorlevel 1 (
  echo Installing Python dependencies from requirements.txt...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
)

echo.
%PY% -m pytest -v
goto :end

:find_python
rem Prefer the project virtual environment, then python, then the py launcher.
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
  exit /b 0
)
python -c "import sys" >nul 2>nul
if not errorlevel 1 (
  set "PY=python"
  exit /b 0
)
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
  set "PY=py -3"
  exit /b 0
)
echo [ERROR] Python was not found.
echo Install Python 3.14 from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
exit /b 1

:fail
echo.
echo [ERROR] Startup failed. Read the messages above for details.
pause
exit /b 1

:end
pause
