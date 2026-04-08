@echo off
setlocal

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "PYTHON_BIN=%ROOT_DIR%\.venv311\Scripts\python.exe"
set "HOST=%MRN_SERVER_HOST%"
set "PORT=%MRN_SERVER_PORT%"
set "HEALTH_URL=http://%HOST%:%PORT%/health"

if "%HOST%"=="" set "HOST=127.0.0.1"
if "%PORT%"=="" set "PORT=8001"
set "HEALTH_URL=http://%HOST%:%PORT%/health"

if not exist "%PYTHON_BIN%" (
  echo Missing Python runtime: %PYTHON_BIN%
  echo Create %ROOT_DIR%\.venv311 first.
  exit /b 1
)

curl -fsS "%HEALTH_URL%" >nul 2>nul
if not errorlevel 1 (
  echo MRN server is already running at http://%HOST%:%PORT%
  echo Health check: %HEALTH_URL%
  exit /b 0
)

cd /d "%ROOT_DIR%"
set "PYTHONPATH=%ROOT_DIR%"
"%PYTHON_BIN%" -m uvicorn apps.server.src.app:app --host %HOST% --port %PORT%
