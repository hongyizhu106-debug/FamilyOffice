@echo off
setlocal

REM Convenience wrapper: run repo-root Start_Web.bat
set ROOT_DIR=%~dp0..
call "%ROOT_DIR%\Start_Web.bat" %*

endlocal
