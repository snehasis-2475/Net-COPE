@echo off
setlocal
cd /d "%~dp0"
title NetCoop AI - Launcher
echo ========================================================
echo NetCoop AI - Starting backend and website
echo ========================================================

echo Starting the backend in a new window...
start "NetCoop AI - FastAPI Backend Server" "%~dp0run_backend.bat"

echo Waiting for the API at http://127.0.0.1:8000/health ...
set /a TRIES=0
:wait_api
curl.exe -s -f -o nul http://127.0.0.1:8000/health >nul 2>nul
if not errorlevel 1 goto :api_ready
set /a TRIES+=1
if %TRIES% geq 90 goto :api_slow
timeout /t 2 /nobreak >nul
goto :wait_api

:api_slow
echo The API is taking longer than expected - starting the website anyway.
echo The website header switches to ONLINE as soon as the API is up.
goto :start_site

:api_ready
echo API is online.

:start_site
echo Starting the website in a new window...
start "NetCoop AI - Website" "%~dp0run_frontend.bat"
echo.
echo Both services are running in their own windows.
echo To stop them, press Ctrl+C in each window or close the windows.
timeout /t 8 >nul
