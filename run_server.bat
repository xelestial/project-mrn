@echo off
setlocal

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

if "%MRN_PYTHON_BIN%"=="" (
  set "PYTHON_BIN=%ROOT_DIR%\.venv\Scripts\python.exe"
) else (
  set "PYTHON_BIN=%MRN_PYTHON_BIN%"
)

if "%MRN_SERVER_HOST%"=="" (
  set "HOST=127.0.0.1"
) else (
  set "HOST=%MRN_SERVER_HOST%"
)

if "%MRN_SERVER_PORT%"=="" (
  set "PORT=9090"
) else (
  set "PORT=%MRN_SERVER_PORT%"
)

if "%MRN_SERVER_APP%"=="" (
  set "APP_MODULE=apps.server.src.app:app"
) else (
  set "APP_MODULE=%MRN_SERVER_APP%"
)

set "HEALTH_URL=http://%HOST%:%PORT%/health"

if "%~1"=="-h" goto :usage
if "%~1"=="--help" goto :usage

if not exist "%PYTHON_BIN%" (
  echo Missing Python runtime: %PYTHON_BIN%
  echo Create the virtualenv first, or set MRN_PYTHON_BIN.
  exit /b 1
)

curl -fsS "%HEALTH_URL%" >nul 2>nul
if not errorlevel 1 (
  echo MRN server is already healthy at %HEALTH_URL%
  exit /b 0
)

cd /d "%ROOT_DIR%"
set "PYTHONPATH=%ROOT_DIR%"

echo Starting MRN server: http://%HOST%:%PORT%
if "%MRN_RELOAD%"=="1" (
  "%PYTHON_BIN%" -m uvicorn %APP_MODULE% --host %HOST% --port %PORT% --reload
) else (
  "%PYTHON_BIN%" -m uvicorn %APP_MODULE% --host %HOST% --port %PORT%
)
exit /b %ERRORLEVEL%

:usage
echo Usage: run_server.bat
echo.
echo Environment:
echo   MRN_PYTHON_BIN     Python interpreter path ^(default: .venv\Scripts\python.exe^)
echo   MRN_SERVER_HOST    Backend host ^(default: 127.0.0.1^)
echo   MRN_SERVER_PORT    Backend port ^(default: 9090^)
echo   MRN_SERVER_APP     ASGI app module ^(default: apps.server.src.app:app^)
echo   MRN_RELOAD=1       Start uvicorn with --reload
exit /b 0
