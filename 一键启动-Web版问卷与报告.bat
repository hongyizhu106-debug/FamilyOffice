@echo off
chcp 65001 >nul
title 家族诊断问卷系统

echo.
echo  ============================================
echo   家族诊断问卷与报告系统
echo   网页地址: http://127.0.0.1:5000/
echo   访问密码: familyoffice
echo  ============================================
echo.
echo  正在启动服务，请稍候...

cd /d "%~dp0RowData"

REM 检查是否已有进程占用 5000 端口
netstat -ano | findstr ":5000 " | findstr LISTENING >nul 2>&1
if %errorlevel%==0 (
    echo  检测到服务已在运行，直接打开浏览器...
    timeout /t 1 /nobreak >nul
    start http://127.0.0.1:5000/
    goto :eof
)

REM 启动问卷服务（后台窗口）
start "问卷报告服务" Step1\Env\Scripts\python.exe MainController\MacinController.py

REM 等待服务就绪后打开浏览器
timeout /t 3 /nobreak >nul
start http://127.0.0.1:5000/

echo  浏览器已打开。关闭"问卷报告服务"窗口即可停止服务。
echo.
pause
