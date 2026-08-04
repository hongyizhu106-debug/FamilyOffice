@echo off
setlocal
cd /d %~dp0

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js not found in PATH.
  echo Install Node.js 18+ (recommended 20/22/24) and try again.
  pause
  exit /b 1
)

REM Optional: install deps if node_modules missing
if not exist node_modules (
  echo [INFO] node_modules not found, running npm install...
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] npm not found in PATH.
    pause
    exit /b 1
  )
  npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    pause
    exit /b 1
  )
)

echo [INFO] Starting FinanceMCP stdio server...
echo        This will wait for an MCP client to connect.
echo.

node .\build\index.js
