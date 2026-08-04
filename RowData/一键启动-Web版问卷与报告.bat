@echo off
setlocal

REM 一键启动 FamilyOfficerVersion1 本地网页服务
REM 优先启动可执行文件，否则用 Python 启动

set "ROOT=%~dp0"

REM 1. 优先启动打包好的 SurveyWeb_onefile_lan.exe
if exist "%ROOT%_release\_tmp_SurveyWeb_allinone\SurveyWeb_onefile_lan.exe" (
    pushd "%ROOT%_release\_tmp_SurveyWeb_allinone"
    start "SurveyWeb" SurveyWeb_onefile_lan.exe
    popd
    goto :eof
)

REM 2. 否则尝试用虚拟环境 Python 启动 Web_survey_app.py
if exist "%ROOT%Step1\Env\Scripts\python.exe" (
    pushd "%ROOT%Step1\Constructor"
    start "SurveyWeb" ..\Env\Scripts\python.exe Web_survey_app.py
    popd
    goto :eof
)

REM 3. 否则尝试用系统 Python 启动
pushd "%ROOT%Step1\Constructor"
start "SurveyWeb" python Web_survey_app.py
popd

echo 启动失败，请检查环境或联系开发者。
pause
endlocal
