@echo off
setlocal

REM 启动 Web 问卷服务（由 MainController\Start_Web.bat 调用，或直接双击运行）
REM 路径策略：优先打包 exe > 虚拟环境 Python > 系统 Python

set "ROOT=%~dp0"

REM 1. 优先启动打包好的 exe
if exist "%ROOT%_release\_tmp_SurveyWeb_allinone\SurveyWeb_onefile_lan.exe" (
    pushd "%ROOT%_release\_tmp_SurveyWeb_allinone"
    start "SurveyWeb" SurveyWeb_onefile_lan.exe %*
    popd
    goto :eof
)

REM 2. 尝试虚拟环境 Python（可能在另一台机器上失效，下面有回退）
if exist "%ROOT%Step1\Env\Scripts\python.exe" (
    "%ROOT%Step1\Env\Scripts\python.exe" -c "import sys; sys.exit(0)" >nul 2>&1
    if %errorlevel%==0 (
        pushd "%ROOT%Step1\Constructor"
        start "SurveyWeb" ..\Env\Scripts\python.exe Web_survey_app.py %*
        popd
        goto :eof
    )
)

REM 3. 回退到系统 Python
where python >nul 2>&1
if %errorlevel%==0 (
    pushd "%ROOT%Step1\Constructor"
    start "SurveyWeb" python Web_survey_app.py %*
    popd
    goto :eof
)

echo [错误] 找不到可用的 Python 解释器，请安装 Python 3.10+ 并加入 PATH。
pause
endlocal
