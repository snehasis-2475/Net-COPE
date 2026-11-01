@echo off
setlocal
rem Always run from the website folder, even when double-clicked or started elsewhere.
cd /d "%~dp0frontend"
title NetCoop AI - Website
echo ========================================================
echo NetCoop AI - Website
echo ========================================================

call npm --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js / npm was not found.
  echo Install Node.js 20 or newer from https://nodejs.org/ and open a new window.
  goto :fail
)

rem Install or repair dependencies only when they are missing or out of date.
call npm ls --depth=0 >nul 2>nul
if errorlevel 1 (
  echo Installing website dependencies, this can take a minute...
  call npm ci
  if errorlevel 1 (
    echo npm ci failed, retrying with npm install...
    call npm install
    if errorlevel 1 goto :fail
  )
)

echo.
echo Website: http://localhost:5173  - your browser opens automatically
echo Press Ctrl+C to stop.
echo.
call npm run dev -- --open
goto :end

:fail
echo.
echo [ERROR] Startup failed. Read the messages above for details.
pause
exit /b 1

:end
pause
